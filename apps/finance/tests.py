from django.test import SimpleTestCase

from .models import PaymentStatus


class PaymentStatusTests(SimpleTestCase):
    def test_payment_statuses_are_minimal_phase_one_states(self):
        self.assertEqual(set(PaymentStatus.values), {"POSTED", "REVERSED"})
