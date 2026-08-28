from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .models import SalesInvoice


class SalesInvoiceValidationTests(SimpleTestCase):
    def test_completed_walk_in_sale_must_be_settled(self):
        invoice = SalesInvoice(
            status=SalesInvoice.Status.COMPLETED,
            invoice_number="SALE-1",
            customer=None,
            balance_due=Decimal("1.00"),
        )

        with self.assertRaises(ValidationError):
            invoice.clean()
