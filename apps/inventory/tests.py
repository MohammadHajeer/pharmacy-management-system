import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.catalog.models import Category, Manufacturer, Medicine

from .models import MedicineBatch, StockMovement


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
