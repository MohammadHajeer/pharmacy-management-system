from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Category, Manufacturer, Medicine, MedicineUnit
from apps.core.models import PaymentMethod
from apps.parties.models import Customer, Supplier
from apps.purchasing.models import PurchaseInvoice
from apps.returns.models import (
    CustomerRefund,
    CustomerReturn,
    RefundStatus,
    ReturnStatus,
    SupplierReturn,
)
from apps.sales.models import SalesInvoice, SalesInvoiceLine

from .models import CustomerPayment, PaymentStatus, SupplierPayment
from .queries import (
    customer_statement,
    search_purchase_invoices,
    search_sales_invoices,
    supplier_statement,
)


def _grant(user, app_label, codename):
    permission = Permission.objects.get(content_type__app_label=app_label, codename=codename)
    user.user_permissions.add(permission)


class _StatementFixtureMixin:
    @classmethod
    def _build_fixtures(cls):
        cls.pharmacist = get_user_model().objects.create_user(username="pharmacist-user")

        category = Category.objects.create(name="Pain relief")
        manufacturer = Manufacturer.objects.create(name="Example manufacturer")
        cls.medicine = Medicine.objects.create(
            name="Example tablet",
            category=category,
            manufacturer=manufacturer,
            default_selling_price=Decimal("10.0000"),
        )
        cls.unit = MedicineUnit.objects.create(
            medicine=cls.medicine,
            name="Tablet",
            conversion_to_base=Decimal("1.000000"),
            is_base_unit=True,
        )

        cls.payment_method = PaymentMethod.objects.create(code="CASH", name="Cash")

        cls.customer = Customer.objects.create(code="CUST-1", name="Jane Customer")
        cls.other_customer = Customer.objects.create(code="CUST-2", name="Amir Other")
        cls.supplier = Supplier.objects.create(code="SUPP-1", name="Acme Supplier")

        now = timezone.now()

        cls.sales_invoice = SalesInvoice.objects.create(
            invoice_number="SAL-STMT0001",
            status=SalesInvoice.Status.COMPLETED,
            customer=cls.customer,
            pharmacist=cls.pharmacist,
            currency_code="USD",
            subtotal=Decimal("100.00"),
            grand_total=Decimal("100.00"),
            paid_total=Decimal("40.00"),
            balance_due=Decimal("60.00"),
            payment_status=SalesInvoice.PaymentStatus.PARTIAL,
            completed_at=now - timedelta(days=5),
        )
        SalesInvoiceLine.objects.create(
            sales_invoice=cls.sales_invoice,
            medicine=cls.medicine,
            medicine_description_snapshot=cls.medicine.name,
            medicine_unit=cls.unit,
            unit_name_snapshot=cls.unit.name,
            quantity=Decimal("10.000"),
            conversion_to_base_snapshot=Decimal("1.000000"),
            requested_quantity_base=Decimal("10.000"),
            unit_price=Decimal("10.0000"),
            line_total=Decimal("100.00"),
        )

        cls.other_sales_invoice = SalesInvoice.objects.create(
            invoice_number="SAL-STMT0002",
            status=SalesInvoice.Status.COMPLETED,
            customer=cls.other_customer,
            pharmacist=cls.pharmacist,
            currency_code="USD",
            subtotal=Decimal("50.00"),
            grand_total=Decimal("50.00"),
            paid_total=Decimal("50.00"),
            balance_due=Decimal("0.00"),
            payment_status=SalesInvoice.PaymentStatus.PAID,
            completed_at=now - timedelta(days=3),
        )

        cls.customer_payment = CustomerPayment.objects.create(
            sales_invoice=cls.sales_invoice,
            customer=cls.customer,
            payment_method=cls.payment_method,
            amount=Decimal("40.00"),
            processed_by=cls.pharmacist,
            paid_at=now - timedelta(days=4),
            status=PaymentStatus.POSTED,
        )

        cls.customer_return = CustomerReturn.objects.create(
            return_number="CRT-STMT0001",
            sales_invoice=cls.sales_invoice,
            customer=cls.customer,
            reason="Damaged packaging",
            return_total=Decimal("10.00"),
            status=ReturnStatus.POSTED,
            processed_by=cls.pharmacist,
            posted_at=now - timedelta(days=2),
        )
        cls.customer_refund = CustomerRefund.objects.create(
            refund_number="CRF-STMT0001",
            customer_return=cls.customer_return,
            sales_invoice=cls.sales_invoice,
            payment_method=cls.payment_method,
            amount=Decimal("10.00"),
            processed_by=cls.pharmacist,
            refunded_at=now - timedelta(days=1),
            status=RefundStatus.POSTED,
        )

        cls.purchase_invoice = PurchaseInvoice.objects.create(
            invoice_number="PUR-STMT0001",
            supplier=cls.supplier,
            invoice_date=timezone.localdate() - timedelta(days=10),
            status=PurchaseInvoice.Status.POSTED,
            currency_code="USD",
            subtotal=Decimal("200.00"),
            grand_total=Decimal("200.00"),
            paid_total=Decimal("50.00"),
            remaining_balance=Decimal("150.00"),
            payment_status=PurchaseInvoice.PaymentStatus.PARTIAL,
            created_by=cls.pharmacist,
            posted_by=cls.pharmacist,
            posted_at=now - timedelta(days=9),
        )
        cls.supplier_payment = SupplierPayment.objects.create(
            purchase_invoice=cls.purchase_invoice,
            supplier=cls.supplier,
            payment_method=cls.payment_method,
            amount=Decimal("50.00"),
            processed_by=cls.pharmacist,
            paid_at=now - timedelta(days=8),
            status=PaymentStatus.POSTED,
        )
        cls.supplier_return = SupplierReturn.objects.create(
            return_number="SRT-STMT0001",
            supplier=cls.supplier,
            purchase_invoice=cls.purchase_invoice,
            reason="Expired stock",
            return_total=Decimal("20.00"),
            status=ReturnStatus.POSTED,
            processed_by=cls.pharmacist,
            posted_at=now - timedelta(days=7),
        )


class InvoiceSearchPermissionTests(_StatementFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._build_fixtures()
        cls.viewer = get_user_model().objects.create_user(username="sales-viewer")
        _grant(cls.viewer, "sales", "view_salesinvoice")
        cls.purchasing_viewer = get_user_model().objects.create_user(username="purchasing-viewer")
        _grant(cls.purchasing_viewer, "purchasing", "view_purchaseinvoice")
        cls.no_perms = get_user_model().objects.create_user(username="no-perms")

    def test_search_sales_invoices_requires_permission(self):
        with self.assertRaises(PermissionDenied):
            search_sales_invoices(actor=self.no_perms, query="")

    def test_search_sales_invoices_filters_by_query(self):
        results = search_sales_invoices(actor=self.viewer, query="STMT0001")
        self.assertEqual(list(results), [self.sales_invoice])

    def test_search_sales_invoices_filters_by_customer_and_status(self):
        results = search_sales_invoices(
            actor=self.viewer,
            customer=self.other_customer,
            status=SalesInvoice.Status.COMPLETED,
        )
        self.assertEqual(list(results), [self.other_sales_invoice])

    def test_search_purchase_invoices_requires_permission(self):
        with self.assertRaises(PermissionDenied):
            search_purchase_invoices(actor=self.no_perms, query="")

    def test_search_purchase_invoices_filters_by_query(self):
        results = search_purchase_invoices(actor=self.purchasing_viewer, query="STMT0001")
        self.assertEqual(list(results), [self.purchase_invoice])


class CustomerStatementTests(_StatementFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._build_fixtures()
        cls.viewer = get_user_model().objects.create_user(username="statement-viewer")
        _grant(cls.viewer, "parties", "view_customer")
        _grant(cls.viewer, "finance", "view_customerpayment")
        cls.missing_party_perm = get_user_model().objects.create_user(username="missing-party-perm")
        _grant(cls.missing_party_perm, "finance", "view_customerpayment")
        cls.missing_payment_perm = get_user_model().objects.create_user(username="missing-payment-perm")
        _grant(cls.missing_payment_perm, "parties", "view_customer")

    def test_requires_both_party_and_payment_permission(self):
        with self.assertRaises(PermissionDenied):
            customer_statement(actor=self.missing_party_perm, customer=self.customer)
        with self.assertRaises(PermissionDenied):
            customer_statement(actor=self.missing_payment_perm, customer=self.customer)

    def test_statement_applies_each_event_once_with_pharmacy_perspective_signs(self):
        entries, net_balance = customer_statement(actor=self.viewer, customer=self.customer)

        by_type = {entry.event_type: entry for entry in entries}
        self.assertEqual(set(by_type), {
            "SALES_INVOICE", "CUSTOMER_PAYMENT", "CUSTOMER_RETURN", "CUSTOMER_REFUND",
        })
        self.assertEqual(by_type["SALES_INVOICE"].amount, Decimal("100.00"))
        self.assertEqual(by_type["CUSTOMER_PAYMENT"].amount, Decimal("-40.00"))
        self.assertEqual(by_type["CUSTOMER_RETURN"].amount, Decimal("-10.00"))
        self.assertEqual(by_type["CUSTOMER_REFUND"].amount, Decimal("10.00"))

        # 100 - 40 - 10 + 10 = 60, matching the invoice's own balance_due
        # here, but derived independently through a separate code path.
        self.assertEqual(net_balance, Decimal("60.00"))
        self.assertEqual(entries[-1].running_balance, net_balance)

    def test_statement_is_chronologically_ordered(self):
        entries, _ = customer_statement(actor=self.viewer, customer=self.customer)
        occurred_ats = [entry.occurred_at for entry in entries]
        self.assertEqual(occurred_ats, sorted(occurred_ats))

    def test_statement_does_not_include_other_customers_events(self):
        entries, net_balance = customer_statement(actor=self.viewer, customer=self.other_customer)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].event_type, "SALES_INVOICE")
        self.assertEqual(net_balance, Decimal("50.00"))

    def test_statement_never_writes_back_to_invoice_balance(self):
        customer_statement(actor=self.viewer, customer=self.customer)
        self.sales_invoice.refresh_from_db()
        self.assertEqual(self.sales_invoice.balance_due, Decimal("60.00"))
        self.assertEqual(self.sales_invoice.paid_total, Decimal("40.00"))


class SupplierStatementTests(_StatementFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._build_fixtures()
        cls.viewer = get_user_model().objects.create_user(username="supplier-statement-viewer")
        _grant(cls.viewer, "parties", "view_supplier")
        _grant(cls.viewer, "finance", "view_supplierpayment")
        cls.no_perms = get_user_model().objects.create_user(username="no-perms-supplier")

    def test_requires_permission(self):
        with self.assertRaises(PermissionDenied):
            supplier_statement(actor=self.no_perms, supplier=self.supplier)

    def test_statement_applies_each_event_once_with_pharmacy_perspective_signs(self):
        entries, net_balance = supplier_statement(actor=self.viewer, supplier=self.supplier)

        by_type = {entry.event_type: entry for entry in entries}
        self.assertEqual(set(by_type), {
            "PURCHASE_INVOICE", "SUPPLIER_PAYMENT", "SUPPLIER_RETURN",
        })
        self.assertEqual(by_type["PURCHASE_INVOICE"].amount, Decimal("-200.00"))
        self.assertEqual(by_type["SUPPLIER_PAYMENT"].amount, Decimal("50.00"))
        self.assertEqual(by_type["SUPPLIER_RETURN"].amount, Decimal("20.00"))

        # -200 + 50 + 20 = -130: the pharmacy owes the supplier 130.
        self.assertEqual(net_balance, Decimal("-130.00"))
        self.assertEqual(entries[-1].running_balance, net_balance)

    def test_statement_never_writes_back_to_invoice_balance(self):
        supplier_statement(actor=self.viewer, supplier=self.supplier)
        self.purchase_invoice.refresh_from_db()
        self.assertEqual(self.purchase_invoice.remaining_balance, Decimal("150.00"))
