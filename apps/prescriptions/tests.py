from django.test import SimpleTestCase

from .models import Prescription


class PrescriptionStringTests(SimpleTestCase):
    def test_reference_number_is_used_for_display(self):
        self.assertEqual(
            str(Prescription(reference_number="RX-100")),
            "RX-100",
        )
