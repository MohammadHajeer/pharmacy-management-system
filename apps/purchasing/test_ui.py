from datetime import timedelta
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Manufacturer, Medicine, MedicineUnit
from apps.core.models import PharmacySettings
from apps.inventory.models import MedicineBatch, StockMovement
from apps.parties.models import Supplier

from .models import PurchaseInvoice


class PurchaseWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="purchase-ui")
        cls.user.user_permissions.add(*Permission.objects.filter(content_type__app_label="purchasing"))
        cls.supplier = Supplier.objects.create(code="SUP-UI", name="Example supplier")
        cls.medicine = Medicine.objects.create(
            name="Example medicine", category=Category.objects.create(name="UI category"),
            manufacturer=Manufacturer.objects.create(name="UI manufacturer"),
        )
        cls.unit = MedicineUnit.objects.create(medicine=cls.medicine, name="Tablet", conversion_to_base=1, is_base_unit=True)
        PharmacySettings.objects.create(pharmacy_name="Example pharmacy", currency_code="USD")

    def setUp(self):
        self.client.force_login(self.user)
        self.create_url = reverse("purchasing:purchase-invoice-create")

    def payload(self):
        return {
            "supplier": str(self.supplier.pk), "supplier_invoice_reference": "REF-UI",
            "invoice_date": timezone.localdate().isoformat(), "currency_code": "USD",
            "lines-TOTAL_FORMS": "2", "lines-INITIAL_FORMS": "0", "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000", "lines-0-medicine": str(self.medicine.pk),
            "lines-0-medicine_unit": str(self.unit.pk), "lines-0-quantity": "2.000",
            "lines-0-unit_cost": "5.2500", "lines-0-discount_amount": "0.50",
            "lines-0-tax_rate_percent": "10", "lines-0-batch_number": "UI-BATCH",
            "lines-0-expiry_date": (timezone.localdate() + timedelta(days=180)).isoformat(),
        }

    def test_create_detail_and_post_preserve_the_existing_contract(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        response = self.client.get(self.create_url)
        self.assertContains(response, 'name="lines-TOTAL_FORMS"')
        self.assertContains(response, "Purchase lines")
        token = self.client.cookies["csrftoken"].value
        response = self.client.post(self.create_url, {**self.payload(), "csrfmiddlewaretoken": token}, follow=True)
        self.assertEqual(response.status_code, 200)
        invoice = PurchaseInvoice.objects.get()
        self.assertEqual(invoice.lines.count(), 1)
        self.assertEqual(str(invoice.grand_total), "11.00")
        self.assertContains(response, self.supplier.name)  # Draft snapshot is still blank.
        self.assertContains(response, "Post invoice")
        self.assertFalse(MedicineBatch.objects.exists())
        post_url = reverse("purchasing:purchase-invoice-post", args=[invoice.pk])
        response = self.client.post(post_url, {"csrfmiddlewaretoken": token}, follow=True)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "POSTED")
        self.assertContains(response, invoice.invoice_number)
        self.assertNotContains(response, "Post invoice")
        self.assertEqual(StockMovement.objects.filter(source_id=invoice.pk).count(), 1)
        self.supplier.name = "Changed supplier name"
        self.supplier.save()
        self.assertContains(self.client.get(reverse("purchasing:purchase-invoice-detail", args=[invoice.pk])), "Example supplier")

    def test_invalid_line_and_deleted_line_retain_values_and_errors(self):
        payload = self.payload()
        payload.update({"lines-0-quantity": "0", "lines-1-DELETE": "on"})
        response = self.client.post(self.create_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="REF-UI"')
        self.assertContains(response, 'value="UI-BATCH"')
        self.assertContains(response, 'id="id_lines-0-quantity-error"')
        tag = re.search(r'<input\s[^>]*name="lines-1-DELETE"[^>]*>', response.content.decode()).group()
        self.assertIn("checked", tag)
        self.assertFalse(PurchaseInvoice.objects.exists())

    def test_missing_management_form_exposes_formset_error(self):
        payload = self.payload()
        del payload["lines-TOTAL_FORMS"]
        response = self.client.post(self.create_url, payload)
        self.assertContains(response, "TOTAL_FORMS")
        self.assertContains(response, "This field is required.")
        self.assertFalse(response.context["formset"].is_valid())
        self.assertFalse(PurchaseInvoice.objects.exists())

    def test_multiple_submitted_lines_are_kept(self):
        payload = self.payload()
        payload.update({key.replace("lines-0-", "lines-1-"): value for key, value in list(payload.items()) if key.startswith("lines-0-")})
        payload["lines-1-batch_number"] = "UI-BATCH-2"
        response = self.client.post(self.create_url, payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PurchaseInvoice.objects.get().lines.count(), 2)

    def test_view_only_user_sees_no_create_or_post_actions(self):
        self.client.post(self.create_url, self.payload())
        invoice = PurchaseInvoice.objects.get()
        self.user.user_permissions.set(Permission.objects.filter(content_type__app_label="purchasing", codename="view_purchaseinvoice"))
        self.assertNotContains(self.client.get(reverse("purchasing:purchase-invoice-list")), "New purchase invoice")
        response = self.client.get(reverse("purchasing:purchase-invoice-detail", args=[invoice.pk]))
        self.assertNotContains(response, "Post invoice")
        self.assertEqual(self.client.post(reverse("purchasing:purchase-invoice-post", args=[invoice.pk])).status_code, 403)
