from django.test import SimpleTestCase

from .models import StockMovement


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
