import threading
from datetime import timedelta
from decimal import Decimal
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, connections
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.utils import timezone

from apps.catalog.models import Category, Manufacturer, Medicine, MedicineUnit
from apps.core.models import PaymentMethod
from apps.inventory.models import MedicineBatch, StockMovement
from apps.inventory.services import InsufficientStockError
from apps.parties.models import Customer, Supplier
from apps.purchasing.models import PurchaseInvoice
from apps.sales.models import SaleBatchAllocation, SalesInvoice, SalesInvoiceLine

from .forms import CustomerRefundForm
from .models import (
    CustomerRefund,
    CustomerReturn,
    CustomerReturnLine,
    RefundStatus,
    ReturnStatus,
    SupplierReturn,
)
from .services import (
    create_customer_return,
    create_draft_supplier_return,
    post_customer_return,
    post_supplier_return,
    process_customer_refund,
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


def _grant(user, codename):
    permission = Permission.objects.get(content_type__app_label="returns", codename=codename)
    user.user_permissions.add(permission)


class _CustomerReturnsFixtureMixin:
    """Shared Phase 1 fixtures: one completed sales invoice with a single
    fully-allocated batch line, plus users with/without the returns
    permissions."""

    @classmethod
    def _build_fixtures(cls):
        cls.returns_user = get_user_model().objects.create_user(username="returns-service-user")
        _grant(cls.returns_user, "add_customerreturn")
        _grant(cls.returns_user, "post_customerreturn")
        _grant(cls.returns_user, "process_refund")

        cls.unauthorized_user = get_user_model().objects.create_user(username="returns-no-perms")
        cls.pharmacist = get_user_model().objects.create_user(username="returns-pharmacist")

        category = Category.objects.create(name="Pain relief - returns")
        manufacturer = Manufacturer.objects.create(name="Returns manufacturer")
        cls.medicine = Medicine.objects.create(
            name="Returns tablet",
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

        cls.payment_method = PaymentMethod.objects.create(
            code="CASH-RET", name="Cash", requires_reference=False
        )
        cls.customer = Customer.objects.create(code="CUS-RET", name="Returns Customer")
        cls.other_customer = Customer.objects.create(code="CUS-RET-2", name="Other Customer")

        cls.batch = MedicineBatch.objects.create(
            medicine=cls.medicine,
            batch_number="BATCH-RET-1",
            expiry_date=timezone.localdate() + timedelta(days=365),
            acquisition_cost_per_base_unit=Decimal("5.0000"),
            quantity_available_base=Decimal("90.000"),
            first_received_at=timezone.now(),
        )
        cls.expired_batch = MedicineBatch.objects.create(
            medicine=cls.medicine,
            batch_number="BATCH-RET-EXPIRED",
            expiry_date=timezone.localdate() - timedelta(days=1),
            acquisition_cost_per_base_unit=Decimal("5.0000"),
            quantity_available_base=Decimal("50.000"),
            first_received_at=timezone.now(),
        )

        cls.sales_invoice = SalesInvoice.objects.create(
            invoice_number="SAL-RET0001",
            status=SalesInvoice.Status.COMPLETED,
            customer=cls.customer,
            pharmacist=cls.pharmacist,
            currency_code="USD",
            subtotal=Decimal("100.00"),
            grand_total=Decimal("100.00"),
            paid_total=Decimal("100.00"),
            balance_due=Decimal("0.00"),
            payment_status=SalesInvoice.PaymentStatus.PAID,
            completed_at=timezone.now(),
        )
        cls.sales_invoice_line = SalesInvoiceLine.objects.create(
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
        cls.allocation = SaleBatchAllocation.objects.create(
            sales_invoice_line=cls.sales_invoice_line,
            batch=cls.batch,
            allocated_quantity_base=Decimal("10.000"),
            acquisition_cost_snapshot=Decimal("5.0000"),
        )

        # A second, unrelated completed sale — used to prove a return line
        # cannot reference a sales line/batch pair from a different sale.
        cls.other_sales_invoice = SalesInvoice.objects.create(
            invoice_number="SAL-RET0002",
            status=SalesInvoice.Status.COMPLETED,
            customer=cls.other_customer,
            pharmacist=cls.pharmacist,
            currency_code="USD",
            subtotal=Decimal("50.00"),
            grand_total=Decimal("50.00"),
            paid_total=Decimal("50.00"),
            balance_due=Decimal("0.00"),
            payment_status=SalesInvoice.PaymentStatus.PAID,
            completed_at=timezone.now(),
        )
        cls.other_sales_invoice_line = SalesInvoiceLine.objects.create(
            sales_invoice=cls.other_sales_invoice,
            medicine=cls.medicine,
            medicine_description_snapshot=cls.medicine.name,
            medicine_unit=cls.unit,
            unit_name_snapshot=cls.unit.name,
            quantity=Decimal("5.000"),
            conversion_to_base_snapshot=Decimal("1.000000"),
            requested_quantity_base=Decimal("5.000"),
            unit_price=Decimal("10.0000"),
            line_total=Decimal("50.00"),
        )

    def _return_line(self, *, quantity="4.000", refund="40.00", restock=True,
                      condition=CustomerReturnLine.Condition.RESELLABLE,
                      sales_invoice_line=None, batch=None):
        return {
            "sales_invoice_line": sales_invoice_line or self.sales_invoice_line,
            "batch": batch or self.batch,
            "returned_quantity_base": Decimal(quantity),
            "condition": condition,
            "restock": restock,
            "refund_amount": Decimal(refund),
        }

    def _create_draft_return(self, *, lines_data=None, actor=None):
        return create_customer_return(
            actor=actor or self.returns_user,
            sales_invoice=self.sales_invoice,
            reason="Customer changed their mind",
            lines_data=lines_data if lines_data is not None else [self._return_line()],
        )

    def _refund_data(self, **overrides):
        data = {
            "payment_method": str(self.payment_method.pk),
            "amount": "40.00",
            "reference": "",
            "refunded_at": timezone.now().isoformat(),
        }
        data.update(overrides)
        return data


class CreateCustomerReturnServiceTests(_CustomerReturnsFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._build_fixtures()

    def test_anonymous_or_unauthorized_actor_is_denied(self):
        with self.assertRaises(PermissionDenied):
            create_customer_return(
                actor=AnonymousUser(),
                sales_invoice=self.sales_invoice,
                reason="No permission",
                lines_data=[self._return_line()],
            )
        with self.assertRaises(PermissionDenied):
            create_customer_return(
                actor=self.unauthorized_user,
                sales_invoice=self.sales_invoice,
                reason="No permission",
                lines_data=[self._return_line()],
            )

    def test_create_assigns_number_draft_status_and_total(self):
        customer_return = self._create_draft_return()

        self.assertEqual(customer_return.status, ReturnStatus.DRAFT)
        self.assertTrue(customer_return.return_number)
        self.assertEqual(customer_return.customer_id, self.customer.pk)
        self.assertEqual(customer_return.return_total, Decimal("40.00"))
        self.assertEqual(customer_return.lines.count(), 1)
        self.assertIsNone(customer_return.posted_at)

    def test_create_requires_completed_sale(self):
        self.sales_invoice.status = SalesInvoice.Status.DRAFT
        self.sales_invoice.save(update_fields=["status"])
        try:
            with self.assertRaises(ValidationError):
                self._create_draft_return()
        finally:
            self.sales_invoice.status = SalesInvoice.Status.COMPLETED
            self.sales_invoice.save(update_fields=["status"])

    def test_create_rejects_line_from_a_different_sales_invoice(self):
        with self.assertRaises(ValidationError):
            self._create_draft_return(
                lines_data=[
                    self._return_line(sales_invoice_line=self.other_sales_invoice_line)
                ]
            )

    def test_create_rejects_batch_not_allocated_to_the_sales_line(self):
        with self.assertRaises(ValidationError):
            self._create_draft_return(
                lines_data=[self._return_line(batch=self.expired_batch)]
            )

    def test_create_requires_at_least_one_line(self):
        with self.assertRaises(ValidationError):
            self._create_draft_return(lines_data=[])


class PostCustomerReturnServiceTests(_CustomerReturnsFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._build_fixtures()

    def test_anonymous_or_unauthorized_actor_is_denied(self):
        customer_return = self._create_draft_return()
        with self.assertRaises(PermissionDenied):
            post_customer_return(actor=AnonymousUser(), customer_return=customer_return)
        with self.assertRaises(PermissionDenied):
            post_customer_return(actor=self.unauthorized_user, customer_return=customer_return)

    def test_post_restocks_resellable_nonexpired_line(self):
        customer_return = self._create_draft_return()
        starting_quantity = self.batch.quantity_available_base

        posted = post_customer_return(actor=self.returns_user, customer_return=customer_return)

        self.assertEqual(posted.status, ReturnStatus.POSTED)
        self.assertIsNotNone(posted.posted_at)

        self.batch.refresh_from_db()
        self.assertEqual(
            self.batch.quantity_available_base, starting_quantity + Decimal("4.000")
        )

        line = posted.lines.get()
        movement = StockMovement.objects.get(
            movement_type=StockMovement.MovementType.CUSTOMER_RETURN_RESTOCK,
            source_id=posted.id,
            source_line_id=line.id,
        )
        self.assertEqual(movement.quantity_delta_base, Decimal("4.000"))
        self.assertEqual(movement.batch_id, self.batch.pk)
        self.assertEqual(movement.reference_number, posted.return_number)

    def test_post_does_not_restock_non_resellable_line(self):
        customer_return = self._create_draft_return(
            lines_data=[
                self._return_line(
                    condition=CustomerReturnLine.Condition.NON_RESELLABLE,
                    restock=False,
                )
            ]
        )
        starting_quantity = self.batch.quantity_available_base

        posted = post_customer_return(actor=self.returns_user, customer_return=customer_return)

        self.assertEqual(posted.status, ReturnStatus.POSTED)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available_base, starting_quantity)
        self.assertFalse(
            StockMovement.objects.filter(
                movement_type=StockMovement.MovementType.CUSTOMER_RETURN_RESTOCK,
                source_id=posted.id,
            ).exists()
        )

    def test_post_rejects_a_non_draft_return(self):
        customer_return = self._create_draft_return()
        post_customer_return(actor=self.returns_user, customer_return=customer_return)

        with self.assertRaises(ValidationError):
            post_customer_return(actor=self.returns_user, customer_return=customer_return)

    def test_post_rejects_cumulative_quantity_exceeding_original_allocation(self):
        first_return = self._create_draft_return(
            lines_data=[self._return_line(quantity="6.000", refund="60.00")]
        )
        second_return = self._create_draft_return(
            lines_data=[self._return_line(quantity="6.000", refund="60.00")]
        )

        post_customer_return(actor=self.returns_user, customer_return=first_return)

        with self.assertRaises(ValidationError):
            post_customer_return(actor=self.returns_user, customer_return=second_return)

        second_return.refresh_from_db()
        self.assertEqual(second_return.status, ReturnStatus.DRAFT)
        self.assertFalse(
            StockMovement.objects.filter(source_id=second_return.id).exists()
        )

    def test_post_aggregates_duplicate_current_lines_for_quantity_cap(self):
        customer_return = self._create_draft_return(
            lines_data=[
                self._return_line(quantity="6.000", refund="30.00"),
                self._return_line(quantity="6.000", refund="30.00"),
            ]
        )

        with self.assertRaises(ValidationError):
            post_customer_return(
                actor=self.returns_user,
                customer_return=customer_return,
            )

        customer_return.refresh_from_db()
        self.assertEqual(customer_return.status, ReturnStatus.DRAFT)
        self.assertFalse(StockMovement.objects.filter(source_id=customer_return.id).exists())

    def test_post_rejects_cumulative_refund_value_exceeding_original_line_total(self):
        first_return = self._create_draft_return(
            lines_data=[self._return_line(quantity="4.000", refund="70.00")]
        )
        second_return = self._create_draft_return(
            lines_data=[self._return_line(quantity="4.000", refund="70.00")]
        )

        post_customer_return(actor=self.returns_user, customer_return=first_return)

        with self.assertRaises(ValidationError):
            post_customer_return(actor=self.returns_user, customer_return=second_return)

        second_return.refresh_from_db()
        self.assertEqual(second_return.status, ReturnStatus.DRAFT)

    def test_post_aggregates_duplicate_current_lines_for_value_cap(self):
        customer_return = self._create_draft_return(
            lines_data=[
                self._return_line(quantity="4.000", refund="60.00"),
                self._return_line(quantity="4.000", refund="60.00"),
            ]
        )

        with self.assertRaises(ValidationError):
            post_customer_return(
                actor=self.returns_user,
                customer_return=customer_return,
            )

        customer_return.refresh_from_db()
        self.assertEqual(customer_return.status, ReturnStatus.DRAFT)

    def test_post_rejects_restocking_an_expired_batch_and_rolls_back_all_lines(self):
        # A second, still-valid batch line is posted alongside the expired
        # one to prove that when posting fails, nothing already validated
        # for an earlier line is written either (acceptance criterion 5).
        # Both lines reference the same sales invoice (a return cannot span
        # invoices), but different sales invoice lines/batches, mirroring a
        # sale that was originally filled from two batches.
        second_batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            batch_number="BATCH-RET-2",
            expiry_date=timezone.localdate() + timedelta(days=365),
            acquisition_cost_per_base_unit=Decimal("5.0000"),
            quantity_available_base=Decimal("20.000"),
            first_received_at=timezone.now(),
        )
        second_line = SalesInvoiceLine.objects.create(
            sales_invoice=self.sales_invoice,
            medicine=self.medicine,
            medicine_description_snapshot=self.medicine.name,
            medicine_unit=self.unit,
            unit_name_snapshot=self.unit.name,
            quantity=Decimal("3.000"),
            conversion_to_base_snapshot=Decimal("1.000000"),
            requested_quantity_base=Decimal("3.000"),
            unit_price=Decimal("10.0000"),
            line_total=Decimal("30.00"),
        )
        SaleBatchAllocation.objects.create(
            sales_invoice_line=second_line,
            batch=second_batch,
            allocated_quantity_base=Decimal("3.000"),
            acquisition_cost_snapshot=Decimal("5.0000"),
        )
        third_line = SalesInvoiceLine.objects.create(
            sales_invoice=self.sales_invoice,
            medicine=self.medicine,
            medicine_description_snapshot=self.medicine.name,
            medicine_unit=self.unit,
            unit_name_snapshot=self.unit.name,
            quantity=Decimal("3.000"),
            conversion_to_base_snapshot=Decimal("1.000000"),
            requested_quantity_base=Decimal("3.000"),
            unit_price=Decimal("10.0000"),
            line_total=Decimal("30.00"),
        )
        SaleBatchAllocation.objects.create(
            sales_invoice_line=third_line,
            batch=self.expired_batch,
            allocated_quantity_base=Decimal("3.000"),
            acquisition_cost_snapshot=Decimal("5.0000"),
        )

        customer_return = self._create_draft_return(
            lines_data=[
                self._return_line(
                    quantity="2.000",
                    refund="20.00",
                    batch=second_batch,
                    sales_invoice_line=second_line,
                ),
                self._return_line(
                    quantity="2.000",
                    refund="20.00",
                    batch=self.expired_batch,
                    sales_invoice_line=third_line,
                ),
            ]
        )
        second_batch_starting_quantity = second_batch.quantity_available_base
        expired_batch_starting_quantity = self.expired_batch.quantity_available_base

        with self.assertRaises(ValidationError):
            post_customer_return(actor=self.returns_user, customer_return=customer_return)

        customer_return.refresh_from_db()
        second_batch.refresh_from_db()
        self.expired_batch.refresh_from_db()

        self.assertEqual(customer_return.status, ReturnStatus.DRAFT)
        self.assertEqual(second_batch.quantity_available_base, second_batch_starting_quantity)
        self.assertEqual(
            self.expired_batch.quantity_available_base, expired_batch_starting_quantity
        )
        self.assertFalse(StockMovement.objects.filter(source_id=customer_return.id).exists())

    def test_post_does_not_change_original_invoice_totals(self):
        customer_return = self._create_draft_return()
        post_customer_return(actor=self.returns_user, customer_return=customer_return)

        self.sales_invoice.refresh_from_db()
        self.assertEqual(self.sales_invoice.grand_total, Decimal("100.00"))
        self.assertEqual(self.sales_invoice.paid_total, Decimal("100.00"))
        self.assertEqual(self.sales_invoice.balance_due, Decimal("0.00"))


class ProcessCustomerRefundServiceTests(_CustomerReturnsFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._build_fixtures()

    def _posted_return(self):
        customer_return = self._create_draft_return()
        return post_customer_return(actor=self.returns_user, customer_return=customer_return)

    def test_anonymous_or_unauthorized_actor_is_denied(self):
        customer_return = self._posted_return()
        with self.assertRaises(PermissionDenied):
            process_customer_refund(
                actor=AnonymousUser(),
                customer_return=customer_return,
                data=self._refund_data(),
            )
        with self.assertRaises(PermissionDenied):
            process_customer_refund(
                actor=self.unauthorized_user,
                customer_return=customer_return,
                data=self._refund_data(),
            )

    def test_process_refund_creates_a_posted_separate_record(self):
        customer_return = self._posted_return()

        form, refund = process_customer_refund(
            actor=self.returns_user,
            customer_return=customer_return,
            data=self._refund_data(amount="40.00"),
        )

        self.assertIsNotNone(refund)
        self.assertEqual(refund.status, RefundStatus.POSTED)
        self.assertEqual(refund.amount, Decimal("40.00"))
        self.assertEqual(refund.customer_return_id, customer_return.pk)
        self.assertEqual(refund.sales_invoice_id, self.sales_invoice.pk)
        self.assertEqual(refund.processed_by_id, self.returns_user.pk)
        self.assertTrue(refund.refund_number)

    def test_process_refund_rejects_amount_over_the_eligible_remaining_amount(self):
        customer_return = self._posted_return()

        form, refund = process_customer_refund(
            actor=self.returns_user,
            customer_return=customer_return,
            data=self._refund_data(amount="45.00"),
        )

        self.assertIsNone(refund)
        self.assertIn("amount", form.errors)

    def test_process_refund_rejects_on_a_draft_return(self):
        customer_return = self._create_draft_return()

        form, refund = process_customer_refund(
            actor=self.returns_user,
            customer_return=customer_return,
            data=self._refund_data(amount="10.00"),
        )

        self.assertIsNone(refund)
        self.assertTrue(form.non_field_errors())

    def test_process_refund_tracks_cumulative_amount_across_multiple_refunds(self):
        customer_return = self._posted_return()

        _, first_refund = process_customer_refund(
            actor=self.returns_user,
            customer_return=customer_return,
            data=self._refund_data(amount="25.00"),
        )
        self.assertIsNotNone(first_refund)

        _, second_refund = process_customer_refund(
            actor=self.returns_user,
            customer_return=customer_return,
            data=self._refund_data(amount="15.00"),
        )
        self.assertIsNotNone(second_refund)

        form, third_refund = process_customer_refund(
            actor=self.returns_user,
            customer_return=customer_return,
            data=self._refund_data(amount="0.01"),
        )
        self.assertIsNone(third_refund)
        self.assertIn("amount", form.errors)

    def test_process_refund_does_not_touch_original_invoice(self):
        customer_return = self._posted_return()
        process_customer_refund(
            actor=self.returns_user,
            customer_return=customer_return,
            data=self._refund_data(amount="40.00"),
        )

        self.sales_invoice.refresh_from_db()
        self.assertEqual(self.sales_invoice.grand_total, Decimal("100.00"))
        self.assertEqual(self.sales_invoice.paid_total, Decimal("100.00"))
        self.assertEqual(self.sales_invoice.balance_due, Decimal("0.00"))


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locks are required.")
class ConcurrentCustomerReturnPostingTests(_CustomerReturnsFixtureMixin, TransactionTestCase):
    """Two threads try to post the same draft return at once. The row lock
    on the CustomerReturn must ensure exactly one of them posts it and
    restocks the batch exactly once."""

    def setUp(self):
        super().setUp()
        self._build_fixtures()

    def test_only_one_concurrent_post_succeeds(self):
        customer_return = self._create_draft_return()
        starting_quantity = self.batch.quantity_available_base

        outcomes = []
        barrier = threading.Barrier(2)

        def attempt():
            try:
                barrier.wait(timeout=5)
                post_customer_return(actor=self.returns_user, customer_return=customer_return)
                outcomes.append("posted")
            except ValidationError:
                outcomes.append("rejected")
            except Exception as error:  # pragma: no cover - asserted below
                outcomes.append(f"unexpected:{type(error).__name__}:{error}")
            finally:
                connections.close_all()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertCountEqual(outcomes, ["posted", "rejected"])

        customer_return.refresh_from_db()
        self.batch.refresh_from_db()
        self.assertEqual(customer_return.status, ReturnStatus.POSTED)
        self.assertEqual(
            self.batch.quantity_available_base, starting_quantity + Decimal("4.000")
        )
        self.assertEqual(
            StockMovement.objects.filter(source_id=customer_return.id).count(), 1
        )

    def test_different_batches_share_the_sales_line_refund_cap(self):
        self.allocation.allocated_quantity_base = Decimal("5.000")
        self.allocation.save(update_fields=["allocated_quantity_base"])
        second_batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            batch_number="BATCH-RET-CONCURRENT-2",
            expiry_date=timezone.localdate() + timedelta(days=365),
            acquisition_cost_per_base_unit=Decimal("5.0000"),
            quantity_available_base=Decimal("90.000"),
            first_received_at=timezone.now(),
        )
        SaleBatchAllocation.objects.create(
            sales_invoice_line=self.sales_invoice_line,
            batch=second_batch,
            allocated_quantity_base=Decimal("5.000"),
            acquisition_cost_snapshot=Decimal("5.0000"),
        )
        returns = [
            self._create_draft_return(
                lines_data=[
                    self._return_line(
                        quantity="5.000",
                        refund="70.00",
                        restock=False,
                        batch=batch,
                    )
                ]
            )
            for batch in (self.batch, second_batch)
        ]

        outcomes = []
        barrier = threading.Barrier(2)

        def attempt(customer_return):
            try:
                barrier.wait(timeout=5)
                post_customer_return(
                    actor=self.returns_user,
                    customer_return=customer_return,
                )
                outcomes.append("posted")
            except ValidationError:
                outcomes.append("rejected")
            except Exception as error:  # pragma: no cover - asserted below
                outcomes.append(f"unexpected:{type(error).__name__}:{error}")
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=attempt, args=(customer_return,))
            for customer_return in returns
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertCountEqual(outcomes, ["posted", "rejected"])
        self.assertEqual(
            CustomerReturn.objects.filter(status=ReturnStatus.POSTED).count(),
            1,
        )


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locks are required.")
class ConcurrentCustomerRefundTests(_CustomerReturnsFixtureMixin, TransactionTestCase):
    """Two refund requests, each individually within the return total but
    together exceeding it, are posted concurrently. The row lock on the
    CustomerReturn must ensure only one succeeds."""

    def setUp(self):
        super().setUp()
        self._build_fixtures()

    def test_only_one_concurrent_refund_fits_the_eligible_amount(self):
        customer_return = self._create_draft_return()
        customer_return = post_customer_return(
            actor=self.returns_user, customer_return=customer_return
        )

        outcomes = []
        barrier = threading.Barrier(2)

        def attempt():
            try:
                barrier.wait(timeout=5)
                _, refund = process_customer_refund(
                    actor=self.returns_user,
                    customer_return=customer_return,
                    data=self._refund_data(amount="30.00"),
                )
                outcomes.append("posted" if refund is not None else "rejected")
            except Exception as error:  # pragma: no cover - asserted below
                outcomes.append(f"unexpected:{type(error).__name__}:{error}")
            finally:
                connections.close_all()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertCountEqual(outcomes, ["posted", "rejected"])

        total_refunded = sum(
            (refund.amount for refund in CustomerRefund.objects.filter(customer_return=customer_return)),
            Decimal("0.00"),
        )
        self.assertLessEqual(total_refunded, customer_return.return_total)


class SupplierReturnServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = get_user_model().objects.create_user(username="returns-actor")
        _grant(cls.actor, "add_supplierreturn")
        _grant(cls.actor, "post_supplierreturn")
        cls.supplier = Supplier.objects.create(code="SUP-RT", name="Returns supplier")
        category = Category.objects.create(name="Returns category")
        manufacturer = Manufacturer.objects.create(name="Returns manufacturer")
        cls.medicine = Medicine.objects.create(
            name="Returns medicine",
            category=category,
            manufacturer=manufacturer,
            default_selling_price=Decimal("5.00"),
        )

    def _make_batch(self, *, batch_number="SRB-1", quantity="20.000", cost="4.0000"):
        return MedicineBatch.objects.create(
            medicine=self.medicine,
            batch_number=batch_number,
            expiry_date=timezone.localdate() + timezone.timedelta(days=180),
            acquisition_cost_per_base_unit=Decimal(cost),
            quantity_available_base=Decimal(quantity),
            first_received_at=timezone.now(),
            is_active=True,
        )

    def test_create_draft_snapshots_batch_cost_and_computes_totals(self):
        batch = self._make_batch()
        supplier_return = create_draft_supplier_return(
            actor=self.actor,
            supplier=self.supplier,
            reason="Damaged on arrival",
            lines_data=[
                {
                    "medicine": self.medicine,
                    "batch": batch,
                    "returned_quantity_base": Decimal("5.000"),
                }
            ],
        )

        self.assertEqual(supplier_return.status, ReturnStatus.DRAFT)
        self.assertTrue(supplier_return.return_number.startswith("SRT-"))
        line = supplier_return.lines.get()
        self.assertEqual(line.unit_cost_snapshot, Decimal("4.0000"))
        self.assertEqual(line.line_total, Decimal("20.00"))
        self.assertEqual(supplier_return.return_total, Decimal("20.00"))
        batch.refresh_from_db()
        self.assertEqual(batch.quantity_available_base, Decimal("20.000"))

    def test_create_draft_requires_active_supplier(self):
        self.supplier.is_active = False
        self.supplier.save(update_fields=["is_active"])
        batch = self._make_batch()

        with self.assertRaises(ValidationError):
            create_draft_supplier_return(
                actor=self.actor,
                supplier=self.supplier,
                reason="Damaged",
                lines_data=[
                    {
                        "medicine": self.medicine,
                        "batch": batch,
                        "returned_quantity_base": Decimal("1.000"),
                    }
                ],
            )

    def test_post_supplier_return_deducts_exact_batch_and_records_movement(self):
        batch = self._make_batch()
        supplier_return = create_draft_supplier_return(
            actor=self.actor,
            supplier=self.supplier,
            reason="Damaged on arrival",
            lines_data=[
                {
                    "medicine": self.medicine,
                    "batch": batch,
                    "returned_quantity_base": Decimal("5.000"),
                }
            ],
        )

        posted = post_supplier_return(
            actor=self.actor,
            supplier_return_id=supplier_return.id,
        )

        self.assertEqual(posted.status, ReturnStatus.POSTED)
        self.assertIsNotNone(posted.posted_at)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity_available_base, Decimal("15.000"))
        line = posted.lines.get()
        movement = StockMovement.objects.get(source_line_id=line.id)
        self.assertEqual(
            movement.movement_type,
            StockMovement.MovementType.SUPPLIER_RETURN,
        )
        self.assertEqual(movement.quantity_delta_base, Decimal("-5.000"))
        self.assertEqual(movement.source_type, "SUPPLIER_RETURN")
        self.assertEqual(movement.source_id, posted.id)
        self.assertEqual(movement.reference_number, posted.return_number)

    def test_post_supplier_return_two_lines_same_batch_accumulate_deduction(self):
        batch = self._make_batch()
        supplier_return = create_draft_supplier_return(
            actor=self.actor,
            supplier=self.supplier,
            reason="Two lines, one batch",
            lines_data=[
                {
                    "medicine": self.medicine,
                    "batch": batch,
                    "returned_quantity_base": Decimal("6.000"),
                },
                {
                    "medicine": self.medicine,
                    "batch": batch,
                    "returned_quantity_base": Decimal("4.000"),
                },
            ],
        )

        post_supplier_return(actor=self.actor, supplier_return_id=supplier_return.id)

        batch.refresh_from_db()
        self.assertEqual(batch.quantity_available_base, Decimal("10.000"))
        self.assertEqual(
            StockMovement.objects.filter(source_id=supplier_return.id).count(),
            2,
        )

    def test_post_supplier_return_rejects_a_non_draft_return(self):
        batch = self._make_batch()
        supplier_return = create_draft_supplier_return(
            actor=self.actor,
            supplier=self.supplier,
            reason="Damaged",
            lines_data=[
                {
                    "medicine": self.medicine,
                    "batch": batch,
                    "returned_quantity_base": Decimal("1.000"),
                }
            ],
        )
        post_supplier_return(actor=self.actor, supplier_return_id=supplier_return.id)

        with self.assertRaises(ValidationError):
            post_supplier_return(
                actor=self.actor,
                supplier_return_id=supplier_return.id,
            )

    def test_post_supplier_return_rejects_over_return_and_rolls_back_everything(self):
        first_batch = self._make_batch(batch_number="SRB-OVER-1", quantity="5.000")
        second_batch = self._make_batch(batch_number="SRB-OVER-2", quantity="2.000")
        supplier_return = create_draft_supplier_return(
            actor=self.actor,
            supplier=self.supplier,
            reason="Over-return attempt",
            lines_data=[
                {
                    "medicine": self.medicine,
                    "batch": first_batch,
                    "returned_quantity_base": Decimal("5.000"),
                },
                {
                    "medicine": self.medicine,
                    "batch": second_batch,
                    "returned_quantity_base": Decimal("3.000"),
                },
            ],
        )

        with self.assertRaises(InsufficientStockError):
            post_supplier_return(
                actor=self.actor,
                supplier_return_id=supplier_return.id,
            )

        supplier_return.refresh_from_db()
        self.assertEqual(supplier_return.status, ReturnStatus.DRAFT)
        first_batch.refresh_from_db()
        second_batch.refresh_from_db()
        self.assertEqual(first_batch.quantity_available_base, Decimal("5.000"))
        self.assertEqual(second_batch.quantity_available_base, Decimal("2.000"))
        self.assertFalse(
            StockMovement.objects.filter(source_id=supplier_return.id).exists()
        )

    def test_post_supplier_return_rejects_tampered_total(self):
        batch = self._make_batch()
        supplier_return = create_draft_supplier_return(
            actor=self.actor,
            supplier=self.supplier,
            reason="Damaged",
            lines_data=[
                {
                    "medicine": self.medicine,
                    "batch": batch,
                    "returned_quantity_base": Decimal("5.000"),
                }
            ],
        )
        SupplierReturn.objects.filter(pk=supplier_return.pk).update(
            return_total=Decimal("999.99")
        )

        with self.assertRaises(ValidationError):
            post_supplier_return(
                actor=self.actor,
                supplier_return_id=supplier_return.id,
            )

        batch.refresh_from_db()
        self.assertEqual(batch.quantity_available_base, Decimal("20.000"))

    def test_post_supplier_return_rechecks_permission_after_creation(self):
        batch = self._make_batch()
        supplier_return = create_draft_supplier_return(
            actor=self.actor,
            supplier=self.supplier,
            reason="Damaged",
            lines_data=[
                {
                    "medicine": self.medicine,
                    "batch": batch,
                    "returned_quantity_base": Decimal("1.000"),
                }
            ],
        )
        unauthorized_actor = get_user_model().objects.create_user(
            username="unauthorized-returns-user"
        )

        with self.assertRaises(PermissionDenied):
            post_supplier_return(
                actor=unauthorized_actor,
                supplier_return_id=supplier_return.id,
            )


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locks are required.")
class ConcurrentSupplierReturnTests(TransactionTestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user(username="returns-concurrent")
        _grant(self.actor, "add_supplierreturn")
        _grant(self.actor, "post_supplierreturn")
        self.supplier = Supplier.objects.create(code="SUP-CC", name="Concurrent supplier")
        category = Category.objects.create(name="Concurrent category")
        manufacturer = Manufacturer.objects.create(name="Concurrent manufacturer")
        self.medicine = Medicine.objects.create(
            name="Concurrent medicine",
            category=category,
            manufacturer=manufacturer,
            default_selling_price=Decimal("5.00"),
        )
        self.batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            batch_number="SRB-CONC",
            expiry_date=timezone.localdate() + timezone.timedelta(days=180),
            acquisition_cost_per_base_unit=Decimal("4.0000"),
            quantity_available_base=Decimal("10.000"),
            first_received_at=timezone.now(),
            is_active=True,
        )

    def test_two_full_batch_returns_cannot_both_post(self):
        returns = [
            create_draft_supplier_return(
                actor=self.actor,
                supplier=self.supplier,
                reason=f"Concurrent return {index}",
                lines_data=[
                    {
                        "medicine": self.medicine,
                        "batch": self.batch,
                        "returned_quantity_base": Decimal("10.000"),
                    }
                ],
            )
            for index in range(2)
        ]
        outcomes = []
        barrier = threading.Barrier(2)

        def attempt(supplier_return_id):
            try:
                barrier.wait(timeout=5)
                post_supplier_return(
                    actor=self.actor,
                    supplier_return_id=supplier_return_id,
                )
                outcomes.append("posted")
            except InsufficientStockError:
                outcomes.append("insufficient")
            except Exception as error:  # pragma: no cover - asserted below
                outcomes.append(f"unexpected:{type(error).__name__}:{error}")
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=attempt, args=(supplier_return.id,))
            for supplier_return in returns
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertCountEqual(outcomes, ["posted", "insufficient"])
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available_base, Decimal("0.000"))
        self.assertEqual(
            SupplierReturn.objects.filter(status=ReturnStatus.POSTED).count(),
            1,
        )
