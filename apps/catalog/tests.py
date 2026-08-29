from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .models import MedicineUnit
from .unit_economics import (
    acquisition_cost_per_base_unit,
    base_quantity,
    selected_unit_selling_price,
)


class MedicineUnitValidationTests(SimpleTestCase):
    def test_base_unit_requires_conversion_of_one(self):
        unit = MedicineUnit(is_base_unit=True, conversion_to_base=Decimal("2"))

        with self.assertRaises(ValidationError):
            unit.clean()


class UnitEconomicsTests(SimpleTestCase):
    def test_selected_units_convert_to_base_quantity(self):
        self.assertEqual(
            base_quantity(Decimal("2.000"), Decimal("20.000000")),
            Decimal("40.000"),
        )

    def test_base_unit_selling_price_converts_to_selected_unit_price(self):
        self.assertEqual(
            selected_unit_selling_price(
                Decimal("0.2500"),
                Decimal("20.000000"),
            ),
            Decimal("5.0000"),
        )

    def test_selected_purchase_unit_cost_converts_to_base_unit_cost(self):
        self.assertEqual(
            acquisition_cost_per_base_unit(
                Decimal("8.0000"),
                Decimal("20.000000"),
            ),
            Decimal("0.4000"),
        )

    def test_base_quantity_uses_three_decimal_half_up_rounding(self):
        self.assertEqual(
            base_quantity(Decimal("0.001"), Decimal("0.500000")),
            Decimal("0.001"),
        )
