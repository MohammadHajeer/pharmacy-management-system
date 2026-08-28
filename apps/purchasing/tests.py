from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .models import PurchaseInvoice


class PurchaseInvoiceValidationTests(SimpleTestCase):
    def test_posted_invoice_requires_number(self):
        invoice = PurchaseInvoice(status=PurchaseInvoice.Status.POSTED, invoice_number="")

        with self.assertRaises(ValidationError):
            invoice.clean()
