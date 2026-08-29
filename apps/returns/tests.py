from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.models import PaymentMethod
from apps.parties.models import Customer, Supplier
from apps.purchasing.models import PurchaseInvoice
from apps.sales.models import SalesInvoice

from .models import (
    CustomerRefund,
    CustomerReturn,
    CustomerReturnLine,
    RefundStatus,
    ReturnStatus,
    SupplierReturn,
)


class ReturnChoiceTests(SimpleTestCase):
    def test_return_and_refund_states_match_phase_one(self):
        self.assertEqual(set(ReturnStatus.values), {"DRAFT", "POSTED", "VOID"})
        self.assertEqual(set(RefundStatus.values), {"POSTED"})
        self.assertEqual(CustomerRefund._meta.get_field("status").default, "POSTED")
        self.assertIn(
            "returns_customer_refund_posted_only",
            {constraint.name for constraint in CustomerRefund._meta.constraints},
        )

    def test_return_conditions_match_phase_one(self):
        self.assertEqual(
            set(CustomerReturnLine.Condition.values),
            {"RESELLABLE", "NON_RESELLABLE"},
        )


class ReturnBalanceIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="returns-user")
        cls.customer = Customer.objects.create(code="CUS-1", name="Customer")
        cls.supplier = Supplier.objects.create(code="SUP-1", name="Supplier")
        cls.payment_method = PaymentMethod.objects.create(code="CASH", name="Cash")

    def test_customer_refund_does_not_rewrite_original_sales_invoice_balance(self):
        invoice = SalesInvoice.objects.create(
            invoice_number="SAL-HISTORY",
            status=SalesInvoice.Status.COMPLETED,
            customer=self.customer,
            pharmacist=self.user,
            currency_code="USD",
            subtotal=Decimal("100.00"),
            grand_total=Decimal("100.00"),
            paid_total=Decimal("100.00"),
            balance_due=Decimal("0.00"),
            payment_status=SalesInvoice.PaymentStatus.PAID,
            completed_at=timezone.now(),
        )
        customer_return = CustomerReturn.objects.create(
            return_number="CRT-HISTORY",
            sales_invoice=invoice,
            customer=self.customer,
            reason="Returned item",
            return_total=Decimal("20.00"),
            status=ReturnStatus.POSTED,
            processed_by=self.user,
            posted_at=timezone.now(),
        )
        CustomerRefund.objects.create(
            refund_number="CRF-HISTORY",
            customer_return=customer_return,
            sales_invoice=invoice,
            payment_method=self.payment_method,
            amount=Decimal("20.00"),
            processed_by=self.user,
            refunded_at=timezone.now(),
        )

        invoice.refresh_from_db()
        self.assertEqual(invoice.grand_total, Decimal("100.00"))
        self.assertEqual(invoice.paid_total, Decimal("100.00"))
        self.assertEqual(invoice.balance_due, Decimal("0.00"))

    def test_supplier_return_does_not_rewrite_original_purchase_invoice_balance(self):
        invoice = PurchaseInvoice.objects.create(
            invoice_number="PUR-HISTORY",
            supplier=self.supplier,
            invoice_date=timezone.localdate(),
            status=PurchaseInvoice.Status.POSTED,
            payment_status=PurchaseInvoice.PaymentStatus.PARTIAL,
            currency_code="USD",
            subtotal=Decimal("100.00"),
            grand_total=Decimal("100.00"),
            paid_total=Decimal("40.00"),
            remaining_balance=Decimal("60.00"),
            created_by=self.user,
            posted_by=self.user,
            posted_at=timezone.now(),
        )
        SupplierReturn.objects.create(
            return_number="SRT-HISTORY",
            supplier=self.supplier,
            purchase_invoice=invoice,
            reason="Supplier return",
            return_total=Decimal("20.00"),
            status=ReturnStatus.POSTED,
            processed_by=self.user,
            posted_at=timezone.now(),
        )

        invoice.refresh_from_db()
        self.assertEqual(invoice.grand_total, Decimal("100.00"))
        self.assertEqual(invoice.paid_total, Decimal("40.00"))
        self.assertEqual(invoice.remaining_balance, Decimal("60.00"))
