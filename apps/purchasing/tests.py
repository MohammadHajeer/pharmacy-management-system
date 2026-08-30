from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .models import PurchaseInvoice


class PurchaseInvoiceValidationTests(SimpleTestCase):
    def test_posted_invoice_requires_number(self):
        invoice = PurchaseInvoice(status=PurchaseInvoice.Status.POSTED, invoice_number="")

        with self.assertRaises(ValidationError):
            invoice.clean()


from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Category, Manufacturer, Medicine, MedicineUnit
from apps.inventory.models import MedicineBatch
from apps.parties.models import Supplier

from .services import create_draft_purchase_invoice, post_purchase_invoice


class PurchaseInvoiceServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name="Purchasing category")
        manufacturer = Manufacturer.objects.create(name="Purchasing manufacturer")
        cls.medicine = Medicine.objects.create(
            name="Purchasing medicine",
            category=category,
            manufacturer=manufacturer,
            default_selling_price=Decimal("2.00"),
        )
        cls.base_unit = MedicineUnit.objects.create(
            medicine=cls.medicine,
            name="Tablet",
            conversion_to_base=Decimal("1.000000"),
            is_base_unit=True,
        )
        cls.box_unit = MedicineUnit.objects.create(
            medicine=cls.medicine,
            name="Box of 10",
            conversion_to_base=Decimal("10.000000"),
            is_base_unit=False,
        )
        cls.supplier = Supplier.objects.create(code="SUP-PT", name="Purchasing supplier")

        cls.actor = get_user_model().objects.create_user(username="purchasing-user")
        for codename in ("add_purchaseinvoice", "post_purchaseinvoice", "view_purchaseinvoice"):
            cls.actor.user_permissions.add(
                Permission.objects.get(codename=codename, content_type__app_label="purchasing")
            )

    def _line(self, **overrides):
        line = {
            "medicine": self.medicine,
            "medicine_unit": self.box_unit,
            "quantity": Decimal("5.000"),
            "unit_cost": Decimal("12.5000"),
            "discount_amount": Decimal("0.00"),
            "tax_rate_percent": Decimal("10.0000"),
            "batch_number": "PB-1",
            "expiry_date": timezone.localdate() + timedelta(days=180),
        }
        line.update(overrides)
        return line

    def test_create_draft_computes_totals_and_base_quantities(self):
        invoice = create_draft_purchase_invoice(
            actor=self.actor,
            supplier=self.supplier,
            invoice_date=timezone.localdate(),
            currency_code="USD",
            lines_data=[self._line()],
        )

        self.assertEqual(invoice.status, PurchaseInvoice.Status.DRAFT)
        line = invoice.lines.get()
        # 5 boxes * 10 tablets/box = 50 base units.
        self.assertEqual(line.received_quantity_base, Decimal("50.000"))
        # subtotal = 5 * 12.50 = 62.50; tax = 6.25; total = 68.75
        self.assertEqual(invoice.subtotal, Decimal("62.50"))
        self.assertEqual(invoice.tax_total, Decimal("6.25"))
        self.assertEqual(invoice.grand_total, Decimal("68.75"))
        self.assertEqual(invoice.remaining_balance, invoice.grand_total)

    def test_post_purchase_invoice_creates_batch_and_marks_posted(self):
        invoice = create_draft_purchase_invoice(
            actor=self.actor,
            supplier=self.supplier,
            invoice_date=timezone.localdate(),
            currency_code="USD",
            lines_data=[self._line()],
        )

        posted = post_purchase_invoice(actor=self.actor, purchase_invoice_id=invoice.id)

        self.assertEqual(posted.status, PurchaseInvoice.Status.POSTED)
        self.assertTrue(posted.invoice_number.startswith("PUR-"))
        self.assertIsNotNone(posted.posted_at)

        batch = MedicineBatch.objects.get(medicine=self.medicine, batch_number="PB-1")
        self.assertEqual(batch.quantity_available_base, Decimal("50.000"))

        line = posted.lines.get()
        self.assertEqual(line.medicine_batch_id, batch.id)

    def test_posting_same_batch_twice_accumulates_quantity_in_one_batch_row(self):
        first_invoice = create_draft_purchase_invoice(
            actor=self.actor,
            supplier=self.supplier,
            invoice_date=timezone.localdate(),
            currency_code="USD",
            lines_data=[self._line(quantity=Decimal("2.000"))],
        )
        second_invoice = create_draft_purchase_invoice(
            actor=self.actor,
            supplier=self.supplier,
            invoice_date=timezone.localdate(),
            currency_code="USD",
            lines_data=[self._line(quantity=Decimal("3.000"))],
        )

        post_purchase_invoice(actor=self.actor, purchase_invoice_id=first_invoice.id)
        post_purchase_invoice(actor=self.actor, purchase_invoice_id=second_invoice.id)

        self.assertEqual(
            MedicineBatch.objects.filter(medicine=self.medicine, batch_number="PB-1").count(),
            1,
        )
        batch = MedicineBatch.objects.get(medicine=self.medicine, batch_number="PB-1")
        # (2 + 3) boxes * 10 = 50 base units.
        self.assertEqual(batch.quantity_available_base, Decimal("50.000"))

    def test_cannot_post_an_already_posted_invoice(self):
        invoice = create_draft_purchase_invoice(
            actor=self.actor,
            supplier=self.supplier,
            invoice_date=timezone.localdate(),
            currency_code="USD",
            lines_data=[self._line()],
        )
        post_purchase_invoice(actor=self.actor, purchase_invoice_id=invoice.id)

        with self.assertRaises(ValidationError):
            post_purchase_invoice(actor=self.actor, purchase_invoice_id=invoice.id)
