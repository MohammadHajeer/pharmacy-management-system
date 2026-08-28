from decimal import Decimal

from django.test import SimpleTestCase

from .models import PharmacySettings


class PharmacySettingsTests(SimpleTestCase):
    def test_string_representation_uses_pharmacy_name(self):
        settings = PharmacySettings(
            pharmacy_name="Community Pharmacy",
            currency_code="USD",
            default_low_stock_threshold=Decimal("0.000"),
        )

        self.assertEqual(str(settings), "Community Pharmacy")
