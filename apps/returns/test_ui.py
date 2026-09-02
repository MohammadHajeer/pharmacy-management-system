from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Manufacturer, Medicine, MedicineUnit
from apps.core.models import PaymentMethod
from apps.inventory.models import MedicineBatch
from apps.parties.models import Customer, Supplier
from apps.purchasing.models import PurchaseInvoice
from apps.sales.models import SaleBatchAllocation, SalesInvoice, SalesInvoiceLine

from .models import CustomerRefund, CustomerReturn, ReturnStatus, SupplierReturn


class ReturnsUITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.user = user_model.objects.create_user(username="returns-ui")
        cls.denied = user_model.objects.create_user(username="returns-ui-denied")
        cls.user.user_permissions.set(
            Permission.objects.filter(content_type__app_label="returns")
        )
        category = Category.objects.create(name="Returns UI")
        manufacturer = Manufacturer.objects.create(name="Returns Labs")
        cls.medicine = Medicine.objects.create(
            name="Returned Medicine", category=category, manufacturer=manufacturer
        )
        cls.unit = MedicineUnit.objects.create(
            medicine=cls.medicine,
            name="Tablet",
            conversion_to_base=Decimal("1.000000"),
            is_base_unit=True,
        )
        cls.customer = Customer.objects.create(code="CUS-RET-UI", name="Return Patient")
        cls.supplier = Supplier.objects.create(code="SUP-RET-UI", name="Return Supplier")
        cls.batch = MedicineBatch.objects.create(
            medicine=cls.medicine,
            batch_number="RET-BATCH-001",
            expiry_date=timezone.localdate() + timedelta(days=180),
            acquisition_cost_per_base_unit=Decimal("2.0000"),
            quantity_available_base=Decimal("10.000"),
            first_received_at=timezone.now(),
        )
        cls.sale = SalesInvoice.objects.create(
            invoice_number="SAL-RET-UI",
            status=SalesInvoice.Status.COMPLETED,
            customer=cls.customer,
            pharmacist=cls.user,
            customer_name_snapshot=cls.customer.name,
            currency_code="USD",
            subtotal=Decimal("20.00"),
            grand_total=Decimal("20.00"),
            balance_due=Decimal("20.00"),
            completed_at=timezone.now(),
        )
        cls.sale_line = SalesInvoiceLine.objects.create(
            sales_invoice=cls.sale,
            medicine=cls.medicine,
            medicine_description_snapshot=cls.medicine.name,
            medicine_unit=cls.unit,
            unit_name_snapshot=cls.unit.name,
            quantity=Decimal("2.000"),
            conversion_to_base_snapshot=Decimal("1.000000"),
            requested_quantity_base=Decimal("2.000"),
            unit_price=Decimal("10.0000"),
            line_total=Decimal("20.00"),
        )
        SaleBatchAllocation.objects.create(
            sales_invoice_line=cls.sale_line,
            batch=cls.batch,
            allocated_quantity_base=Decimal("2.000"),
            acquisition_cost_snapshot=Decimal("2.0000"),
        )
        cls.purchase = PurchaseInvoice.objects.create(
            invoice_number="PUR-RET-UI",
            supplier=cls.supplier,
            invoice_date=date(2026, 8, 20),
            status=PurchaseInvoice.Status.POSTED,
            supplier_name_snapshot=cls.supplier.name,
            currency_code="USD",
            subtotal=Decimal("20.00"),
            grand_total=Decimal("20.00"),
            remaining_balance=Decimal("20.00"),
            created_by=cls.user,
            posted_by=cls.user,
            posted_at=timezone.now(),
        )
        cls.payment_method = PaymentMethod.objects.create(name="Cash")

    def customer_data(self, **overrides):
        data = {
            "sales_invoice": str(self.sale.pk),
            "reason": "Customer changed treatment",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-sales_invoice_line": str(self.sale_line.pk),
            "lines-0-batch": str(self.batch.pk),
            "lines-0-returned_quantity_base": "1.000",
            "lines-0-condition": "NON_RESELLABLE",
            "lines-0-refund_amount": "10.00",
        }
        data.update(overrides)
        return data

    def supplier_data(self):
        return {
            "supplier": str(self.supplier.pk),
            "purchase_invoice": str(self.purchase.pk),
            "reason": "Supplier quality return",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-medicine": str(self.medicine.pk),
            "lines-0-batch": str(self.batch.pk),
            "lines-0-returned_quantity_base": "1.000",
        }

    def test_registries_require_server_side_permissions_and_show_empty_state(self):
        self.assertEqual(self.client.get(reverse("returns:home")).status_code, 302)
        self.client.force_login(self.denied)
        self.assertEqual(self.client.get(reverse("returns:customer-return-list")).status_code, 403)
        self.client.force_login(self.user)
        self.assertContains(
            self.client.get(reverse("returns:customer-return-list")),
            "No customer returns found",
        )
        self.assertContains(
            self.client.get(reverse("returns:supplier-return-list")),
            "No supplier returns found",
        )

    def test_customer_create_post_detail_and_refund_workflow(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("returns:customer-return-create"), self.customer_data())
        customer_return = CustomerReturn.objects.get()
        self.assertRedirects(
            response,
            reverse("returns:customer-return-detail", args=[customer_return.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(customer_return.status, ReturnStatus.DRAFT)
        response = self.client.post(reverse("returns:customer-return-post", args=[customer_return.pk]))
        self.assertEqual(response.status_code, 302)
        customer_return.refresh_from_db()
        self.assertEqual(customer_return.status, ReturnStatus.POSTED)
        response = self.client.post(
            reverse("returns:customer-refund-create", args=[customer_return.pk]),
            {
                "payment_method": str(self.payment_method.pk),
                "amount": "6.00",
                "reference": "REF-UI",
                "refunded_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CustomerRefund.objects.get().amount, Decimal("6.00"))
        detail = self.client.get(reverse("returns:customer-return-detail", args=[customer_return.pk]))
        self.assertContains(detail, "REF-UI")

    def test_invalid_refund_service_error_is_rendered_without_write(self):
        self.client.force_login(self.user)
        self.client.post(reverse("returns:customer-return-create"), self.customer_data())
        customer_return = CustomerReturn.objects.get()
        self.client.post(reverse("returns:customer-return-post", args=[customer_return.pk]))
        response = self.client.post(
            reverse("returns:customer-refund-create", args=[customer_return.pk]),
            {
                "payment_method": str(self.payment_method.pk),
                "amount": "11.00",
                "reference": "",
                "refunded_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "eligible refundable amount", status_code=400)
        self.assertFalse(CustomerRefund.objects.exists())

    def test_supplier_create_and_post_deducts_through_inventory_service(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("returns:supplier-return-create"), self.supplier_data())
        supplier_return = SupplierReturn.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(supplier_return.status, ReturnStatus.DRAFT)
        before = self.batch.quantity_available_base
        response = self.client.post(reverse("returns:supplier-return-post", args=[supplier_return.pk]))
        self.assertEqual(response.status_code, 302)
        self.batch.refresh_from_db()
        supplier_return.refresh_from_db()
        self.assertEqual(self.batch.quantity_available_base, before - Decimal("1.000"))
        self.assertEqual(supplier_return.status, ReturnStatus.POSTED)

    def test_registry_filtering_and_invalid_status_are_deterministic(self):
        CustomerReturn.objects.create(
            return_number="CRT-FILTER-UI",
            sales_invoice=self.sale,
            customer=self.customer,
            reason="Filter fixture",
            processed_by=self.user,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("returns:customer-return-list"), {"q": "FILTER"})
        self.assertContains(response, "CRT-FILTER-UI")
        response = self.client.get(reverse("returns:customer-return-list"), {"status": "BAD"})
        self.assertEqual(list(response.context["customer_returns"]), [])
        self.assertContains(response, "status filter is invalid")
