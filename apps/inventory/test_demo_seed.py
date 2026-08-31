"""Command integration tests: Django creates a disposable test database.

Run with DATABASE_URL=sqlite:///:memory: to avoid even creating a test database
on the shared Neon server. Never invoke this file against a live database.
"""

import os
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Count, Sum
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.catalog.models import Category, Manufacturer, Medicine, MedicineBarcode, MedicineUnit
from apps.catalog.unit_economics import acquisition_cost_per_base_unit, base_quantity
from apps.core.models import PharmacySettings
from apps.finance.models import SupplierPayment
from apps.inventory.management.demo_dataset import barcode_value, identity
from apps.inventory.models import MedicineBatch, StockMovement
from apps.inventory.services import receive_purchase_stock, get_fefo_eligible_batches
from apps.parties.models import Supplier
from apps.purchasing.models import PurchaseInvoice, PurchaseInvoiceLine
from apps.purchasing.services import compute_line_amounts
from apps.sales.models import SaleBatchAllocation, SalesInvoice


COMMAND_MODULE = "apps.inventory.management.commands.seed_demo_data"
MODELS = (Category, Manufacturer, Medicine, MedicineUnit, MedicineBarcode,
          Supplier, PurchaseInvoice, PurchaseInvoiceLine, MedicineBatch, StockMovement)


def run_seed(**kwargs):
    output = StringIO()
    kwargs.setdefault("stderr", StringIO())
    call_command("seed_demo_data", stdout=output, **kwargs)
    return output.getvalue()


def prerequisites():
    actor = get_user_model().objects.create_user(username="owner")
    PharmacySettings.objects.create(pharmacy_name="Shared development pharmacy", currency_code="USD")
    return actor


@override_settings(DEBUG=True)
class DemoDatasetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Fixture setup explicitly opts into the command's development guard.
        with override_settings(DEBUG=True):
            cls.actor = prerequisites()
            cls.output = run_seed()

    def test_counts_and_summary_are_derived_from_created_rows(self):
        expected = (18, 24, 120, 228, 184, 6, 23, 203, 203, 203)
        self.assertEqual(tuple(model.objects.count() for model in MODELS), expected)
        self.assertIn("PHARMANEX demo data ready", self.output)
        for label, value in (("Batches", 203), ("Expired batches", 8), ("Expiry 0-30 days", 14), ("Expiry 31-90 days", 14)):
            self.assertRegex(self.output, rf"{label}:\s+{value}\b")
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertFalse(SupplierPayment.objects.exists())
        self.assertFalse(SalesInvoice.objects.exists())
        self.assertFalse(SaleBatchAllocation.objects.exists())

    def test_creation_reports_phases_chunks_verification_and_timing(self):
        for phase in (
            "Existing database & deterministic identities", "Categories & manufacturers",
            "Medicines, units & barcodes", "Suppliers",
            "Purchase invoices, batches & movements", "Verification",
        ):
            self.assertIn(phase, self.output)
        for progress in ("25/120", "100/120", "5/23", "20/23", "50/203", "200/203"):
            self.assertIn(progress, self.output)
        for signal in (
            "Created 120 medicines", "Stock invariants verified",
            "Inventory traceability verified", "PHARMANEX demo data ready", "Total time:",
        ):
            self.assertIn(signal, self.output)

    def test_rerun_preserves_every_row_and_date_even_later(self):
        before = {model: list(model.objects.order_by("pk").values()) for model in MODELS}
        original_localdate = timezone.localdate
        def later_date(value=None, timezone=None):
            return original_localdate(value, timezone) if value is not None else original_localdate() + timedelta(days=450)
        with patch(f"{COMMAND_MODULE}.timezone.localdate", side_effect=later_date):
            output = run_seed()
        self.assertIn("Existing demo rows preserved", output)
        self.assertIn("Existing deterministic records detected", output)
        self.assertIn("creation skipped", output)
        self.assertIn("Stock invariants verified", output)
        self.assertIn("Inventory traceability verified", output)
        self.assertIn("PHARMANEX demo data ready", output)
        self.assertNotIn("Created ", output)
        for model in MODELS:
            self.assertEqual(list(model.objects.order_by("pk").values()), before[model])

    def test_base_units_and_barcode_relationships(self):
        unit_counts = set()
        for medicine in Medicine.objects.prefetch_related("units"):
            bases = [unit for unit in medicine.units.all() if unit.is_active and unit.is_base_unit]
            self.assertEqual(len(bases), 1)
            self.assertEqual(bases[0].conversion_to_base, Decimal("1.000000"))
            unit_counts.add(medicine.units.count())
        self.assertEqual(unit_counts, {1, 2, 3})
        codes = list(MedicineBarcode.objects.values_list("barcode", flat=True))
        self.assertEqual(len(codes), len(set(codes)))
        for code in codes:
            self.assertEqual(len(code), 13)
            weighted = sum(int(digit) * (1 if n % 2 == 0 else 3) for n, digit in enumerate(code[:-1]))
            self.assertEqual((-weighted) % 10, int(code[-1]))
        self.assertTrue(MedicineBarcode.objects.filter(is_active=False).exists())
        self.assertTrue(MedicineUnit.objects.filter(is_active=False, is_base_unit=False).exists())
        self.assertEqual(Medicine.objects.filter(is_active=False).count(), 9)
        self.assertTrue(Medicine.objects.filter(prescription_required=True).exists())
        self.assertTrue(Medicine.objects.filter(prescription_required=False).exists())

    def test_stock_and_expiry_scenarios(self):
        today = timezone.localdate()
        above = equal = below = zero = no_batches = expired_only = multiple = 0
        for medicine in Medicine.objects.prefetch_related("batches"):
            batches = list(medicine.batches.all())
            qty = sum((batch.quantity_available_base for batch in get_fefo_eligible_batches(medicine)), Decimal("0.000"))
            above += qty > medicine.low_stock_threshold_base
            equal += qty == medicine.low_stock_threshold_base
            below += 0 < qty < medicine.low_stock_threshold_base
            zero += qty == 0
            no_batches += not batches
            expired_only += bool(batches) and all(batch.expiry_date < today for batch in batches)
            multiple += len(batches) > 1
            ordered = list(get_fefo_eligible_batches(medicine))
            self.assertEqual(ordered, sorted(ordered, key=lambda batch: (batch.expiry_date, batch.first_received_at, batch.pk)))
        self.assertEqual((above, equal, below, zero, no_batches, expired_only, multiple), (84, 7, 14, 15, 11, 4, 84))
        self.assertTrue(MedicineBatch.objects.filter(expiry_date=today).exists())
        self.assertTrue(MedicineBatch.objects.filter(expiry_date__gt=today + timedelta(days=730)).exists())
        for batch in MedicineBatch.objects.select_related("medicine"):
            self.assertGreaterEqual(batch.quantity_available_base, 0)
            self.assertLess(batch.acquisition_cost_per_base_unit, batch.medicine.default_selling_price)
            self.assertEqual(batch.acquisition_cost_per_base_unit, batch.acquisition_cost_per_base_unit.quantize(Decimal("0.0001")))
            batch.full_clean()
        layers = MedicineBatch.objects.values("medicine_id", "batch_number", "expiry_date").annotate(n=Count("id"))
        self.assertTrue(layers.filter(n__gt=1).exists())

    def test_complete_authoritative_chain_and_financial_snapshots(self):
        for invoice in PurchaseInvoice.objects.prefetch_related("lines"):
            self.assertEqual(invoice.status, PurchaseInvoice.Status.POSTED)
            self.assertEqual(invoice.payment_status, PurchaseInvoice.PaymentStatus.UNPAID)
            self.assertEqual(invoice.paid_total, Decimal("0.00"))
            self.assertEqual(invoice.remaining_balance, invoice.grand_total)
            self.assertEqual(invoice.pharmacy_name_snapshot, "Shared development pharmacy")
            self.assertEqual(invoice.currency_code, "USD")
            self.assertEqual(timezone.localdate(invoice.posted_at), invoice.invoice_date)
            self.assertLessEqual(invoice.lines.count(), 9)
            totals = [Decimal("0.00")] * 4
            for line in invoice.lines.select_related("medicine_batch", "medicine_unit"):
                line.full_clean()
                batch = line.medicine_batch
                self.assertGreaterEqual(line.expiry_date, invoice.invoice_date)
                self.assertEqual(line.received_quantity_base, base_quantity(line.quantity, line.conversion_to_base_snapshot))
                self.assertEqual(batch.acquisition_cost_per_base_unit, acquisition_cost_per_base_unit(line.unit_cost, line.conversion_to_base_snapshot))
                movement = StockMovement.objects.get(source_id=invoice.pk, source_line_id=line.pk)
                self.assertEqual(movement.movement_type, StockMovement.MovementType.PURCHASE_RECEIPT)
                self.assertEqual(movement.source_type, StockMovement.MovementType.PURCHASE_RECEIPT)
                self.assertEqual(movement.batch_id, batch.pk)
                self.assertEqual(movement.medicine_id, line.medicine_id)
                self.assertEqual(movement.quantity_delta_base, line.received_quantity_base)
                self.assertEqual(movement.unit_cost_snapshot, batch.acquisition_cost_per_base_unit)
                self.assertEqual(movement.reference_number, invoice.invoice_number)
                self.assertEqual(movement.performed_by_id, invoice.posted_by_id)
                self.assertEqual(movement.occurred_at, invoice.posted_at)
                self.assertEqual(batch.stock_movements.aggregate(total=Sum("quantity_delta_base"))["total"], batch.quantity_available_base)
                subtotal, tax, total = compute_line_amounts(quantity=line.quantity, unit_cost=line.unit_cost, discount_amount=line.discount_amount, tax_rate_percent=line.tax_rate_percent)
                self.assertEqual((tax, total), (line.tax_amount, line.line_total))
                totals = [a + b for a, b in zip(totals, (subtotal, line.discount_amount, tax, total))]
            self.assertEqual(totals, [invoice.subtotal, invoice.discount_total, invoice.tax_total, invoice.grand_total])
        keys = StockMovement.objects.values("movement_type", "source_type", "source_id", "source_line_id").annotate(n=Count("id"))
        self.assertFalse(keys.filter(n__gt=1).exists())

    def test_rerun_preserves_manual_catalog_edits_and_ordinary_data(self):
        medicine = Medicine.objects.get(pk=identity("medicine", 0))
        medicine.name = "Team edited demo product"
        medicine.default_selling_price = Decimal("9.1234")
        medicine.save()
        category = Category.objects.create(name="Team category")
        manufacturer = Manufacturer.objects.create(name="Team manufacturer")
        ordinary = Medicine.objects.create(name="Team medicine", category=category, manufacturer=manufacturer)
        run_seed()
        medicine.refresh_from_db()
        self.assertEqual(medicine.name, "Team edited demo product")
        self.assertEqual(medicine.default_selling_price, Decimal("9.1234"))
        self.assertTrue(Medicine.objects.filter(pk=ordinary.pk).exists())

    def test_rerun_does_not_replenish_stock_after_supplier_return(self):
        from apps.core.document_numbers import supplier_return_number_for_creation
        from apps.inventory.services import deduct_supplier_return
        from apps.returns.models import ReturnStatus, SupplierReturn, SupplierReturnLine

        line = PurchaseInvoiceLine.objects.select_related("purchase_invoice", "medicine_batch").first()
        batch = line.medicine_batch
        returned = SupplierReturn(
            supplier=line.purchase_invoice.supplier, purchase_invoice=line.purchase_invoice,
            reason="Test supplier return", processed_by=self.actor,
            status=ReturnStatus.POSTED, posted_at=timezone.now(),
            return_total=batch.acquisition_cost_per_base_unit.quantize(Decimal("0.01")),
        )
        returned.return_number = supplier_return_number_for_creation(returned.pk)
        returned.save()
        return_line = SupplierReturnLine.objects.create(
            supplier_return=returned, medicine=line.medicine, batch=batch,
            returned_quantity_base=Decimal("1.000"),
            unit_cost_snapshot=batch.acquisition_cost_per_base_unit,
            line_total=returned.return_total,
        )
        deduct_supplier_return(
            actor=self.actor, batch=batch, quantity_base=return_line.returned_quantity_base,
            source_type="SUPPLIER_RETURN", source_id=returned.pk,
            source_line_id=return_line.pk, reference_number=returned.return_number,
        )
        before = list(MedicineBatch.objects.order_by("pk").values())
        movements = StockMovement.objects.count()
        run_seed()
        self.assertEqual(list(MedicineBatch.objects.order_by("pk").values()), before)
        self.assertEqual(StockMovement.objects.count(), movements)

    def test_corrupt_history_is_reported_not_repaired(self):
        line = PurchaseInvoiceLine.objects.first()
        movement = StockMovement.objects.get(source_line_id=line.pk)
        movement.reference_number = "BROKEN-REFERENCE"
        movement.save(update_fields=["reference_number"])
        with self.assertRaisesMessage(CommandError, "traceability"):
            run_seed()
        movement.refresh_from_db()
        self.assertEqual(movement.reference_number, "BROKEN-REFERENCE")

    def test_missing_demo_record_is_not_silently_recreated(self):
        MedicineBarcode.objects.first().delete()
        with self.assertRaisesMessage(CommandError, "Incomplete demo dataset"):
            run_seed()
        self.assertEqual(MedicineBarcode.objects.count(), 183)

    def test_unexplained_quantity_is_reported_not_repaired(self):
        batch = MedicineBatch.objects.first()
        # Deliberate corruption in the disposable test database, never a seed
        # mechanism. A command rerun must detect rather than normalize this.
        batch.quantity_available_base += Decimal("1.000")
        batch.save(update_fields=["quantity_available_base"])
        with self.assertRaisesMessage(CommandError, "stock/movement balance"):
            run_seed()
        batch.refresh_from_db()
        recorded = batch.stock_movements.aggregate(total=Sum("quantity_delta_base"))["total"]
        self.assertEqual(batch.quantity_available_base, recorded + Decimal("1.000"))


@override_settings(DEBUG=True)
class DemoSeedSafetyTests(TestCase):
    def setUp(self):
        self.actor = prerequisites()

    def test_debug_false_refuses_before_database_access(self):
        with override_settings(DEBUG=False), self.assertNumQueries(0):
            with self.assertRaisesMessage(CommandError, "development-only"):
                run_seed()

    def test_production_environment_refuses_even_with_debug_true(self):
        for name in ("ENVIRONMENT", "APP_ENV", "DJANGO_ENV", "ENV", "NODE_ENV"):
            with self.subTest(name=name), patch.dict(os.environ, {name: "production"}), self.assertNumQueries(0):
                with self.assertRaisesMessage(CommandError, "non-development"):
                    run_seed()

    def test_production_settings_and_render_refuse_even_with_debug_true(self):
        for markers in ({"DJANGO_SETTINGS_MODULE": "config.settings_production"}, {"RENDER": "true"}):
            with self.subTest(markers=markers), patch.dict(os.environ, markers), self.assertNumQueries(0):
                with self.assertRaisesMessage(CommandError, "production settings/deployment"):
                    run_seed()

    def test_existing_actor_and_settings_are_required_without_mutating_auth(self):
        with self.assertRaisesMessage(CommandError, "active --actor"):
            run_seed(actor="missing-user")
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertFalse(Category.objects.exists())
        PharmacySettings.objects.get(singleton_key=1).delete()  # Disposable test DB only.
        with self.assertRaisesMessage(CommandError, "PharmacySettings"):
            run_seed()
        self.assertFalse(Category.objects.exists())

    def test_ordinary_category_name_collision_rolls_back(self):
        category = Category.objects.create(name="analgesics [demo]")
        with self.assertRaisesMessage(CommandError, "rolled back"):
            run_seed()
        self.assertEqual(list(Category.objects.values_list("pk", flat=True)), [category.pk])
        self.assertFalse(Manufacturer.objects.exists())
        self.assertFalse(PurchaseInvoice.objects.exists())

    def test_late_inventory_failure_rolls_back_complete_fixture_chain(self):
        count = 0
        class FlushedOutput(StringIO):
            flushed_text = ""

            def flush(self):
                self.flushed_text = self.getvalue()
                super().flush()

        output = FlushedOutput()
        errors = StringIO()
        def fail_after_receipts(**kwargs):
            nonlocal count
            count += 1
            if count == 4:
                self.assertIn("Purchase invoices, batches & movements", output.flushed_text)
                raise ValidationError("deliberate late fixture failure")
            return receive_purchase_stock(**kwargs)
        with patch(f"{COMMAND_MODULE}.receive_purchase_stock", side_effect=fail_after_receipts):
            with self.assertRaisesMessage(CommandError, "rolled back"):
                call_command("seed_demo_data", stdout=output, stderr=errors)
        self.assertEqual(count, 4)
        self.assertIn("Failed during", errors.getvalue())
        self.assertIn("Purchase invoices, batches & movements", errors.getvalue())
        self.assertNotIn("PHARMANEX demo data ready", output.getvalue())
        for model in MODELS:
            self.assertEqual(model.objects.count(), 0)
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(PharmacySettings.objects.count(), 1)

    def test_unexpected_failure_keeps_its_exception_and_phase_context(self):
        error = RuntimeError("unexpected supplier failure")
        errors = StringIO()
        output = StringIO()
        with patch(f"{COMMAND_MODULE}.Command._create_suppliers", side_effect=error):
            with self.assertRaises(RuntimeError) as raised:
                call_command("seed_demo_data", stdout=output, stderr=errors)
        self.assertIs(raised.exception, error)
        self.assertIn("Suppliers", errors.getvalue())
        self.assertNotIn("PHARMANEX demo data ready", output.getvalue())
        for model in MODELS:
            self.assertEqual(model.objects.count(), 0)

    def test_existing_barcode_collision_preserves_team_data_and_rolls_back(self):
        category = Category.objects.create(name="Team category")
        manufacturer = Manufacturer.objects.create(name="Team manufacturer")
        medicine = Medicine.objects.create(name="Team medicine", category=category, manufacturer=manufacturer)
        unit = MedicineUnit.objects.create(
            medicine=medicine, name="Tablet", is_base_unit=True,
            conversion_to_base=Decimal("1.000000"),
        )
        barcode = MedicineBarcode.objects.create(medicine_unit=unit, barcode=barcode_value(0, 0))
        before = {model: list(model.objects.order_by("pk").values()) for model in MODELS}
        with self.assertRaisesMessage(CommandError, "rolled back"):
            run_seed()
        for model in MODELS:
            self.assertEqual(list(model.objects.order_by("pk").values()), before[model])
        self.assertEqual(MedicineBarcode.objects.get(pk=barcode.pk).medicine_unit_id, unit.pk)

    def test_partial_seed_identity_refuses_without_adopting_ordinary_rows(self):
        category = Category.objects.create(id=identity("category", 0), name="Unrelated data at reserved UUID")
        with self.assertRaisesMessage(CommandError, "Incomplete demo dataset"):
            run_seed()
        self.assertEqual(list(Category.objects.values_list("pk", flat=True)), [category.pk])
