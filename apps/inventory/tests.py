import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.catalog.models import Category, Manufacturer, Medicine

from .models import MedicineBatch, StockMovement
from .services import (
    InsufficientStockError,
    InvalidStockOperationError,
    deduct_stock_fefo,
    deduct_supplier_return,
    receive_purchase_stock,
    restock_customer_return,
)


class StockMovementChoiceTests(SimpleTestCase):
    def test_phase_one_movement_types_are_present(self):
        self.assertEqual(
            set(StockMovement.MovementType.values),
            {
                "PURCHASE_RECEIPT",
                "SALE",
                "CUSTOMER_RETURN_RESTOCK",
                "SUPPLIER_RETURN",
                "MANUAL_ADJUSTMENT_IN",
                "MANUAL_ADJUSTMENT_OUT",
            },
        )


class StockMovementSourceConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name="Inventory category")
        manufacturer = Manufacturer.objects.create(name="Inventory manufacturer")
        cls.medicine = Medicine.objects.create(
            name="Inventory medicine",
            category=category,
            manufacturer=manufacturer,
        )
        cls.batch = MedicineBatch.objects.create(
            medicine=cls.medicine,
            batch_number="INV-BATCH-1",
            expiry_date=timezone.localdate() + timedelta(days=365),
            acquisition_cost_per_base_unit=Decimal("0.5000"),
            quantity_available_base=Decimal("10.000"),
            first_received_at=timezone.now(),
        )
        cls.user = get_user_model().objects.create_user(username="movement-user")

    def movement_values(self, **overrides):
        values = {
            "medicine": self.medicine,
            "batch": self.batch,
            "movement_type": StockMovement.MovementType.SALE,
            "quantity_delta_base": Decimal("-1.000"),
            "source_type": "SALE",
            "source_id": uuid.uuid4(),
            "source_line_id": uuid.uuid4(),
            "performed_by": self.user,
            "occurred_at": timezone.now(),
        }
        values.update(overrides)
        return values

    def test_duplicate_authoritative_source_line_is_rejected(self):
        values = self.movement_values()
        StockMovement.objects.create(**values)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StockMovement.objects.create(**values)

    def test_source_less_manual_movements_are_not_globally_unique(self):
        values = self.movement_values(
            movement_type=StockMovement.MovementType.MANUAL_ADJUSTMENT_IN,
            quantity_delta_base=Decimal("1.000"),
            source_type="MANUAL_ADJUSTMENT_IN",
            source_line_id=None,
        )
        StockMovement.objects.create(**values)
        StockMovement.objects.create(**values)

        self.assertEqual(
            StockMovement.objects.filter(
                movement_type=StockMovement.MovementType.MANUAL_ADJUSTMENT_IN,
                source_id=values["source_id"],
            ).count(),
            2,
        )


class InventoryServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name="Service category")
        manufacturer = Manufacturer.objects.create(name="Service manufacturer")
        cls.medicine = Medicine.objects.create(
            name="Service medicine",
            category=category,
            manufacturer=manufacturer,
        )
        cls.user = get_user_model().objects.create_user(username="service-user")

    def test_receive_purchase_stock_creates_new_batch_and_movement(self):
        batch = receive_purchase_stock(
            actor=self.user,
            medicine=self.medicine,
            batch_number="BATCH-A",
            expiry_date=timezone.localdate() + timedelta(days=90),
            acquisition_cost_per_base_unit=Decimal("1.5000"),
            quantity_base=Decimal("10.000"),
            source_type="PURCHASE_RECEIPT",
            source_id=uuid.uuid4(),
            source_line_id=uuid.uuid4(),
            reference_number="PUR-RECEIPT-A",
        )

        self.assertEqual(batch.quantity_available_base, Decimal("10.000"))
        self.assertEqual(
            StockMovement.objects.filter(
                batch=batch, movement_type=StockMovement.MovementType.PURCHASE_RECEIPT
            ).count(),
            1,
        )

    def test_receive_purchase_stock_increases_existing_cost_layer(self):
        expiry_date = timezone.localdate() + timedelta(days=90)
        first_source_line = uuid.uuid4()
        receive_purchase_stock(
            actor=self.user,
            medicine=self.medicine,
            batch_number="BATCH-B",
            expiry_date=expiry_date,
            acquisition_cost_per_base_unit=Decimal("2.0000"),
            quantity_base=Decimal("5.000"),
            source_type="PURCHASE_RECEIPT",
            source_id=uuid.uuid4(),
            source_line_id=first_source_line,
            reference_number="PUR-RECEIPT-B1",
        )
        batch = receive_purchase_stock(
            actor=self.user,
            medicine=self.medicine,
            batch_number="BATCH-B",
            expiry_date=expiry_date,
            acquisition_cost_per_base_unit=Decimal("2.0000"),
            quantity_base=Decimal("3.000"),
            source_type="PURCHASE_RECEIPT",
            source_id=uuid.uuid4(),
            source_line_id=uuid.uuid4(),
            reference_number="PUR-RECEIPT-B2",
        )

        self.assertEqual(
            MedicineBatch.objects.filter(
                medicine=self.medicine, batch_number="BATCH-B"
            ).count(),
            1,
        )
        self.assertEqual(batch.quantity_available_base, Decimal("8.000"))

    def test_deduct_stock_fefo_uses_earliest_expiry_first(self):
        earlier_batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            batch_number="EARLY",
            expiry_date=timezone.localdate() + timedelta(days=10),
            acquisition_cost_per_base_unit=Decimal("1.0000"),
            quantity_available_base=Decimal("5.000"),
            first_received_at=timezone.now() - timedelta(days=5),
        )
        later_batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            batch_number="LATE",
            expiry_date=timezone.localdate() + timedelta(days=100),
            acquisition_cost_per_base_unit=Decimal("1.0000"),
            quantity_available_base=Decimal("5.000"),
            first_received_at=timezone.now(),
        )

        allocations = deduct_stock_fefo(
            actor=self.user,
            medicine=self.medicine,
            quantity_base=Decimal("7.000"),
            source_type="SALE",
            source_id=uuid.uuid4(),
            source_line_id_factory=lambda allocation: uuid.uuid4(),
            reference_number="SAL-FEFO-1",
        )

        earlier_batch.refresh_from_db()
        later_batch.refresh_from_db()
        self.assertEqual(earlier_batch.quantity_available_base, Decimal("0.000"))
        self.assertEqual(later_batch.quantity_available_base, Decimal("3.000"))
        self.assertEqual(len(allocations), 2)
        self.assertEqual(allocations[0].batch.pk, earlier_batch.pk)
        sale_movements = StockMovement.objects.filter(
            movement_type=StockMovement.MovementType.SALE,
            reference_number="SAL-FEFO-1",
        )
        self.assertEqual(sale_movements.count(), 2)
        self.assertEqual(
            sale_movements.values("source_line_id").distinct().count(),
            2,
        )

    def test_deduct_stock_fefo_excludes_expired_batches(self):
        MedicineBatch.objects.create(
            medicine=self.medicine,
            batch_number="EXPIRED",
            expiry_date=timezone.localdate() - timedelta(days=1),
            acquisition_cost_per_base_unit=Decimal("1.0000"),
            quantity_available_base=Decimal("5.000"),
            first_received_at=timezone.now(),
        )

        with self.assertRaises(InsufficientStockError):
            deduct_stock_fefo(
                actor=self.user,
                medicine=self.medicine,
                quantity_base=Decimal("1.000"),
                source_type="SALE",
                source_id=uuid.uuid4(),
                source_line_id_factory=lambda allocation: uuid.uuid4(),
                reference_number="SAL-EXPIRED",
            )

    def test_deduct_stock_fefo_raises_on_insufficient_stock_and_rolls_back(self):
        batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            batch_number="SHORT",
            expiry_date=timezone.localdate() + timedelta(days=30),
            acquisition_cost_per_base_unit=Decimal("1.0000"),
            quantity_available_base=Decimal("2.000"),
            first_received_at=timezone.now(),
        )

        with self.assertRaises(InsufficientStockError):
            deduct_stock_fefo(
                actor=self.user,
                medicine=self.medicine,
                quantity_base=Decimal("5.000"),
                source_type="SALE",
                source_id=uuid.uuid4(),
                source_line_id_factory=lambda allocation: uuid.uuid4(),
                reference_number="SAL-SHORT",
            )

        batch.refresh_from_db()
        self.assertEqual(batch.quantity_available_base, Decimal("2.000"))
        self.assertFalse(
            StockMovement.objects.filter(batch=batch, movement_type="SALE").exists()
        )

    def test_restock_customer_return_increases_quantity(self):
        batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            batch_number="RESTOCK",
            expiry_date=timezone.localdate() + timedelta(days=30),
            acquisition_cost_per_base_unit=Decimal("1.0000"),
            quantity_available_base=Decimal("2.000"),
            first_received_at=timezone.now(),
        )

        restock_customer_return(
            actor=self.user,
            batch=batch,
            quantity_base=Decimal("1.000"),
            source_type="CUSTOMER_RETURN_RESTOCK",
            source_id=uuid.uuid4(),
            source_line_id=uuid.uuid4(),
            reference_number="CRT-RESTOCK",
        )

        batch.refresh_from_db()
        self.assertEqual(batch.quantity_available_base, Decimal("3.000"))

    def test_restock_customer_return_rejects_expired_batch(self):
        batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            batch_number="EXPIRED-RETURN",
            expiry_date=timezone.localdate() - timedelta(days=1),
            acquisition_cost_per_base_unit=Decimal("1.0000"),
            quantity_available_base=Decimal("2.000"),
            first_received_at=timezone.now(),
        )

        with self.assertRaises(InvalidStockOperationError):
            restock_customer_return(
                actor=self.user,
                batch=batch,
                quantity_base=Decimal("1.000"),
                source_type="CUSTOMER_RETURN_RESTOCK",
                source_id=uuid.uuid4(),
                source_line_id=uuid.uuid4(),
                reference_number="CRT-EXPIRED",
            )

        batch.refresh_from_db()
        self.assertEqual(batch.quantity_available_base, Decimal("2.000"))

    def test_deduct_supplier_return_rejects_over_return(self):
        batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            batch_number="SUPPLIER-RETURN",
            expiry_date=timezone.localdate() + timedelta(days=30),
            acquisition_cost_per_base_unit=Decimal("1.0000"),
            quantity_available_base=Decimal("2.000"),
            first_received_at=timezone.now(),
        )

        with self.assertRaises(InsufficientStockError):
            deduct_supplier_return(
                actor=self.user,
                batch=batch,
                quantity_base=Decimal("5.000"),
                source_type="SUPPLIER_RETURN",
                source_id=uuid.uuid4(),
                source_line_id=uuid.uuid4(),
                reference_number="SRT-OVER",
            )

        batch.refresh_from_db()
        self.assertEqual(batch.quantity_available_base, Decimal("2.000"))
