import threading
from datetime import timedelta
from decimal import Decimal
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, connections, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import (
    Category,
    Manufacturer,
    Medicine,
    MedicineBarcode,
    MedicineUnit,
)
from apps.core.models import PaymentMethod, PharmacySettings, TaxRate
from apps.finance.models import CustomerPayment, PaymentStatus
from apps.inventory.models import MedicineBatch, StockMovement
from apps.inventory.services import InsufficientStockError
from apps.parties.models import Customer
from apps.prescriptions.models import Prescription

from .forms import DraftSaleForm, DraftSaleLineFormSet
from .models import SaleBatchAllocation, SalesInvoice, SalesInvoiceLine
from .queries import active_pos_medicine_queryset, find_active_pos_barcode
from .services import complete_sale, process_draft_sale


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

    def test_medicine_search_paginates_in_stable_twelve_item_pages(self):
        now = timezone.now()
        medicines = []
        for number in range(1, 14):
            medicine = Medicine.objects.create(
                name=f"Paging medicine {number:02d}",
                category=self.category,
                manufacturer=self.manufacturer,
                default_selling_price=Decimal("1.0000"),
            )
            MedicineUnit.objects.create(
                medicine=medicine,
                name="Unit",
                conversion_to_base=Decimal("1.000000"),
                is_base_unit=True,
            )
            MedicineBatch.objects.create(
                medicine=medicine,
                batch_number=f"PAGING-{number:02d}",
                expiry_date=timezone.localdate() + timedelta(days=30),
                acquisition_cost_per_base_unit=Decimal("0.5000"),
                quantity_available_base=Decimal("1.000"),
                first_received_at=now,
            )
            medicines.append(medicine)

        self.client.force_login(self.authorized_user)
        url = reverse("sales:pos-medicine-search")
        first = self.client.get(url, {"q": "Paging medicine", "limit": 12, "page": 1})
        second = self.client.get(url, {"q": "Paging medicine", "limit": 12, "page": 2})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        first_payload = first.json()
        second_payload = second.json()
        self.assertEqual(
            [result["id"] for result in first_payload["results"]],
            [str(medicine.pk) for medicine in medicines[:12]],
        )
        self.assertEqual(first_payload["page"], 1)
        self.assertEqual(first_payload["page_size"], 12)
        self.assertFalse(first_payload["has_previous"])
        self.assertTrue(first_payload["has_next"])
        self.assertEqual(
            [result["id"] for result in second_payload["results"]],
            [str(medicines[12].pk)],
        )
        self.assertEqual(second_payload["page"], 2)
        self.assertEqual(second_payload["page_size"], 12)
        self.assertTrue(second_payload["has_previous"])
        self.assertFalse(second_payload["has_next"])

    def test_medicine_search_rejects_non_positive_page_numbers(self):
        self.client.force_login(self.authorized_user)
        response = self.client.get(
            reverse("sales:pos-medicine-search"),
            {"q": "medicine", "limit": 12, "page": 0},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("page", response.json()["errors"])


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


class SaleCompletionServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.actor = user_model.objects.create_user(username="sale-completer")
        cls.actor.user_permissions.set(
            Permission.objects.filter(
                codename__in={"complete_sale", "post_customerpayment"},
                content_type__app_label__in={"sales", "finance"},
            )
        )
        cls.unauthorized_user = user_model.objects.create_user(
            username="sale-completion-denied"
        )

        cls.category = Category.objects.create(name="Completion category")
        cls.manufacturer = Manufacturer.objects.create(name="Completion manufacturer")
        cls.medicine = Medicine.objects.create(
            name="Completion tablets",
            category=cls.category,
            manufacturer=cls.manufacturer,
            default_selling_price=Decimal("10.0000"),
        )
        cls.unit = MedicineUnit.objects.create(
            medicine=cls.medicine,
            name="Tablet",
            conversion_to_base=Decimal("1.000000"),
            is_base_unit=True,
        )
        cls.customer = Customer.objects.create(
            code="COMP-CUSTOMER",
            name="Completion Customer",
            phone="555-0100",
        )
        cls.payment_method = PaymentMethod.objects.create(code="COMP-CASH", name="Cash")
        PharmacySettings.objects.create(
            pharmacy_name="Completion Pharmacy",
            currency_code="USD",
        )

    def setUp(self):
        now = timezone.now()
        self.first_batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            batch_number="COMP-FIRST",
            expiry_date=timezone.localdate() + timedelta(days=30),
            acquisition_cost_per_base_unit=Decimal("2.5000"),
            quantity_available_base=Decimal("4.000"),
            first_received_at=now - timedelta(days=2),
        )
        self.second_batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            batch_number="COMP-SECOND",
            expiry_date=timezone.localdate() + timedelta(days=60),
            acquisition_cost_per_base_unit=Decimal("3.0000"),
            quantity_available_base=Decimal("10.000"),
            first_received_at=now - timedelta(days=1),
        )
        self.expired_batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            batch_number="COMP-EXPIRED",
            expiry_date=timezone.localdate() - timedelta(days=1),
            acquisition_cost_per_base_unit=Decimal("1.0000"),
            quantity_available_base=Decimal("100.000"),
            first_received_at=now - timedelta(days=10),
        )

    def create_draft(
        self,
        *,
        quantity=Decimal("7.000"),
        customer=True,
        prescription_required=False,
        warning_acknowledged=True,
    ):
        grand_total = (quantity * Decimal("10.0000")).quantize(Decimal("0.01"))
        invoice = SalesInvoice.objects.create(
            customer=self.customer if customer else None,
            pharmacist=self.actor,
            currency_code="USD",
            subtotal=grand_total,
            grand_total=grand_total,
            balance_due=grand_total,
        )
        SalesInvoiceLine.objects.create(
            sales_invoice=invoice,
            medicine=self.medicine,
            medicine_description_snapshot=self.medicine.name,
            medicine_unit=self.unit,
            unit_name_snapshot=self.unit.name,
            quantity=quantity,
            conversion_to_base_snapshot=Decimal("1.000000"),
            requested_quantity_base=quantity,
            unit_price=Decimal("10.0000"),
            line_total=grand_total,
            prescription_required_snapshot=prescription_required,
            prescription_warning_acknowledged=warning_acknowledged,
        )
        return invoice

    def payment_data(self, amount):
        return {
            "payment_method": str(self.payment_method.pk),
            "amount": str(amount),
            "reference": "",
            "paid_at": timezone.now().isoformat(),
        }

    def test_completion_allocates_fefo_and_creates_exact_movement_mapping(self):
        invoice = self.create_draft()

        result = complete_sale(actor=self.actor, sales_invoice_id=invoice.pk)

        completed = result.invoice
        self.assertEqual(completed.status, SalesInvoice.Status.COMPLETED)
        self.assertEqual(completed.invoice_number, f"SAL-{invoice.id.hex.upper()}")
        self.assertEqual(completed.pharmacy_name_snapshot, "Completion Pharmacy")
        self.assertEqual(completed.customer_name_snapshot, self.customer.name)
        self.assertEqual(completed.customer_phone_snapshot, self.customer.phone)
        self.assertIsNotNone(completed.completed_at)

        allocations = list(
            SaleBatchAllocation.objects.filter(
                sales_invoice_line__sales_invoice=completed
            ).order_by("batch__expiry_date")
        )
        self.assertEqual(
            [allocation.allocated_quantity_base for allocation in allocations],
            [Decimal("4.000"), Decimal("3.000")],
        )
        self.assertEqual(
            [allocation.acquisition_cost_snapshot for allocation in allocations],
            [Decimal("2.5000"), Decimal("3.0000")],
        )

        movements = list(
            StockMovement.objects.filter(
                movement_type=StockMovement.MovementType.SALE,
                source_id=completed.pk,
            ).order_by("batch__expiry_date")
        )
        self.assertEqual(len(movements), 2)
        for allocation, movement in zip(allocations, movements, strict=True):
            self.assertEqual(movement.source_type, "SALE")
            self.assertEqual(movement.source_line_id, allocation.pk)
            self.assertEqual(movement.batch_id, allocation.batch_id)
            self.assertEqual(
                movement.quantity_delta_base,
                -allocation.allocated_quantity_base,
            )
            self.assertEqual(
                movement.unit_cost_snapshot,
                allocation.acquisition_cost_snapshot,
            )
            self.assertEqual(movement.reference_number, completed.invoice_number)

        self.first_batch.refresh_from_db()
        self.second_batch.refresh_from_db()
        self.expired_batch.refresh_from_db()
        self.assertEqual(self.first_batch.quantity_available_base, Decimal("0.000"))
        self.assertEqual(self.second_batch.quantity_available_base, Decimal("7.000"))
        self.assertEqual(self.expired_batch.quantity_available_base, Decimal("100.000"))

    def test_invoice_output_keeps_completion_snapshots_after_master_data_changes(self):
        self.actor.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="sales",
                codename__in={"view_salesinvoice", "view_salesinvoiceline"},
            )
        )
        completed = complete_sale(
            actor=self.actor,
            sales_invoice_id=self.create_draft().pk,
        ).invoice
        line = completed.lines.get()
        historical_values = {
            "pharmacy": completed.pharmacy_name_snapshot,
            "customer": completed.customer_name_snapshot,
            "phone": completed.customer_phone_snapshot,
            "medicine": line.medicine_description_snapshot,
            "unit": line.unit_name_snapshot,
        }

        pharmacy = PharmacySettings.objects.get(singleton_key=1)
        pharmacy.pharmacy_name = "Changed Pharmacy Master"
        pharmacy.save(update_fields=["pharmacy_name", "updated_at"])
        self.customer.name = "Changed Customer Master"
        self.customer.phone = "555-0199"
        self.customer.save(update_fields=["name", "phone", "updated_at"])
        self.medicine.name = "Changed Medicine Master"
        self.medicine.save(update_fields=["name", "updated_at"])
        self.unit.name = "Changed Unit Master"
        self.unit.save(update_fields=["name", "updated_at"])

        self.client.force_login(self.actor)
        detail_response = self.client.get(
            reverse("sales:invoice-detail", args=[completed.pk])
        )
        print_response = self.client.get(
            reverse("sales:invoice-print", args=[completed.pk])
        )
        receipt_response = self.client.get(
            reverse("sales:invoice-print", args=[completed.pk]),
            {"format": "receipt"},
        )

        for response in (detail_response, print_response, receipt_response):
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, historical_values["customer"])
            self.assertContains(response, historical_values["phone"])
            self.assertContains(response, historical_values["medicine"])
            self.assertContains(response, historical_values["unit"])
            self.assertNotContains(response, "Changed Customer Master")
            self.assertNotContains(response, "555-0199")
            self.assertNotContains(response, "Changed Medicine Master")
            self.assertNotContains(response, "Changed Unit Master")

        for response in (print_response, receipt_response):
            self.assertContains(response, historical_values["pharmacy"])
            self.assertNotContains(response, "Changed Pharmacy Master")

    def test_optional_initial_payment_uses_finance_service_and_updates_balance(self):
        invoice = self.create_draft()

        result = complete_sale(
            actor=self.actor,
            sales_invoice_id=invoice.pk,
            initial_payment_data=self.payment_data("20.00"),
        )

        self.assertIsNotNone(result.initial_payment)
        self.assertEqual(result.initial_payment.status, PaymentStatus.POSTED)
        self.assertEqual(result.invoice.paid_total, Decimal("20.00"))
        self.assertEqual(result.invoice.balance_due, Decimal("50.00"))
        self.assertEqual(
            result.invoice.payment_status,
            SalesInvoice.PaymentStatus.PARTIAL,
        )

    def test_walk_in_requires_and_accepts_only_full_initial_payment(self):
        missing_payment_invoice = self.create_draft(customer=False)
        with self.assertRaisesMessage(
            ValidationError,
            "A walk-in sale requires full payment during completion.",
        ):
            complete_sale(actor=self.actor, sales_invoice_id=missing_payment_invoice.pk)

        partial_payment_invoice = self.create_draft(customer=False)
        with self.assertRaisesMessage(
            ValidationError,
            "A completed walk-in sale must be fully settled.",
        ):
            complete_sale(
                actor=self.actor,
                sales_invoice_id=partial_payment_invoice.pk,
                initial_payment_data=self.payment_data("20.00"),
            )

        full_payment_invoice = self.create_draft(customer=False)
        result = complete_sale(
            actor=self.actor,
            sales_invoice_id=full_payment_invoice.pk,
            initial_payment_data=self.payment_data("70.00"),
        )
        self.assertEqual(result.invoice.balance_due, Decimal("0.00"))
        self.assertEqual(result.invoice.paid_total, Decimal("70.00"))
        self.assertEqual(result.invoice.payment_status, SalesInvoice.PaymentStatus.PAID)

        for rejected_invoice in (missing_payment_invoice, partial_payment_invoice):
            rejected_invoice.refresh_from_db()
            self.assertEqual(rejected_invoice.status, SalesInvoice.Status.DRAFT)
            self.assertEqual(rejected_invoice.invoice_number, "")

    def test_zero_total_walk_in_is_already_settled_without_payment(self):
        invoice = self.create_draft(customer=False)
        line = invoice.lines.get()
        line.discount_amount = Decimal("70.00")
        line.line_total = Decimal("0.00")
        line.save(update_fields=["discount_amount", "line_total"])
        invoice.discount_total = Decimal("70.00")
        invoice.grand_total = Decimal("0.00")
        invoice.balance_due = Decimal("0.00")
        invoice.save(update_fields=["discount_total", "grand_total", "balance_due"])

        result = complete_sale(actor=self.actor, sales_invoice_id=invoice.pk)

        self.assertEqual(result.invoice.status, SalesInvoice.Status.COMPLETED)
        self.assertEqual(result.invoice.balance_due, Decimal("0.00"))
        self.assertIsNone(result.initial_payment)
        self.assertFalse(CustomerPayment.objects.exists())

    def test_permission_status_totals_and_warning_are_rechecked_after_invoice_lock(self):
        invoice = self.create_draft()
        with self.assertRaises(PermissionDenied):
            complete_sale(actor=self.unauthorized_user, sales_invoice_id=invoice.pk)

        invoice.subtotal = Decimal("0.01")
        invoice.save(update_fields=["subtotal"])
        with self.assertRaisesMessage(
            ValidationError,
            "The sale totals no longer match its stored lines.",
        ):
            complete_sale(actor=self.actor, sales_invoice_id=invoice.pk)

        invoice.subtotal = invoice.grand_total
        invoice.save(update_fields=["subtotal"])
        line = invoice.lines.get()
        line.prescription_required_snapshot = True
        line.prescription_warning_acknowledged = False
        line.save(
            update_fields=[
                "prescription_required_snapshot",
                "prescription_warning_acknowledged",
            ]
        )
        with self.assertRaisesMessage(ValidationError, "must be acknowledged"):
            complete_sale(actor=self.actor, sales_invoice_id=invoice.pk)

        line.prescription_warning_acknowledged = True
        line.save(update_fields=["prescription_warning_acknowledged"])
        invoice.status = SalesInvoice.Status.VOID
        invoice.save(update_fields=["status"])
        with self.assertRaisesMessage(ValidationError, "Only a draft sale"):
            complete_sale(actor=self.actor, sales_invoice_id=invoice.pk)

        self.assertFalse(SaleBatchAllocation.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_insufficient_stock_and_payment_failure_roll_back_every_write(self):
        insufficient_invoice = self.create_draft(quantity=Decimal("20.000"))
        with self.assertRaises(InsufficientStockError):
            complete_sale(actor=self.actor, sales_invoice_id=insufficient_invoice.pk)

        payment_failure_invoice = self.create_draft()
        with self.assertRaises(ValidationError):
            complete_sale(
                actor=self.actor,
                sales_invoice_id=payment_failure_invoice.pk,
                initial_payment_data=self.payment_data("999.00"),
            )

        for rejected_invoice in (insufficient_invoice, payment_failure_invoice):
            rejected_invoice.refresh_from_db()
            self.assertEqual(rejected_invoice.status, SalesInvoice.Status.DRAFT)
            self.assertEqual(rejected_invoice.invoice_number, "")
        self.first_batch.refresh_from_db()
        self.second_batch.refresh_from_db()
        self.assertEqual(self.first_batch.quantity_available_base, Decimal("4.000"))
        self.assertEqual(self.second_batch.quantity_available_base, Decimal("10.000"))
        self.assertFalse(SaleBatchAllocation.objects.exists())
        self.assertFalse(StockMovement.objects.exists())
        self.assertFalse(CustomerPayment.objects.exists())

    def test_completion_endpoint_is_permission_scoped(self):
        invoice = self.create_draft()
        url = reverse("sales:pos-sale-complete", args=[invoice.pk])

        self.assertEqual(self.client.post(url).status_code, 302)
        self.client.force_login(self.unauthorized_user)
        self.assertEqual(self.client.post(url).status_code, 403)

        self.client.force_login(self.actor)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], SalesInvoice.Status.COMPLETED)
        self.assertEqual(response.json()["invoice_number"], f"SAL-{invoice.id.hex.upper()}")


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locks are required.")
class SaleCompletionConcurrencyTests(TransactionTestCase):
    reset_sequences = False

    def setUp(self):
        user_model = get_user_model()
        self.actor = user_model.objects.create_user(username="concurrent-sale-completer")
        self.actor.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="sales",
                codename="complete_sale",
            )
        )
        category = Category.objects.create(name="Concurrent sale category")
        manufacturer = Manufacturer.objects.create(name="Concurrent sale manufacturer")
        self.medicine = Medicine.objects.create(
            name="Concurrent tablets",
            category=category,
            manufacturer=manufacturer,
            default_selling_price=Decimal("10.0000"),
        )
        self.unit = MedicineUnit.objects.create(
            medicine=self.medicine,
            name="Tablet",
            conversion_to_base=Decimal("1.000000"),
            is_base_unit=True,
        )
        self.customer = Customer.objects.create(
            code="CONCURRENT-CUSTOMER",
            name="Concurrent Customer",
        )
        PharmacySettings.objects.create(
            pharmacy_name="Concurrent Pharmacy",
            currency_code="USD",
        )
        self.batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            batch_number="CONCURRENT-BATCH",
            expiry_date=timezone.localdate() + timedelta(days=30),
            acquisition_cost_per_base_unit=Decimal("2.0000"),
            quantity_available_base=Decimal("10.000"),
            first_received_at=timezone.now(),
        )
        self.invoice_ids = [self.create_draft().pk for _ in range(2)]

    def create_draft(self):
        invoice = SalesInvoice.objects.create(
            customer=self.customer,
            pharmacist=self.actor,
            currency_code="USD",
            subtotal=Decimal("80.00"),
            grand_total=Decimal("80.00"),
            balance_due=Decimal("80.00"),
        )
        SalesInvoiceLine.objects.create(
            sales_invoice=invoice,
            medicine=self.medicine,
            medicine_description_snapshot=self.medicine.name,
            medicine_unit=self.unit,
            unit_name_snapshot=self.unit.name,
            quantity=Decimal("8.000"),
            conversion_to_base_snapshot=Decimal("1.000000"),
            requested_quantity_base=Decimal("8.000"),
            unit_price=Decimal("10.0000"),
            line_total=Decimal("80.00"),
        )
        return invoice

    def test_concurrent_completions_cannot_oversell(self):
        barrier = threading.Barrier(2)
        outcomes = []

        def attempt(invoice_id):
            try:
                actor = get_user_model().objects.get(pk=self.actor.pk)
                barrier.wait(timeout=10)
                complete_sale(actor=actor, sales_invoice_id=invoice_id)
                outcomes.append("completed")
            except InsufficientStockError:
                outcomes.append("insufficient")
            except Exception as error:  # pragma: no cover - asserted below for diagnostics
                outcomes.append(f"unexpected:{type(error).__name__}:{error}")
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=attempt, args=(invoice_id,))
            for invoice_id in self.invoice_ids
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertCountEqual(outcomes, ["completed", "insufficient"])
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available_base, Decimal("2.000"))
        self.assertEqual(
            SalesInvoice.objects.filter(status=SalesInvoice.Status.COMPLETED).count(),
            1,
        )
        self.assertEqual(
            SalesInvoice.objects.filter(status=SalesInvoice.Status.DRAFT).count(),
            1,
        )
        self.assertEqual(
            StockMovement.objects.filter(
                movement_type=StockMovement.MovementType.SALE
            ).count(),
            1,
        )
