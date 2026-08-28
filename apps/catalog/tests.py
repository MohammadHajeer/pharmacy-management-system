from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .models import MedicineUnit


class MedicineUnitValidationTests(SimpleTestCase):
    def test_base_unit_requires_conversion_of_one(self):
        unit = MedicineUnit(is_base_unit=True, conversion_to_base=Decimal("2"))

        with self.assertRaises(ValidationError):
            unit.clean()
