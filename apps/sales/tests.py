from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import (
    Category,
    Manufacturer,
    Medicine,
    MedicineBarcode,
    MedicineUnit,
)
from apps.core.models import PharmacySettings, TaxRate
from apps.inventory.models import MedicineBatch, StockMovement
from apps.parties.models import Customer
from apps.prescriptions.models import Prescription

from .forms import DraftSaleForm, DraftSaleLineFormSet
from .models import SaleBatchAllocation, SalesInvoice, SalesInvoiceLine
from .queries import active_pos_medicine_queryset, find_active_pos_barcode
from .services import process_draft_sale


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


class PosTestDataMixin:
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        user_model = get_user_model()
        cls.authorized_user = user_model.objects.create_user(username="pos-pharmacist")
        cls.unauthorized_user = user_model.objects.create_user(username="pos-accountant")
        cls.authorized_user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="sales",
                codename__in={
                    "add_salesinvoice",
                    "change_salesinvoice",
                    "view_salesinvoice",
                    "add_salesinvoiceline",
                    "change_salesinvoiceline",
                    "view_salesinvoiceline",
                },
            )
        )

        cls.category = Category.objects.create(name="POS medicines")
        cls.manufacturer = Manufacturer.objects.create(name="POS manufacturer")
        cls.medicine = Medicine.objects.create(
            name="Prescription tablets",
            generic_name="Example ingredient",
            category=cls.category,
            manufacturer=cls.manufacturer,
            strength="10 mg",
            prescription_required=True,
            default_selling_price=Decimal("1.2345"),
        )
        cls.base_unit = MedicineUnit.objects.create(
            medicine=cls.medicine,
            name="Tablet",
            conversion_to_base=Decimal("1.000000"),
            is_base_unit=True,
        )
        cls.box_unit = MedicineUnit.objects.create(
            medicine=cls.medicine,
            name="Box",
            conversion_to_base=Decimal("10.000000"),
        )
        cls.barcode = MedicineBarcode.objects.create(
            medicine_unit=cls.box_unit,
            barcode="POS-BOX-001",
        )
        cls.inactive_barcode = MedicineBarcode.objects.create(
            medicine_unit=cls.box_unit,
            barcode="POS-INACTIVE-001",
            is_active=False,
        )

        cls.other_medicine = Medicine.objects.create(
            name="General tablets",
            category=cls.category,
            manufacturer=cls.manufacturer,
            default_selling_price=Decimal("2.0000"),
        )
        cls.other_unit = MedicineUnit.objects.create(
            medicine=cls.other_medicine,
            name="Tablet",
            conversion_to_base=Decimal("1.000000"),
            is_base_unit=True,
        )

        cls.inactive_medicine = Medicine.objects.create(
            name="Inactive medicine",
            category=cls.category,
            manufacturer=cls.manufacturer,
            default_selling_price=Decimal("3.0000"),
            is_active=False,
        )
        cls.inactive_unit = MedicineUnit.objects.create(
            medicine=cls.inactive_medicine,
            name="Inactive unit",
            conversion_to_base=Decimal("1.000000"),
            is_base_unit=True,
        )
        MedicineBarcode.objects.create(
            medicine_unit=cls.inactive_unit,
            barcode="POS-INACTIVE-MEDICINE",
        )

        now = timezone.now()
        cls.eligible_batch = MedicineBatch.objects.create(
            medicine=cls.medicine,
            batch_number="POS-ELIGIBLE",
            expiry_date=timezone.localdate() + timedelta(days=30),
            acquisition_cost_per_base_unit=Decimal("0.4000"),
            quantity_available_base=Decimal("10.000"),
            first_received_at=now,
        )
        MedicineBatch.objects.create(
            medicine=cls.medicine,
            batch_number="POS-EXPIRED",
            expiry_date=timezone.localdate() - timedelta(days=1),
            acquisition_cost_per_base_unit=Decimal("0.4000"),
            quantity_available_base=Decimal("50.000"),
            first_received_at=now,
        )
        MedicineBatch.objects.create(
            medicine=cls.medicine,
            batch_number="POS-INACTIVE-BATCH",
            expiry_date=timezone.localdate() + timedelta(days=10),
            acquisition_cost_per_base_unit=Decimal("0.4000"),
            quantity_available_base=Decimal("20.000"),
            first_received_at=now,
            is_active=False,
        )

        cls.customer = Customer.objects.create(code="POS-CUSTOMER", name="Saved customer")
        cls.prescription = Prescription.objects.create(
            reference_number="POS-RX",
            customer=cls.customer,
            prescription_date=timezone.localdate(),
            created_by=cls.authorized_user,
        )
        cls.tax_rate = TaxRate.objects.create(
            code="POS-TAX",
            name="POS tax",
            rate_percent=Decimal("11.0000"),
        )
        cls.pharmacy_settings = PharmacySettings.objects.create(
            pharmacy_name="POS Pharmacy",
            currency_code="USD",
            default_tax_rate=cls.tax_rate,
        )

    def draft_data(self, *, customer="", prescription="", line_count=1, **overrides):
        data = {
            "customer": customer,
            "prescription": prescription,
            "lines-TOTAL_FORMS": str(line_count),
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-medicine": str(self.medicine.pk),
            "lines-0-medicine_unit": str(self.box_unit.pk),
            "lines-0-quantity": "2.000",
            "lines-0-discount_amount": "1.00",
            "lines-0-prescription_warning_acknowledged": "",
        }
        if line_count > 1:
            data.update(
                {
                    "lines-1-medicine": str(self.other_medicine.pk),
                    "lines-1-medicine_unit": str(self.other_unit.pk),
                    "lines-1-quantity": "3.000",
                    "lines-1-discount_amount": "0.00",
                    "lines-1-prescription_warning_acknowledged": "",
                }
            )
        data.update(overrides)
        return data


class PosLookupTests(PosTestDataMixin, TestCase):
    def test_active_medicine_search_exposes_only_eligible_query_only_stock(self):
        before_quantity = self.eligible_batch.quantity_available_base
        before_movements = StockMovement.objects.count()

        medicines = list(active_pos_medicine_queryset("Example ingredient"))

        self.assertEqual(medicines, [self.medicine])
        result = medicines[0]
        self.assertEqual(result.available_stock_base, Decimal("10.000"))
        self.assertEqual(result.earliest_expiry_date, self.eligible_batch.expiry_date)
        self.assertEqual(
            [unit.pk for unit in result.pos_sale_units],
            [self.base_unit.pk, self.box_unit.pk],
        )
        self.eligible_batch.refresh_from_db()
        self.assertEqual(self.eligible_batch.quantity_available_base, before_quantity)
        self.assertEqual(StockMovement.objects.count(), before_movements)

    def test_exact_active_barcode_resolves_medicine_and_sale_unit(self):
        result = find_active_pos_barcode("  POS-BOX-001  ")

        self.assertEqual(result, self.barcode)
        self.assertEqual(result.medicine_unit, self.box_unit)
        self.assertEqual(result.medicine_unit.medicine, self.medicine)

    def test_unknown_or_inactive_barcode_returns_none_and_writes_nothing(self):
        counts_before = (
            Medicine.objects.count(),
            MedicineUnit.objects.count(),
            MedicineBarcode.objects.count(),
            SalesInvoice.objects.count(),
            SalesInvoiceLine.objects.count(),
            StockMovement.objects.count(),
        )

        self.assertIsNone(find_active_pos_barcode("UNKNOWN-BARCODE"))
        self.assertIsNone(find_active_pos_barcode(self.inactive_barcode.barcode))
        self.assertIsNone(find_active_pos_barcode("POS-INACTIVE-MEDICINE"))

        self.assertEqual(
            counts_before,
            (
                Medicine.objects.count(),
                MedicineUnit.objects.count(),
                MedicineBarcode.objects.count(),
                SalesInvoice.objects.count(),
                SalesInvoiceLine.objects.count(),
                StockMovement.objects.count(),
            ),
        )

    def test_lookup_endpoints_enforce_permissions_and_return_server_prices(self):
        search_url = reverse("sales:pos-medicine-search")
        barcode_url = reverse("sales:pos-barcode-lookup")
        self.assertEqual(self.client.get(search_url).status_code, 302)

        self.client.force_login(self.unauthorized_user)
        self.assertEqual(self.client.get(search_url).status_code, 403)

        self.client.force_login(self.authorized_user)
        response = self.client.get(search_url, {"q": "Prescription tablets"})
        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        self.assertEqual(result["available_stock_base"], "10.000")
        box_payload = next(unit for unit in result["units"] if unit["name"] == "Box")
        self.assertEqual(box_payload["selected_unit_price"], "12.3450")

        response = self.client.get(barcode_url, {"barcode": "POS-BOX-001"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["matched_unit_id"], str(self.box_unit.pk))
        self.assertEqual(self.client.get(barcode_url, {"barcode": "UNKNOWN"}).status_code, 404)


class PosDraftServiceTests(PosTestDataMixin, TestCase):
    def test_saved_customer_multiple_line_draft_uses_approved_decimal_sequence(self):
        form, line_formset, invoice = process_draft_sale(
            actor=self.authorized_user,
            data=self.draft_data(
                customer=str(self.customer.pk),
                prescription=str(self.prescription.pk),
                line_count=2,
            ),
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(line_formset.is_valid(), line_formset.errors)
        self.assertEqual(invoice.customer, self.customer)
        self.assertEqual(invoice.prescription, self.prescription)
        self.assertEqual(invoice.currency_code, "USD")
        self.assertEqual(invoice.subtotal, Decimal("30.69"))
        self.assertEqual(invoice.discount_total, Decimal("1.00"))
        self.assertEqual(invoice.tax_total, Decimal("3.27"))
        self.assertEqual(invoice.grand_total, Decimal("32.96"))
        self.assertEqual(invoice.balance_due, Decimal("32.96"))
        self.assertEqual(invoice.paid_total, Decimal("0.00"))
        self.assertEqual(invoice.invoice_number, "")

        line = invoice.lines.get(medicine=self.medicine)
        self.assertEqual(line.medicine_description_snapshot, self.medicine.name)
        self.assertEqual(line.unit_name_snapshot, self.box_unit.name)
        self.assertEqual(line.quantity, Decimal("2.000"))
        self.assertEqual(line.conversion_to_base_snapshot, Decimal("10.000000"))
        self.assertEqual(line.requested_quantity_base, Decimal("20.000"))
        self.assertEqual(line.unit_price, Decimal("12.3450"))
        self.assertEqual(line.discount_amount, Decimal("1.00"))
        self.assertEqual(line.tax_rate_percent, Decimal("11.0000"))
        self.assertEqual(line.tax_amount, Decimal("2.61"))
        self.assertEqual(line.line_total, Decimal("26.30"))
        self.assertTrue(line.prescription_required_snapshot)
        self.assertFalse(line.prescription_warning_acknowledged)

    def test_walk_in_draft_requires_no_customer_row(self):
        customer_count = Customer.objects.count()

        _, _, invoice = process_draft_sale(actor=self.authorized_user, data=self.draft_data())

        self.assertIsNone(invoice.customer)
        self.assertEqual(Customer.objects.count(), customer_count)

    def test_stock_and_expiry_records_remain_unchanged(self):
        quantity_before = self.eligible_batch.quantity_available_base
        expiry_before = self.eligible_batch.expiry_date

        _, _, invoice = process_draft_sale(actor=self.authorized_user, data=self.draft_data())

        self.assertIsNotNone(invoice)
        self.eligible_batch.refresh_from_db()
        self.assertEqual(self.eligible_batch.quantity_available_base, quantity_before)
        self.assertEqual(self.eligible_batch.expiry_date, expiry_before)
        self.assertFalse(SaleBatchAllocation.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_tampered_client_totals_are_rejected_without_writes(self):
        for field_name, value in (
            ("grand_total", "0.01"),
            ("lines-0-unit_price", "0.0001"),
            ("lines-0-tax_amount", "0.00"),
            ("lines-0-requested_quantity_base", "1.000"),
        ):
            with self.subTest(field_name=field_name):
                form, line_formset, invoice = process_draft_sale(
                    actor=self.authorized_user,
                    data=self.draft_data(**{field_name: value}),
                )
                self.assertIsNone(invoice)
                self.assertTrue(form.errors or line_formset.errors)
                self.assertFalse(SalesInvoice.objects.exists())

    def test_invalid_medicine_unit_discount_and_inactive_inputs_are_rejected(self):
        invalid_payloads = (
            {"lines-0-medicine_unit": str(self.other_unit.pk)},
            {"lines-0-discount_amount": "24.70"},
            {
                "lines-0-medicine": str(self.inactive_medicine.pk),
                "lines-0-medicine_unit": str(self.inactive_unit.pk),
            },
        )
        for overrides in invalid_payloads:
            with self.subTest(overrides=overrides):
                _, _, invoice = process_draft_sale(
                    actor=self.authorized_user,
                    data=self.draft_data(**overrides),
                )
                self.assertIsNone(invoice)
                self.assertFalse(SalesInvoice.objects.exists())

    def test_unauthorized_and_anonymous_callers_are_denied(self):
        for actor in (self.unauthorized_user, AnonymousUser()):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    process_draft_sale(actor=actor, data=self.draft_data())
        self.assertFalse(SalesInvoice.objects.exists())

    def test_update_recalculates_and_replaces_only_draft_lines(self):
        _, _, invoice = process_draft_sale(actor=self.authorized_user, data=self.draft_data())
        original_line_id = invoice.lines.get().pk

        _, _, updated = process_draft_sale(
            actor=self.authorized_user,
            instance=invoice,
            data=self.draft_data(
                **{
                    "lines-0-quantity": "1.000",
                    "lines-0-discount_amount": "0.00",
                }
            ),
        )

        self.assertEqual(updated.pk, invoice.pk)
        self.assertFalse(SalesInvoiceLine.objects.filter(pk=original_line_id).exists())
        self.assertEqual(updated.lines.count(), 1)
        self.assertEqual(updated.subtotal, Decimal("12.35"))
        self.assertEqual(updated.tax_total, Decimal("1.36"))
        self.assertEqual(updated.grand_total, Decimal("13.71"))

    def test_draft_endpoints_are_permission_scoped_and_return_authoritative_totals(self):
        create_url = reverse("sales:pos-draft-create")
        self.assertEqual(self.client.post(create_url, self.draft_data()).status_code, 302)

        self.client.force_login(self.unauthorized_user)
        self.assertEqual(self.client.post(create_url, self.draft_data()).status_code, 403)

        self.client.force_login(self.authorized_user)
        response = self.client.post(create_url, self.draft_data())
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["grand_total"], "26.30")
        self.assertEqual(payload["lines"][0]["unit_price"], "12.3450")
        self.assertEqual(payload["lines"][0]["requested_quantity_base"], "20.000")

        detail_url = reverse("sales:pos-draft-detail", args=[payload["id"]])
        self.assertEqual(self.client.get(detail_url).status_code, 200)

    def test_forms_expose_only_client_editable_draft_fields(self):
        self.assertEqual(tuple(DraftSaleForm().fields), ("customer", "prescription"))
        formset = DraftSaleLineFormSet(prefix="lines")
        self.assertEqual(
            tuple(formset.empty_form.fields),
            (
                "medicine",
                "medicine_unit",
                "quantity",
                "discount_amount",
                "prescription_warning_acknowledged",
            ),
        )
