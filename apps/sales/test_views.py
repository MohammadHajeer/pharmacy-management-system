"""Presentation and controller regressions; service tests remain unchanged."""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import Permission
from django.utils import timezone

from apps.finance.models import CustomerPayment
from apps.inventory.models import StockMovement

from .models import SaleBatchAllocation, SalesInvoice
from .tests import SaleCompletionServiceTests
from .tests import PosTestDataMixin
from .services import complete_sale


class CompletionBoundaryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        SaleCompletionServiceTests.setUpTestData.__func__(cls)

    setUp = SaleCompletionServiceTests.setUp
    create_draft = SaleCompletionServiceTests.create_draft

    def test_insufficient_stock_is_usable_400_and_rolls_back(self):
        invoice = self.create_draft(quantity=Decimal("20.000"))
        self.client.force_login(self.actor)
        response = self.client.post(reverse("sales:pos-sale-complete", args=[invoice.pk]))
        self.assertEqual(response.status_code, 400)
        self.assertIn("requested base units are available", response.json()["errors"]["__all__"][0])
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, SalesInvoice.Status.DRAFT)
        self.assertEqual(invoice.invoice_number, "")
        self.assertIsNone(invoice.completed_at)
        for batch, expected in ((self.first_batch, "4.000"), (self.second_batch, "10.000"), (self.expired_batch, "100.000")):
            batch.refresh_from_db()
            self.assertEqual(batch.quantity_available_base, Decimal(expected))
        self.assertFalse(SaleBatchAllocation.objects.exists())
        self.assertFalse(StockMovement.objects.exists())
        self.assertFalse(CustomerPayment.objects.exists())

    def test_valid_completion_still_succeeds(self):
        invoice = self.create_draft()
        self.client.force_login(self.actor)
        response = self.client.post(reverse("sales:pos-sale-complete", args=[invoice.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "COMPLETED")
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_unexpected_exception_is_not_swallowed(self):
        invoice = self.create_draft()
        self.client.force_login(self.actor)
        with patch("apps.sales.views.complete_sale", side_effect=RuntimeError("unexpected")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("sales:pos-sale-complete", args=[invoice.pk]))


class SalesWorkspaceTests(PosTestDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.authorized_user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label__in=("sales", "finance"),
            codename__in=("complete_sale", "post_customerpayment", "view_salebatchallocation"),
        ))

    def draft_data(self, **kwargs):
        kwargs.setdefault("lines-0-medicine_unit", str(self.base_unit.pk))
        kwargs.setdefault("lines-0-quantity", "1.000")
        return super().draft_data(**kwargs)

    def setUp(self):
        self.client.force_login(self.authorized_user)

    def save_draft(self, **overrides):
        data = self.draft_data(customer=str(self.customer.pk), **overrides)
        response = self.client.post(reverse("sales:pos"), data)
        self.assertEqual(response.status_code, 302)
        return SalesInvoice.objects.latest("created_at")

    def completed_invoice(self):
        invoice = self.save_draft(**{"lines-0-prescription_warning_acknowledged": "on"})
        return complete_sale(actor=self.authorized_user, sales_invoice_id=invoice.pk).invoice

    def test_new_workspace_is_empty_and_does_not_render_catalog_select(self):
        response = self.client.get(reverse("sales:pos"))
        self.assertContains(response, "Sales checkout")
        self.assertContains(response, "Ready for the first medicine")
        self.assertEqual(response.context["medicine_data"], [])
        self.assertNotContains(response, self.medicine.name)
        self.assertContains(response, "Walk-in — no saved customer")

    def test_create_edit_remove_and_preserve_server_totals(self):
        invoice = self.save_draft(line_count=2)
        url = reverse("sales:pos-workspace", args=[invoice.pk])
        response = self.client.get(url)
        self.assertContains(response, self.medicine.name)
        self.assertContains(response, "Prescription required")
        self.assertContains(response, "Available: 10 Tablet")
        self.assertContains(response, "FEFO")
        self.assertEqual(invoice.lines.count(), 2)
        data = self.draft_data(customer=str(self.customer.pk), **{"lines-0-quantity": "2"})
        self.assertRedirects(self.client.post(url, data), url)
        invoice.refresh_from_db()
        self.assertEqual(invoice.lines.count(), 1)
        self.assertEqual(invoice.lines.get().quantity, Decimal("2.000"))
        self.assertGreater(invoice.grand_total, 0)
        self.assertFalse(StockMovement.objects.exists())

    def test_invalid_draft_keeps_entered_values_and_saved_state(self):
        invoice = self.save_draft()
        total = invoice.grand_total
        response = self.client.post(reverse("sales:pos-workspace", args=[invoice.pk]), self.draft_data(customer=str(self.customer.pk), **{"lines-0-discount_amount": "9999"}))
        self.assertContains(response, "Draft not saved", status_code=400)
        self.assertContains(response, 'value="9999"', status_code=400)
        self.assertFalse(response.context["can_complete"])
        invoice.refresh_from_db()
        self.assertEqual(invoice.grand_total, total)

    def test_saved_customer_and_prescription_are_rendered_selected(self):
        invoice = self.save_draft(prescription=str(self.prescription.pk))
        response = self.client.get(reverse("sales:pos-workspace", args=[invoice.pk]))
        self.assertEqual(invoice.prescription, self.prescription)
        self.assertContains(response, f'value="{self.customer.pk}" selected')
        self.assertContains(response, f'value="{self.prescription.pk}" selected')

    def test_walk_in_completion_requires_full_payment_and_preserves_null_customer(self):
        from apps.core.models import PaymentMethod
        method = PaymentMethod.objects.create(code="UI-CASH", name="Cash")
        response = self.client.post(reverse("sales:pos"), self.draft_data(**{"lines-0-prescription_warning_acknowledged": "on"}))
        self.assertEqual(response.status_code, 302)
        invoice = SalesInvoice.objects.get()
        self.assertIsNone(invoice.customer_id)
        url = reverse("sales:pos-sale-complete", args=[invoice.pk])
        self.assertEqual(self.client.post(url).status_code, 400)
        payment = {"payment_method": str(method.pk), "amount": str(invoice.grand_total), "paid_at": timezone.now().isoformat()}
        response = self.client.post(url, payment)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["payment_status"], "PAID")
        invoice.refresh_from_db()
        self.assertIsNone(invoice.customer_id)
        self.eligible_batch.refresh_from_db()
        self.assertLess(self.eligible_batch.quantity_available_base, Decimal("10.000"))

    def test_unacknowledged_prescription_rejected_and_draft_preserved(self):
        invoice = self.save_draft()
        response = self.client.post(reverse("sales:pos-sale-complete", args=[invoice.pk]))
        self.assertEqual(response.status_code, 400)
        self.assertIn("must be acknowledged", str(response.json()))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "DRAFT")

    def test_payment_reference_overpayment_and_partial_payment(self):
        from apps.core.models import PaymentMethod
        method = PaymentMethod.objects.create(code="UI-CARD", name="Card", requires_reference=True)
        invoice = self.save_draft(**{"lines-0-prescription_warning_acknowledged": "on"})
        url = reverse("sales:pos-sale-complete", args=[invoice.pk])
        payment = {"payment_method": str(method.pk), "amount": "0.10", "paid_at": timezone.now().isoformat()}
        response = self.client.post(url, payment)
        self.assertEqual(response.status_code, 400)
        self.assertIn("requires a reference", str(response.json()))
        self.assertFalse(StockMovement.objects.exists())
        response = self.client.post(url, {**payment, "reference": "POS-TEST", "amount": "9999"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot exceed", str(response.json()))
        response = self.client.post(url, {**payment, "reference": "POS-TEST"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["payment_status"], "PARTIAL")

    def test_completed_invoice_print_receipt_and_finance_action(self):
        invoice = self.completed_invoice()
        detail_url = reverse("sales:invoice-detail", args=[invoice.pk])
        response = self.client.get(detail_url)
        self.assertContains(response, "Sale completed")
        self.assertContains(response, invoice.invoice_number)
        self.assertContains(response, "Record payment")
        self.assertContains(response, reverse("finance:customer-payment-record", args=[invoice.pk]))
        self.assertContains(response, "FEFO allocation traceability")
        self.assertNotContains(response, "Open checkout")
        self.assertRedirects(self.client.get(reverse("sales:pos-workspace", args=[invoice.pk])), detail_url)
        self.pharmacy_settings.invoice_header = "Test invoice header"
        self.pharmacy_settings.invoice_footer = "Invoice footer"
        self.pharmacy_settings.receipt_footer = "Receipt footer"
        self.pharmacy_settings.save()
        print_url = reverse("sales:invoice-print", args=[invoice.pk])
        response = self.client.get(print_url)
        self.assertContains(response, "Test invoice header")
        self.assertContains(response, "Invoice footer")
        self.assertContains(response, invoice.pharmacy_name_snapshot)
        self.assertContains(response, "sales/print.css")
        self.assertNotContains(response, 'data-navigation-sidebar')
        self.assertContains(self.client.get(print_url + "?format=receipt"), "Receipt footer")

    def test_finance_and_allocation_visibility_requires_permissions(self):
        invoice = self.completed_invoice()
        self.authorized_user.user_permissions.remove(*Permission.objects.filter(codename__in=("post_customerpayment", "view_salebatchallocation")))
        response = self.client.get(reverse("sales:invoice-detail", args=[invoice.pk]))
        self.assertNotContains(response, "Record payment")
        self.assertNotContains(response, "FEFO allocation traceability")

    def test_no_print_for_uncompleted_draft(self):
        invoice = self.save_draft()
        self.assertRedirects(self.client.get(reverse("sales:invoice-print", args=[invoice.pk])), reverse("sales:invoice-detail", args=[invoice.pk]))

    def test_anonymous_and_unpermitted_users_cannot_access_pages_or_edit(self):
        invoice = self.save_draft()
        urls = [reverse("sales:pos"), reverse("sales:invoice-list"), reverse("sales:pos-workspace", args=[invoice.pk]), reverse("sales:invoice-detail", args=[invoice.pk]), reverse("sales:invoice-print", args=[invoice.pk])]
        self.client.logout()
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.unauthorized_user)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(reverse("sales:pos"), self.draft_data()).status_code, 403)
        self.assertEqual(self.client.post(reverse("sales:pos-workspace", args=[invoice.pk]), self.draft_data()).status_code, 403)

    def test_view_only_cannot_edit_or_see_completion_action(self):
        invoice = self.save_draft()
        self.unauthorized_user.user_permissions.set(Permission.objects.filter(content_type__app_label="sales", codename__in=("view_salesinvoice", "view_salesinvoiceline")))
        self.client.force_login(self.unauthorized_user)
        url = reverse("sales:pos-workspace", args=[invoice.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_edit"])
        self.assertFalse(response.context["can_complete"])
        self.assertNotContains(response, "Save &amp; review totals")
        self.assertEqual(self.client.post(url, self.draft_data()).status_code, 403)

    def test_registry_filters_pagination_and_exclusive_navigation(self):
        invoice = self.completed_invoice()
        SalesInvoice.objects.bulk_create([SalesInvoice(pharmacist=self.authorized_user, customer=self.customer, currency_code="USD") for _ in range(30)])
        url = reverse("sales:invoice-list")
        response = self.client.get(url)
        self.assertEqual(response.context["page_obj"].paginator.count, 31)
        self.assertEqual(len(response.context["invoices"]), 25)
        self.assertEqual(len(self.client.get(url, {"page": "2"}).context["invoices"]), 6)
        for params in ({"q": invoice.invoice_number}, {"status": "COMPLETED"}, {"period": "1"}):
            self.assertEqual(self.client.get(url, params).context["page_obj"].paginator.count, 1)
        self.assertEqual(self.client.get(url, {"payment_status": "PAID"}).context["page_obj"].paginator.count, 0)
        self.assertEqual(self.client.get(url, {"q": "Saved customer"}).context["page_obj"].paginator.count, 31)
        response = self.client.get(url, {"status": "DRAFT", "payment_status": "UNPAID"})
        self.assertContains(response, "status=DRAFT&amp;payment_status=UNPAID&amp;page=2")
        self.assertEqual(self.client.get(url, {"page": "bad"}).context["page_obj"].number, 1)
        self.assertEqual(self.client.get(url, {"page": "9999"}).context["page_obj"].number, 2)
        for route, active in ((url, "Invoices"), (reverse("sales:pos"), "Sales")):
            items = self.client.get(route).context["dashboard_navigation"]
            self.assertEqual([item["label"] for item in items if item["is_active"]], [active])
