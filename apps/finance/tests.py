import threading
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied
from django.db import connections, models
from django.db.models import NOT_PROVIDED
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.utils import timezone

from apps.catalog.models import Category, Manufacturer, Medicine, MedicineUnit
from apps.core.models import PaymentMethod
from apps.parties.models import Customer, Supplier
from apps.purchasing.models import PurchaseInvoice, PurchaseInvoiceLine
from apps.sales.models import SalesInvoice, SalesInvoiceLine

from .forms import CustomerPaymentForm, SupplierPaymentForm
from .models import CustomerPayment, PaymentStatus, SupplierPayment
from .services import (
    post_customer_payment,
    post_supplier_payment,
    reverse_customer_payment,
    reverse_supplier_payment,
)


class PaymentStatusTests(SimpleTestCase):
    def test_payment_statuses_are_minimal_phase_one_states(self):
        self.assertEqual(set(PaymentStatus.values), {"POSTED", "REVERSED"})

    def test_supplier_payment_reversal_fields_match_phase_one_schema(self):
        status = SupplierPayment._meta.get_field("status")
        reversed_by = SupplierPayment._meta.get_field("reversed_by")
        reversed_at = SupplierPayment._meta.get_field("reversed_at")
        reversal_reason = SupplierPayment._meta.get_field("reversal_reason")

        self.assertIsInstance(status, models.CharField)
        self.assertEqual(status.max_length, 10)
        self.assertEqual(status.default, PaymentStatus.POSTED)
        self.assertFalse(status.null)
        self.assertFalse(status.blank)

        self.assertIsInstance(reversed_by, models.ForeignKey)
        self.assertEqual(reversed_by.remote_field.model._meta.label, settings.AUTH_USER_MODEL)
        self.assertIs(reversed_by.remote_field.on_delete, models.PROTECT)
        self.assertTrue(reversed_by.null)
        self.assertTrue(reversed_by.blank)
        self.assertIs(reversed_by.default, NOT_PROVIDED)

        self.assertIsInstance(reversed_at, models.DateTimeField)
        self.assertTrue(reversed_at.null)
        self.assertTrue(reversed_at.blank)
        self.assertIs(reversed_at.default, NOT_PROVIDED)

        self.assertIsInstance(reversal_reason, models.TextField)
        self.assertFalse(reversal_reason.null)
        self.assertTrue(reversal_reason.blank)
        self.assertIs(reversal_reason.default, NOT_PROVIDED)


class FinancialReportPermissionTests(TestCase):
    def test_permission_is_attached_to_customer_payment_content_type(self):
        permission = Permission.objects.get(
            content_type__app_label="finance",
            codename="view_financial_reports",
        )

        self.assertEqual(permission.content_type.model, "customerpayment")


def _grant(user, codename):
    permission = Permission.objects.get(content_type__app_label="finance", codename=codename)
    user.user_permissions.add(permission)


class _FinanceFixtureMixin:
    """Shared Phase 1 fixtures: one completed sales invoice with a balance
    and one posted purchase invoice with a balance, plus users with/without
    the finance posting permissions."""

    @classmethod
    def _build_fixtures(cls):
        cls.finance_user = get_user_model().objects.create_user(username="finance-user")
        _grant(cls.finance_user, "post_customerpayment")
        _grant(cls.finance_user, "post_supplierpayment")

        cls.unauthorized_user = get_user_model().objects.create_user(username="no-perms-user")

        cls.pharmacist = get_user_model().objects.create_user(username="pharmacist-user")

        category = Category.objects.create(name="Pain relief")
        manufacturer = Manufacturer.objects.create(name="Example manufacturer")
        medicine = Medicine.objects.create(
            name="Example tablet",
            category=category,
            manufacturer=manufacturer,
            default_selling_price=Decimal("10.0000"),
        )
        unit = MedicineUnit.objects.create(
            medicine=medicine,
            name="Tablet",
            conversion_to_base=Decimal("1.000000"),
            is_base_unit=True,
        )

        cls.payment_method = PaymentMethod.objects.create(
            code="CASH",
            name="Cash",
            requires_reference=False,
        )
        cls.reference_payment_method = PaymentMethod.objects.create(
            code="TRANSFER",
            name="Bank transfer",
            requires_reference=True,
        )

        cls.customer = Customer.objects.create(code="CUST-1", name="Jane Customer")
        cls.supplier = Supplier.objects.create(code="SUPP-1", name="Acme Supplier")

        cls.sales_invoice = SalesInvoice.objects.create(
            invoice_number="SAL-TEST0001",
            status=SalesInvoice.Status.COMPLETED,
            customer=cls.customer,
            pharmacist=cls.pharmacist,
            currency_code="USD",
            subtotal=Decimal("100.00"),
            grand_total=Decimal("100.00"),
            paid_total=Decimal("0.00"),
            balance_due=Decimal("100.00"),
            payment_status=SalesInvoice.PaymentStatus.UNPAID,
            completed_at=timezone.now(),
        )
        SalesInvoiceLine.objects.create(
            sales_invoice=cls.sales_invoice,
            medicine=medicine,
            medicine_description_snapshot=medicine.name,
            medicine_unit=unit,
            unit_name_snapshot=unit.name,
            quantity=Decimal("10.000"),
            conversion_to_base_snapshot=Decimal("1.000000"),
            requested_quantity_base=Decimal("10.000"),
            unit_price=Decimal("10.0000"),
            line_total=Decimal("100.00"),
        )

        cls.purchase_invoice = PurchaseInvoice.objects.create(
            invoice_number="PUR-TEST0001",
            supplier=cls.supplier,
            invoice_date=timezone.localdate(),
            status=PurchaseInvoice.Status.POSTED,
            currency_code="USD",
            subtotal=Decimal("200.00"),
            grand_total=Decimal("200.00"),
            paid_total=Decimal("0.00"),
            remaining_balance=Decimal("200.00"),
            payment_status=PurchaseInvoice.PaymentStatus.UNPAID,
            created_by=cls.pharmacist,
            posted_by=cls.pharmacist,
            posted_at=timezone.now(),
        )
        PurchaseInvoiceLine.objects.create(
            purchase_invoice=cls.purchase_invoice,
            medicine=medicine,
            medicine_description_snapshot=medicine.name,
            medicine_unit=unit,
            unit_name_snapshot=unit.name,
            quantity=Decimal("20.000"),
            conversion_to_base_snapshot=Decimal("1.000000"),
            received_quantity_base=Decimal("20.000"),
            unit_cost=Decimal("10.0000"),
            line_total=Decimal("200.00"),
            batch_number="BATCH-1",
            expiry_date=timezone.localdate() + timedelta(days=365),
        )


class CustomerPaymentServiceTests(_FinanceFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._build_fixtures()

    def _payment_data(self, **overrides):
        data = {
            "payment_method": str(self.payment_method.pk),
            "amount": "40.00",
            "reference": "",
            "paid_at": timezone.now().isoformat(),
        }
        data.update(overrides)
        return data

    def test_anonymous_or_unauthorized_actor_is_denied(self):
        with self.assertRaises(PermissionDenied):
            post_customer_payment(
                actor=AnonymousUser(),
                sales_invoice=self.sales_invoice,
                data=self._payment_data(),
            )
        with self.assertRaises(PermissionDenied):
            post_customer_payment(
                actor=self.unauthorized_user,
                sales_invoice=self.sales_invoice,
                data=self._payment_data(),
            )

    def test_post_partial_payment_updates_invoice_balance_and_status(self):
        form, payment = post_customer_payment(
            actor=self.finance_user,
            sales_invoice=self.sales_invoice,
            data=self._payment_data(amount="40.00"),
        )

        self.assertIsNotNone(payment)
        self.assertEqual(payment.status, PaymentStatus.POSTED)
        self.assertEqual(payment.customer_id, self.customer.pk)
        self.assertEqual(payment.processed_by_id, self.finance_user.pk)

        self.sales_invoice.refresh_from_db()
        self.assertEqual(self.sales_invoice.paid_total, Decimal("40.00"))
        self.assertEqual(self.sales_invoice.balance_due, Decimal("60.00"))
        self.assertEqual(self.sales_invoice.payment_status, SalesInvoice.PaymentStatus.PARTIAL)

    def test_multiple_payments_settle_invoice_without_overpayment(self):
        post_customer_payment(
            actor=self.finance_user,
            sales_invoice=self.sales_invoice,
            data=self._payment_data(amount="60.00"),
        )
        form, payment = post_customer_payment(
            actor=self.finance_user,
            sales_invoice=self.sales_invoice,
            data=self._payment_data(amount="40.00"),
        )

        self.assertIsNotNone(payment)
        self.sales_invoice.refresh_from_db()
        self.assertEqual(self.sales_invoice.paid_total, Decimal("100.00"))
        self.assertEqual(self.sales_invoice.balance_due, Decimal("0.00"))
        self.assertEqual(self.sales_invoice.payment_status, SalesInvoice.PaymentStatus.PAID)

    def test_payment_exceeding_balance_is_rejected(self):
        post_customer_payment(
            actor=self.finance_user,
            sales_invoice=self.sales_invoice,
            data=self._payment_data(amount="80.00"),
        )
        form, payment = post_customer_payment(
            actor=self.finance_user,
            sales_invoice=self.sales_invoice,
            data=self._payment_data(amount="30.00"),
        )

        self.assertIsNone(payment)
        self.assertIn("amount", form.errors)
        self.sales_invoice.refresh_from_db()
        self.assertEqual(self.sales_invoice.paid_total, Decimal("80.00"))
        self.assertEqual(CustomerPayment.objects.count(), 1)

    def test_payment_method_requiring_reference_without_one_is_rejected(self):
        form, payment = post_customer_payment(
            actor=self.finance_user,
            sales_invoice=self.sales_invoice,
            data=self._payment_data(
                payment_method=str(self.reference_payment_method.pk),
                reference="",
            ),
        )

        self.assertIsNone(payment)
        self.assertIn("reference", form.errors)

    def test_zero_or_negative_amount_is_rejected(self):
        form, payment = post_customer_payment(
            actor=self.finance_user,
            sales_invoice=self.sales_invoice,
            data=self._payment_data(amount="0.00"),
        )
        self.assertIsNone(payment)
        self.assertIn("amount", form.errors)

    def test_payment_against_non_completed_invoice_is_rejected(self):
        draft_invoice = SalesInvoice.objects.create(
            status=SalesInvoice.Status.DRAFT,
            pharmacist=self.pharmacist,
            currency_code="USD",
        )

        form, payment = post_customer_payment(
            actor=self.finance_user,
            sales_invoice=draft_invoice,
            data=self._payment_data(amount="10.00"),
        )

        self.assertIsNone(payment)

    def test_reverse_payment_records_metadata_and_restores_balance(self):
        _, payment = post_customer_payment(
            actor=self.finance_user,
            sales_invoice=self.sales_invoice,
            data=self._payment_data(amount="100.00"),
        )
        self.sales_invoice.refresh_from_db()
        self.assertEqual(self.sales_invoice.payment_status, SalesInvoice.PaymentStatus.PAID)

        form, reversed_payment = reverse_customer_payment(
            actor=self.finance_user,
            payment=payment,
            data={"reversal_reason": "Customer disputed the charge."},
        )

        self.assertIsNotNone(reversed_payment)
        self.assertEqual(reversed_payment.status, PaymentStatus.REVERSED)
        self.assertEqual(reversed_payment.reversed_by_id, self.finance_user.pk)
        self.assertIsNotNone(reversed_payment.reversed_at)
        self.assertEqual(reversed_payment.reversal_reason, "Customer disputed the charge.")
        self.assertEqual(reversed_payment.amount, Decimal("100.00"))

        self.sales_invoice.refresh_from_db()
        self.assertEqual(self.sales_invoice.paid_total, Decimal("0.00"))
        self.assertEqual(self.sales_invoice.balance_due, Decimal("100.00"))
        self.assertEqual(self.sales_invoice.payment_status, SalesInvoice.PaymentStatus.UNPAID)

    def test_reversing_an_already_reversed_payment_is_rejected(self):
        _, payment = post_customer_payment(
            actor=self.finance_user,
            sales_invoice=self.sales_invoice,
            data=self._payment_data(amount="50.00"),
        )
        reverse_customer_payment(actor=self.finance_user, payment=payment)

        form, result = reverse_customer_payment(actor=self.finance_user, payment=payment)

        self.assertIsNone(result)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.REVERSED)

    def test_reversal_requires_permission(self):
        _, payment = post_customer_payment(
            actor=self.finance_user,
            sales_invoice=self.sales_invoice,
            data=self._payment_data(amount="20.00"),
        )
        with self.assertRaises(PermissionDenied):
            reverse_customer_payment(actor=self.unauthorized_user, payment=payment)


class SupplierPaymentServiceTests(_FinanceFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._build_fixtures()

    def _payment_data(self, **overrides):
        data = {
            "payment_method": str(self.payment_method.pk),
            "amount": "80.00",
            "reference": "",
            "paid_at": timezone.now().isoformat(),
        }
        data.update(overrides)
        return data

    def test_anonymous_or_unauthorized_actor_is_denied(self):
        with self.assertRaises(PermissionDenied):
            post_supplier_payment(
                actor=AnonymousUser(),
                purchase_invoice=self.purchase_invoice,
                data=self._payment_data(),
            )
        with self.assertRaises(PermissionDenied):
            post_supplier_payment(
                actor=self.unauthorized_user,
                purchase_invoice=self.purchase_invoice,
                data=self._payment_data(),
            )

    def test_post_partial_payment_updates_invoice_balance_and_status(self):
        form, payment = post_supplier_payment(
            actor=self.finance_user,
            purchase_invoice=self.purchase_invoice,
            data=self._payment_data(amount="80.00"),
        )

        self.assertIsNotNone(payment)
        self.assertEqual(payment.supplier_id, self.supplier.pk)
        self.assertEqual(payment.processed_by_id, self.finance_user.pk)

        self.purchase_invoice.refresh_from_db()
        self.assertEqual(self.purchase_invoice.paid_total, Decimal("80.00"))
        self.assertEqual(self.purchase_invoice.remaining_balance, Decimal("120.00"))
        self.assertEqual(
            self.purchase_invoice.payment_status, PurchaseInvoice.PaymentStatus.PARTIAL
        )

    def test_multiple_payments_settle_invoice_without_overpayment(self):
        post_supplier_payment(
            actor=self.finance_user,
            purchase_invoice=self.purchase_invoice,
            data=self._payment_data(amount="150.00"),
        )
        form, payment = post_supplier_payment(
            actor=self.finance_user,
            purchase_invoice=self.purchase_invoice,
            data=self._payment_data(amount="50.00"),
        )

        self.assertIsNotNone(payment)
        self.purchase_invoice.refresh_from_db()
        self.assertEqual(self.purchase_invoice.paid_total, Decimal("200.00"))
        self.assertEqual(self.purchase_invoice.remaining_balance, Decimal("0.00"))
        self.assertEqual(
            self.purchase_invoice.payment_status, PurchaseInvoice.PaymentStatus.PAID
        )

    def test_payment_exceeding_balance_is_rejected(self):
        post_supplier_payment(
            actor=self.finance_user,
            purchase_invoice=self.purchase_invoice,
            data=self._payment_data(amount="150.00"),
        )
        form, payment = post_supplier_payment(
            actor=self.finance_user,
            purchase_invoice=self.purchase_invoice,
            data=self._payment_data(amount="60.00"),
        )

        self.assertIsNone(payment)
        self.assertIn("amount", form.errors)
        self.purchase_invoice.refresh_from_db()
        self.assertEqual(self.purchase_invoice.paid_total, Decimal("150.00"))
        self.assertEqual(SupplierPayment.objects.count(), 1)

    def test_payment_against_non_posted_invoice_is_rejected(self):
        draft_invoice = PurchaseInvoice.objects.create(
            status=PurchaseInvoice.Status.DRAFT,
            supplier=self.supplier,
            invoice_date=timezone.localdate(),
            currency_code="USD",
            created_by=self.pharmacist,
        )

        form, payment = post_supplier_payment(
            actor=self.finance_user,
            purchase_invoice=draft_invoice,
            data=self._payment_data(amount="10.00"),
        )

        self.assertIsNone(payment)

    def test_reverse_payment_records_metadata_and_restores_balance(self):
        _, payment = post_supplier_payment(
            actor=self.finance_user,
            purchase_invoice=self.purchase_invoice,
            data=self._payment_data(amount="200.00"),
        )
        self.purchase_invoice.refresh_from_db()
        self.assertEqual(
            self.purchase_invoice.payment_status, PurchaseInvoice.PaymentStatus.PAID
        )

        form, reversed_payment = reverse_supplier_payment(
            actor=self.finance_user,
            payment=payment,
            data={"reversal_reason": "Duplicate bank transfer."},
        )

        self.assertIsNotNone(reversed_payment)
        self.assertEqual(reversed_payment.status, PaymentStatus.REVERSED)
        self.assertEqual(reversed_payment.reversed_by_id, self.finance_user.pk)
        self.assertIsNotNone(reversed_payment.reversed_at)
        self.assertEqual(reversed_payment.reversal_reason, "Duplicate bank transfer.")

        self.purchase_invoice.refresh_from_db()
        self.assertEqual(self.purchase_invoice.paid_total, Decimal("0.00"))
        self.assertEqual(self.purchase_invoice.remaining_balance, Decimal("200.00"))
        self.assertEqual(
            self.purchase_invoice.payment_status, PurchaseInvoice.PaymentStatus.UNPAID
        )

    def test_reversing_an_already_reversed_payment_is_rejected(self):
        _, payment = post_supplier_payment(
            actor=self.finance_user,
            purchase_invoice=self.purchase_invoice,
            data=self._payment_data(amount="100.00"),
        )
        reverse_supplier_payment(actor=self.finance_user, payment=payment)

        form, result = reverse_supplier_payment(actor=self.finance_user, payment=payment)

        self.assertIsNone(result)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.REVERSED)


class PaymentFormTests(TestCase):
    """ModelForm validation runs Model.validate_constraints(), which issues
    a DB query (Django >= 4.1), so these need a real test database rather
    than SimpleTestCase."""

    def test_customer_payment_form_rejects_non_positive_amount(self):
        form = CustomerPaymentForm(
            data={
                "amount": "-5.00",
                "reference": "",
                "paid_at": timezone.now().isoformat(),
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("amount", form.errors)

    def test_supplier_payment_form_requires_payment_method(self):
        form = SupplierPaymentForm(
            data={
                "amount": "10.00",
                "reference": "",
                "paid_at": timezone.now().isoformat(),
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("payment_method", form.errors)


class ConcurrentCustomerPaymentTests(TransactionTestCase):
    """Proves concurrent posting cannot push an invoice past its balance
    (BRD 8 targeted invoice locking; acceptance criterion 6)."""

    def setUp(self):
        self.finance_user = get_user_model().objects.create_user(username="finance-concurrent")
        _grant(self.finance_user, "post_customerpayment")

        self.pharmacist = get_user_model().objects.create_user(username="pharmacist-concurrent")
        category = Category.objects.create(name="Pain relief")
        manufacturer = Manufacturer.objects.create(name="Example manufacturer")
        medicine = Medicine.objects.create(
            name="Example tablet",
            category=category,
            manufacturer=manufacturer,
            default_selling_price=Decimal("10.0000"),
        )
        unit = MedicineUnit.objects.create(
            medicine=medicine,
            name="Tablet",
            conversion_to_base=Decimal("1.000000"),
            is_base_unit=True,
        )
        self.payment_method = PaymentMethod.objects.create(code="CASH", name="Cash")
        self.customer = Customer.objects.create(code="CUST-CC", name="Concurrent Customer")
        self.sales_invoice = SalesInvoice.objects.create(
            invoice_number="SAL-CONC0001",
            status=SalesInvoice.Status.COMPLETED,
            customer=self.customer,
            pharmacist=self.pharmacist,
            currency_code="USD",
            subtotal=Decimal("100.00"),
            grand_total=Decimal("100.00"),
            paid_total=Decimal("0.00"),
            balance_due=Decimal("100.00"),
            payment_status=SalesInvoice.PaymentStatus.UNPAID,
            completed_at=timezone.now(),
        )
        SalesInvoiceLine.objects.create(
            sales_invoice=self.sales_invoice,
            medicine=medicine,
            medicine_description_snapshot=medicine.name,
            medicine_unit=unit,
            unit_name_snapshot=unit.name,
            quantity=Decimal("10.000"),
            conversion_to_base_snapshot=Decimal("1.000000"),
            requested_quantity_base=Decimal("10.000"),
            unit_price=Decimal("10.0000"),
            line_total=Decimal("100.00"),
        )

    def test_two_full_balance_payments_cannot_both_post(self):
        outcomes = []
        barrier = threading.Barrier(2)

        def attempt():
            try:
                barrier.wait(timeout=5)
                _, payment = post_customer_payment(
                    actor=self.finance_user,
                    sales_invoice=self.sales_invoice,
                    data={
                        "payment_method": str(self.payment_method.pk),
                        "amount": "100.00",
                        "reference": "",
                        "paid_at": timezone.now().isoformat(),
                    },
                )
                outcomes.append(payment is not None)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sum(1 for outcome in outcomes if outcome), 1)

        self.sales_invoice.refresh_from_db()
        self.assertEqual(self.sales_invoice.paid_total, Decimal("100.00"))
        self.assertEqual(self.sales_invoice.balance_due, Decimal("0.00"))
        self.assertEqual(
            CustomerPayment.objects.filter(status=PaymentStatus.POSTED).count(), 1
        )
