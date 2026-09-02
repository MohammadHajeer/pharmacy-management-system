import threading
from decimal import Decimal
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, connections
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.utils import timezone

from apps.catalog.models import Category, Manufacturer, Medicine
from apps.core.models import PaymentMethod
from apps.inventory.models import MedicineBatch, StockMovement
from apps.inventory.services import InsufficientStockError
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
from .services import create_draft_supplier_return, post_supplier_return


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


class SupplierReturnServiceTests(TestCase):
    """Covers PMS-16 (E2-T05): posting supplier returns against exact
    batches atomically with targeted row locks, per BRD 5.11."""

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
        batch = self._make_batch(quantity="20.000", cost="4.0000")

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
        # 5 base units * 4.0000 cost = 20.00
        self.assertEqual(line.line_total, Decimal("20.00"))
        self.assertEqual(supplier_return.return_total, Decimal("20.00"))
        # Posting has not touched inventory yet.
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
        batch = self._make_batch(quantity="20.000", cost="4.0000")
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

        posted = post_supplier_return(actor=self.actor, supplier_return_id=supplier_return.id)

        self.assertEqual(posted.status, ReturnStatus.POSTED)
        self.assertIsNotNone(posted.posted_at)

        batch.refresh_from_db()
        self.assertEqual(batch.quantity_available_base, Decimal("15.000"))

        line = posted.lines.get()
        movement = StockMovement.objects.get(source_line_id=line.id)
        self.assertEqual(movement.movement_type, StockMovement.MovementType.SUPPLIER_RETURN)
        self.assertEqual(movement.quantity_delta_base, Decimal("-5.000"))
        self.assertEqual(movement.source_type, "SUPPLIER_RETURN")
        self.assertEqual(movement.source_id, posted.id)
        self.assertEqual(movement.reference_number, posted.return_number)

    def test_post_supplier_return_two_lines_same_batch_accumulate_deduction(self):
        batch = self._make_batch(quantity="20.000", cost="4.0000")
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
            StockMovement.objects.filter(source_id=supplier_return.id).count(), 2
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
            post_supplier_return(actor=self.actor, supplier_return_id=supplier_return.id)

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
                    # Only 2.000 available on this batch.
                    "returned_quantity_base": Decimal("3.000"),
                },
            ],
        )

        with self.assertRaises(InsufficientStockError):
            post_supplier_return(actor=self.actor, supplier_return_id=supplier_return.id)

        supplier_return.refresh_from_db()
        self.assertEqual(supplier_return.status, ReturnStatus.DRAFT)
        first_batch.refresh_from_db()
        second_batch.refresh_from_db()
        # The first line's deduction must be rolled back along with the second.
        self.assertEqual(first_batch.quantity_available_base, Decimal("5.000"))
        self.assertEqual(second_batch.quantity_available_base, Decimal("2.000"))
        self.assertFalse(StockMovement.objects.filter(source_id=supplier_return.id).exists())

    def test_post_supplier_return_rejects_tampered_total(self):
        batch = self._make_batch(quantity="20.000", cost="4.0000")
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
            post_supplier_return(actor=self.actor, supplier_return_id=supplier_return.id)

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
                actor=unauthorized_actor, supplier_return_id=supplier_return.id
            )


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locks are required.")
class ConcurrentSupplierReturnTests(TransactionTestCase):
    """Proves targeted batch locking prevents two concurrent supplier-return
    postings from oversubscribing the same batch (BRD 8 targeted locking;
    PMS-16 acceptance criterion 5: over-return and rollback paths tested)."""

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
                try:
                    post_supplier_return(
                        actor=self.actor, supplier_return_id=supplier_return_id
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
            SupplierReturn.objects.filter(status=ReturnStatus.POSTED).count(), 1
        )
