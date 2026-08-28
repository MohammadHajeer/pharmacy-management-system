from django.conf import settings
from django.db import models
from django.db.models import NOT_PROVIDED
from django.test import SimpleTestCase

from .models import PaymentStatus, SupplierPayment


class PaymentStatusTests(SimpleTestCase):
    def test_payment_statuses_are_minimal_phase_one_states(self):
        self.assertEqual(set(PaymentStatus.values), {"POSTED", "REVERSED"})

    def test_supplier_payment_reversal_fields_match_phase_one_schema(self):
        status = SupplierPayment._meta.get_field("status")
        reversed_by = SupplierPayment._meta.get_field("reversed_by")
        reversed_at = SupplierPayment._meta.get_field("reversed_at")
        reversal_reason = SupplierPayment._meta.get_field("reversal_reason")

        self.assertIsInstance(status, models.CharField)
        self.assertEqual(status.max_length, 10)
        self.assertEqual(status.default, PaymentStatus.POSTED)
        self.assertFalse(status.null)
        self.assertFalse(status.blank)

        self.assertIsInstance(reversed_by, models.ForeignKey)
        self.assertEqual(reversed_by.remote_field.model._meta.label, settings.AUTH_USER_MODEL)
        self.assertIs(reversed_by.remote_field.on_delete, models.PROTECT)
        self.assertTrue(reversed_by.null)
        self.assertTrue(reversed_by.blank)
        self.assertIs(reversed_by.default, NOT_PROVIDED)

        self.assertIsInstance(reversed_at, models.DateTimeField)
        self.assertTrue(reversed_at.null)
        self.assertTrue(reversed_at.blank)
        self.assertIs(reversed_at.default, NOT_PROVIDED)

        self.assertIsInstance(reversal_reason, models.TextField)
        self.assertFalse(reversal_reason.null)
        self.assertTrue(reversal_reason.blank)
        self.assertIs(reversal_reason.default, NOT_PROVIDED)
