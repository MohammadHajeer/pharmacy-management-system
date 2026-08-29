from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.catalog.models import Category, Manufacturer, Medicine, MedicineUnit
from apps.inventory.models import MedicineBatch

from .models import SaleBatchAllocation, SalesInvoice, SalesInvoiceLine


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


class SaleBatchAllocationConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name="Pain relief")
        manufacturer = Manufacturer.objects.create(name="Example manufacturer")
        medicine = Medicine.objects.create(
            name="Example tablet",
            category=category,
            manufacturer=manufacturer,
        )
        unit = MedicineUnit.objects.create(
            medicine=medicine,
            name="Tablet",
            conversion_to_base=Decimal("1.000000"),
            is_base_unit=True,
        )
        cls.batch = MedicineBatch.objects.create(
            medicine=medicine,
            batch_number="BATCH-1",
            expiry_date=timezone.localdate() + timedelta(days=365),
            acquisition_cost_per_base_unit=Decimal("0.4000"),
            quantity_available_base=Decimal("100.000"),
            first_received_at=timezone.now(),
        )
        pharmacist = get_user_model().objects.create_user(username="allocation-user")
        invoice = SalesInvoice.objects.create(
            pharmacist=pharmacist,
            currency_code="USD",
        )
        cls.line = SalesInvoiceLine.objects.create(
            sales_invoice=invoice,
            medicine=medicine,
            medicine_description_snapshot=medicine.name,
            medicine_unit=unit,
            unit_name_snapshot=unit.name,
            quantity=Decimal("2.000"),
            conversion_to_base_snapshot=Decimal("1.000000"),
            requested_quantity_base=Decimal("2.000"),
            unit_price=Decimal("1.0000"),
            line_total=Decimal("2.00"),
        )
        SaleBatchAllocation.objects.create(
            sales_invoice_line=cls.line,
            batch=cls.batch,
            allocated_quantity_base=Decimal("2.000"),
            acquisition_cost_snapshot=Decimal("0.4000"),
        )

    def test_duplicate_line_batch_allocation_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SaleBatchAllocation.objects.create(
                    sales_invoice_line=self.line,
                    batch=self.batch,
                    allocated_quantity_base=Decimal("1.000"),
                    acquisition_cost_snapshot=Decimal("0.4000"),
                )
