"""Guarded, atomic catalog and purchase fixtures for shared DEVELOPMENT data.

This direct historical fixture path exists only for deterministic
development/demo data and must not be used by production request flows.

Invoices/lines are simulated historical records. All batch quantity changes
still go through inventory.receive_purchase_stock with real source records.
No production posting validation is changed, patched, or disabled.
"""

import os
from datetime import datetime, time, timedelta
from decimal import Decimal
from time import perf_counter

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, connection, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.catalog.models import Category, Manufacturer, Medicine, MedicineBarcode, MedicineUnit
from apps.catalog.unit_economics import (
    acquisition_cost_per_base_unit, base_quantity, selected_unit_selling_price,
)
from apps.core.document_numbers import purchase_invoice_number_for_posting
from apps.core.models import PharmacySettings
from apps.inventory.management.demo_dataset import (
    CATEGORIES, CONCEPTS, MANUFACTURERS, MARKER, SUPPLIERS,
    barcode_value, has_barcode, identity, invoice_groups, threshold, unit_specs,
)
from apps.inventory.models import MedicineBatch, StockMovement
from apps.inventory.services import receive_purchase_stock
from apps.parties.models import Supplier
from apps.purchasing.models import PurchaseInvoice, PurchaseInvoiceLine
from apps.purchasing.services import compute_line_amounts


ZERO = Decimal("0.00")


def _save_validated(obj):
    obj.full_clean()
    obj.save()
    return obj


class Command(BaseCommand):
    help = "Create deterministic DEVELOPMENT catalog/stock fixtures; never run in production."

    def add_arguments(self, parser):
        parser.add_argument(
            "--actor", default="owner",
            help="Existing active username for purchase/movement provenance (default: owner).",
        )

    def handle(self, *args, **options):
        self._require_development()
        started_at = perf_counter()
        self._progress("PHARMANEX demo seed\n" + "-" * 32)
        groups = invoice_groups()
        expected = self._expected_ids(groups)
        self._medicine_total = len(expected[Medicine])
        self._receipts_total = len(expected[PurchaseInvoiceLine])
        self._receipts_processed = 0
        self._phase(1, "Existing database & deterministic identities")
        try:
            with transaction.atomic():
                if connection.vendor == "postgresql":
                    # Serialize only competing copies of this seed command, including
                    # the first run when there are no demo rows to lock yet.
                    self._progress("Waiting for the demo-seed transaction lock...")
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [5785218346123])
                # Read counts before the first write; never display URLs/credentials.
                counts = {model: model.objects.count() for model in expected}
                self.stdout.write("Existing database rows (before seed):")
                for model, count in counts.items():
                    self.stdout.write(f"  {model.__name__}: {count}")
                self.stdout.write(f"  MedicineBatch: {MedicineBatch.objects.count()}")
                self.stdout.write(f"  StockMovement: {StockMovement.objects.count()}")

                found = {model: model.objects.filter(pk__in=ids).count() for model, ids in expected.items()}
                existing = any(found.values())
                if existing and any(found[model] != len(ids) for model, ids in expected.items()):
                    raise CommandError(
                        "Incomplete demo dataset or reserved UUID collision. No rows changed. "
                        "Inspect existing demo records; this command never repairs/deletes them automatically."
                    )
                if not existing:
                    actor = get_user_model().objects.filter(
                        username=options["actor"], is_active=True,
                    ).first()
                    if actor is None:
                        raise CommandError("An existing active --actor is required; auth belongs to seed_dev_auth.")
                    pharmacy = PharmacySettings.objects.filter(singleton_key=1).first()
                    if pharmacy is None:
                        raise CommandError("Configure PharmacySettings before seeding; shared settings are never invented.")
                    self._phase_complete("Preflight complete; no existing demo dataset")
                    self._progress(self.style.WARNING(
                        "Creation progress is provisional until the final transaction commits."
                    ))
                    self._create_catalog()
                    self._phase(4, "Suppliers")
                    self._create_suppliers()
                    self._phase_complete(f"Created {len(SUPPLIERS)} demo suppliers")
                    today = timezone.localdate()
                    self._phase(5, "Purchase invoices, batches & movements")
                    for group_index, receipts in enumerate(groups):
                        self._create_historical_purchase(group_index, receipts, actor, pharmacy, today)
                        if (group_index + 1) % 5 == 0:
                            self._progress(f"  Created purchase invoices: {group_index + 1}/{len(groups)}")
                    self._phase_complete(
                        f"Created {len(groups)} invoices; "
                        f"{self._receipts_processed} batches and {self._receipts_processed} movements"
                    )
                else:
                    self._phase_complete("Existing deterministic records detected; creation skipped")
                    for number, label, models in (
                        (2, "Categories & manufacturers", (Category, Manufacturer)),
                        (3, "Medicines, units & barcodes", (Medicine, MedicineUnit, MedicineBarcode)),
                        (4, "Suppliers", (Supplier,)),
                        (5, "Purchase invoices, batches & movements", (PurchaseInvoice, PurchaseInvoiceLine)),
                    ):
                        self._phase(number, label)
                        records = ", ".join(f"{found[model]} {model.__name__}" for model in models)
                        self._phase_complete(f"Existing {records}; creation skipped")

                self._phase(6, "Verification")
                self._verify(expected, groups)
                if not existing:
                    self._progress("Checking initial stock and expiry scenarios...")
                    self._verify_initial_scenarios()
                    self._progress(self.style.SUCCESS("OK: Initial stock and expiry scenarios"))
                self._progress("Calculating final statistics...")
                summary = self._summary(expected)
                self._phase_complete("Demo records verified")
                self._progress("Committing transaction...")
        except (ValidationError, IntegrityError) as error:
            self._report_failure()
            raise CommandError(f"Demo seed rejected; the entire transaction was rolled back: {error}") from error
        except Exception:
            self._report_failure()
            raise

        self.stdout.write("\n" + "-" * 32)
        self.stdout.write(self.style.SUCCESS("PHARMANEX demo data ready"))
        self.stdout.write("-" * 32)
        self.stdout.write(
            "Existing demo rows preserved; no stock added or dates refreshed."
            if existing else "Created fictional development data; not clinical or pricing reference material."
        )
        for label, count in summary.items():
            self.stdout.write(f"{label + ':':<32} {count}")
        self._progress(f"Total time: {perf_counter() - started_at:.1f}s")

    def _progress(self, message):
        self.stdout.write(message)
        # Also show progress promptly when stdout is redirected or buffered.
        self.stdout.flush()

    def _phase(self, number, label):
        self._active_phase = f"[{number}/6] {label}"
        self._phase_started_at = perf_counter()
        self._progress(f"\n{self._active_phase}")

    def _phase_complete(self, message):
        elapsed = perf_counter() - self._phase_started_at
        self._progress(self.style.SUCCESS(f"OK: {message} ({elapsed:.1f}s)"))

    def _report_failure(self):
        # Called after leaving atomic(): report context without swallowing or
        # replacing the existing exception/rollback behavior.
        self.stderr.write(self.style.WARNING(
            f"Failed during {self._active_phase}; seed transaction did not commit."
        ))
        self.stderr.flush()

    def _require_development(self):
        # Render selects config.settings_production through DJANGO_SETTINGS_MODULE.
        # Reject that convention even with DEBUG accidentally on; also respect
        # deployment markers. Unknown environment names fail closed.
        modules = (os.getenv("DJANGO_SETTINGS_MODULE", ""), getattr(settings, "SETTINGS_MODULE", ""))
        if any("production" in str(module).lower() for module in modules) or os.getenv("RENDER", "").lower() == "true":
            raise CommandError("seed_demo_data refused the production settings/deployment environment.")
        allowed = {"", "dev", "development", "local", "test", "testing"}
        markers = ("ENVIRONMENT", "APP_ENV", "DJANGO_ENV", "ENV", "NODE_ENV")
        if not settings.DEBUG:
            raise CommandError("seed_demo_data is development-only and requires DEBUG=True.")
        for name in markers:
            values = (os.environ.get(name, ""), getattr(settings, name, ""))
            if any(str(value).strip().lower() not in allowed for value in values):
                raise CommandError(f"seed_demo_data refused non-development environment marker {name}.")

    def _expected_ids(self, groups):
        return {
            Category: [identity("category", n) for n in range(len(CATEGORIES))],
            Manufacturer: [identity("manufacturer", n) for n in range(len(MANUFACTURERS))],
            Medicine: [identity("medicine", n) for n in range(120)],
            MedicineUnit: [identity("unit", f"{n}:{slot}") for n in range(120) for slot, _ in enumerate(unit_specs(n))],
            MedicineBarcode: [identity("barcode", f"{n}:{slot}") for n in range(120) for slot, _ in enumerate(unit_specs(n)) if has_barcode(n, slot)],
            Supplier: [identity("supplier", n) for n in range(len(SUPPLIERS))],
            PurchaseInvoice: [identity("invoice", n) for n in range(len(groups))],
            PurchaseInvoiceLine: [identity("line", receipt.key) for group in groups for receipt in group],
        }

    def _create_catalog(self):
        self._phase(2, "Categories & manufacturers")
        for index, name in enumerate(CATEGORIES):
            _save_validated(Category(
                id=identity("category", index), name=f"{name} [Demo]", is_active=index != 17,
            ))
        self._progress(self.style.SUCCESS(f"OK: Created {len(CATEGORIES)} categories"))
        for index, name in enumerate(MANUFACTURERS):
            _save_validated(Manufacturer(
                id=identity("manufacturer", index), name=f"{name} [Demo]", is_active=index < 22,
            ))
        self._phase_complete(f"Created {len(MANUFACTURERS)} manufacturers")
        self._phase(3, "Medicines, units & barcodes")
        medicines_created = units_created = barcodes_created = 0
        for index in range(120):
            category, generic, strength_a, strength_b, form = CONCEPTS[index // 2]
            strength = (strength_a, strength_b)[index % 2]
            manufacturer_index = index % 22 if index < 111 else 22 + index % 2
            price = (
                Decimal("0.0500") + Decimal(index % 30) * Decimal("0.0350")
                if index < 60 else Decimal("1.8000") + Decimal(index % 26) * Decimal("0.7000")
            )
            medicine = _save_validated(Medicine(
                id=identity("medicine", index),
                name=f"{generic} {strength} {form} — {'Cedar' if index % 2 == 0 else 'Harbor'} [Demo]",
                generic_name=generic, strength=strength, dosage_form=form,
                category_id=identity("category", category),
                manufacturer_id=identity("manufacturer", manufacturer_index),
                default_selling_price=price, low_stock_threshold_base=threshold(index),
                prescription_required=index % 3 == 0, is_active=index < 111,
            ))
            for slot, (name, conversion) in enumerate(unit_specs(index)):
                unit = _save_validated(MedicineUnit(
                    id=identity("unit", f"{index}:{slot}"), medicine=medicine,
                    name=name, conversion_to_base=conversion, is_base_unit=slot == 0,
                    is_active=slot == 0 or index % 17 != 0,
                    purchase_allowed=True, sale_allowed=slot != 2,
                ))
                units_created += 1
                if has_barcode(index, slot):
                    _save_validated(MedicineBarcode(
                        id=identity("barcode", f"{index}:{slot}"), medicine_unit=unit,
                        barcode=barcode_value(index, slot),
                        is_active=unit.is_active and index % 23 != 0,
                    ))
                    barcodes_created += 1
            medicines_created += 1
            if medicines_created % 25 == 0:
                self._progress(f"  Created medicines with units/barcodes: {medicines_created}/{self._medicine_total}")
        self._phase_complete(
            f"Created {medicines_created} medicines, {units_created} units, {barcodes_created} barcodes"
        )

    def _create_suppliers(self):
        for index, name in enumerate(SUPPLIERS):
            _save_validated(Supplier(
                id=identity("supplier", index), code=f"DEMO-SUP-{index + 1:02d}",
                name=f"{name} [Demo]", contact_person=f"Demo contact {index + 1}",
                email=f"supplier{index + 1}@example.invalid",
                notes=f"{MARKER}: fictional supplier for historical purchase fixtures.",
            ))

    def _create_historical_purchase(self, index, receipts, actor, pharmacy, today):
        """This direct historical fixture path exists only for deterministic
        development/demo data and must not be used by production request flows.

        Current and expired stock both use the real inventory receiving service.
        Only historical invoice construction is special: no fake source UUIDs,
        clock patches, direct quantity writes, or manual-adjustment movements.
        """
        invoice_date = today - timedelta(days=240 + index * 11)
        received_at = timezone.make_aware(datetime.combine(invoice_date, time(10)), timezone.get_default_timezone())
        supplier = Supplier.objects.get(pk=identity("supplier", index % len(SUPPLIERS)))
        invoice = _save_validated(PurchaseInvoice(
            id=identity("invoice", index), supplier=supplier,
            supplier_invoice_reference=f"{MARKER}-PUR-{index + 1:03d}",
            invoice_date=invoice_date, due_date=invoice_date + timedelta(days=30),
            currency_code=pharmacy.currency_code, created_by=actor,
        ))
        invoice.invoice_number = purchase_invoice_number_for_posting(invoice.id)
        totals = [ZERO, ZERO, ZERO, ZERO]
        for receipt in receipts:
            medicine = Medicine.objects.get(pk=identity("medicine", receipt.medicine_index))
            # Prefer an integral pack quantity; do not receive fractional bottles
            # merely to hit the desired base quantity. Base units remain valid.
            units = list(medicine.units.filter(is_active=True, purchase_allowed=True).order_by("-conversion_to_base"))
            unit = next(unit for unit in units if receipt.quantity_base % unit.conversion_to_base == 0)
            quantity = (receipt.quantity_base / unit.conversion_to_base).quantize(Decimal("0.001"))
            ratio = Decimal("0.55") + Decimal(receipt.medicine_index % 20) / Decimal("100") + Decimal(receipt.slot) * Decimal("0.025")
            unit_cost = selected_unit_selling_price(
                medicine.default_selling_price * ratio, unit.conversion_to_base,
            )
            subtotal, tax_amount, line_total = compute_line_amounts(
                quantity=quantity, unit_cost=unit_cost,
                discount_amount=ZERO, tax_rate_percent=Decimal("0.0000"),
            )
            expiry_date = today + timedelta(days=receipt.expiry_days)
            if expiry_date < invoice_date:
                raise CommandError("Historical fixture would receive stock after expiry.")
            line = _save_validated(PurchaseInvoiceLine(
                id=identity("line", receipt.key), purchase_invoice=invoice,
                medicine=medicine, medicine_description_snapshot=medicine.name,
                medicine_unit=unit, unit_name_snapshot=unit.name,
                quantity=quantity, conversion_to_base_snapshot=unit.conversion_to_base,
                received_quantity_base=base_quantity(quantity, unit.conversion_to_base),
                unit_cost=unit_cost, tax_amount=tax_amount, line_total=line_total,
                batch_number=f"DEMO-{receipt.medicine_index + 1:03d}-LOT-{receipt.lot_slot + 1:02d}",
                expiry_date=expiry_date,
            ))
            line.medicine_batch = receive_purchase_stock(
                actor=actor, medicine=medicine, batch_number=line.batch_number,
                expiry_date=line.expiry_date,
                acquisition_cost_per_base_unit=acquisition_cost_per_base_unit(unit_cost, unit.conversion_to_base),
                quantity_base=line.received_quantity_base,
                source_type=StockMovement.MovementType.PURCHASE_RECEIPT,
                source_id=invoice.id, source_line_id=line.id,
                reference_number=invoice.invoice_number, occurred_at=received_at,
            )
            _save_validated(line)
            totals = [a + b for a, b in zip(totals, (subtotal, ZERO, tax_amount, line_total))]
            self._receipts_processed += 1
            if self._receipts_processed % 50 == 0:
                self._progress(
                    f"  Created batches with matching movements: {self._receipts_processed}/{self._receipts_total}"
                )

        invoice.subtotal, invoice.discount_total, invoice.tax_total, invoice.grand_total = totals
        invoice.remaining_balance = invoice.grand_total
        invoice.supplier_name_snapshot = supplier.name
        invoice.pharmacy_name_snapshot = pharmacy.pharmacy_name
        invoice.status = PurchaseInvoice.Status.POSTED
        invoice.payment_status = PurchaseInvoice.PaymentStatus.UNPAID
        invoice.posted_by = actor
        invoice.posted_at = received_at
        _save_validated(invoice)

    def _verify(self, expected, groups):
        """Validate source/accounting chains on first run AND read-only reruns.

        Later legitimate sales/receipts are allowed: current quantities reconcile
        against *all* movement history. Never restore the initial stock snapshot.
        """
        def require(condition, message):
            if not condition:
                raise CommandError(f"Demo integrity check failed: {message}. No rows changed.")

        self._progress("Checking base units, unit ownership and barcodes...")
        for medicine in Medicine.objects.filter(pk__in=expected[Medicine]).prefetch_related("units"):
            bases = [unit for unit in medicine.units.all() if unit.is_active and unit.is_base_unit]
            require(len(bases) == 1 and bases[0].conversion_to_base == 1, "active base unit")
        for index in range(120):
            for slot, _ in enumerate(unit_specs(index)):
                unit = MedicineUnit.objects.get(pk=identity("unit", f"{index}:{slot}"))
                require(unit.medicine_id == identity("medicine", index), "unit ownership")
                if has_barcode(index, slot):
                    barcode = MedicineBarcode.objects.get(pk=identity("barcode", f"{index}:{slot}"))
                    require(barcode.medicine_unit_id == unit.pk, "barcode ownership")
            if (index + 1) % 25 == 0:
                self._progress(f"  Verified medicine units/barcodes: {index + 1}/{len(expected[Medicine])}")
        self._progress(self.style.SUCCESS(f"OK: Units/barcodes verified for {len(expected[Medicine])} demo medicines"))

        invoice_ids = expected[PurchaseInvoice]
        self._progress("Checking batches, movement source keys and stock balances...")
        # Lock batches before reading movements so normal concurrent inventory
        # operations cannot produce a false reconciliation failure on rerun.
        lines = list(
            PurchaseInvoiceLine.objects.filter(pk__in=expected[PurchaseInvoiceLine])
            .select_related("medicine_batch", "medicine_unit")
        )
        batch_ids = {line.medicine_batch_id for line in lines}
        require(None not in batch_ids and len(batch_ids) == len(lines), "missing/merged demo cost layer")
        batches = list(MedicineBatch.objects.select_for_update().filter(pk__in=batch_ids).order_by("pk"))
        movements = list(StockMovement.objects.filter(Q(source_id__in=invoice_ids) | Q(source_line_id__in=expected[PurchaseInvoiceLine])))
        require(len(movements) == len(lines), "missing or extra purchase source movements")
        by_line = {movement.source_line_id: movement for movement in movements}
        require(len(by_line) == len(lines), "duplicate authoritative source keys")
        movement_totals = dict(StockMovement.objects.filter(batch_id__in=batch_ids).values("batch_id").annotate(total=Sum("quantity_delta_base")).values_list("batch_id", "total"))
        for batch in batches:
            require(batch.quantity_available_base >= 0, "negative stock")
            require(batch.quantity_available_base == movement_totals.get(batch.pk), "stock/movement balance")
        self._progress(self.style.SUCCESS(f"OK: Stock invariants verified for {len(batches)} batches"))

        line_map = {line.pk: line for line in lines}
        self._progress("Checking purchase traceability and financial snapshots...")
        for index, group in enumerate(groups):
            invoice = PurchaseInvoice.objects.get(pk=identity("invoice", index))
            require(invoice.status == PurchaseInvoice.Status.POSTED, "purchase status")
            require(invoice.invoice_number == purchase_invoice_number_for_posting(invoice.pk), "invoice number")
            require(invoice.supplier_invoice_reference == f"{MARKER}-PUR-{index + 1:03d}", "invoice ownership marker")
            require(invoice.supplier_id == identity("supplier", index % len(SUPPLIERS)), "supplier ownership")
            require(invoice.posted_by_id is not None and invoice.posted_at is not None, "posting provenance")
            require(bool(invoice.supplier_name_snapshot and invoice.pharmacy_name_snapshot), "purchase snapshots")
            require(timezone.localdate(invoice.posted_at) == invoice.invoice_date, "historical receipt date")
            require(set(invoice.lines.values_list("pk", flat=True)) == {identity("line", receipt.key) for receipt in group}, "invoice lines")
            totals = [ZERO, ZERO, ZERO, ZERO]
            for receipt in group:
                line = line_map[identity("line", receipt.key)]
                batch = line.medicine_batch
                movement = by_line.get(line.pk)
                require(line.medicine_id == identity("medicine", receipt.medicine_index), "line medicine")
                require(line.purchase_invoice_id == invoice.pk, "line parent")
                require(line.medicine_unit.medicine_id == line.medicine_id, "line unit ownership")
                require(line.received_quantity_base == base_quantity(line.quantity, line.conversion_to_base_snapshot), "quantity conversion")
                cost = acquisition_cost_per_base_unit(line.unit_cost, line.conversion_to_base_snapshot)
                require(batch.medicine_id == line.medicine_id and batch.batch_number == line.batch_number and batch.expiry_date == line.expiry_date, "line/batch snapshots")
                require(batch.acquisition_cost_per_base_unit == cost, "acquisition cost conversion")
                require(line.expiry_date >= invoice.invoice_date, "expired at historical receipt")
                require(batch.first_received_at == invoice.posted_at, "first receipt timestamp")
                require(movement is not None, "missing receipt movement")
                require(
                    movement.movement_type == movement.source_type == StockMovement.MovementType.PURCHASE_RECEIPT
                    and movement.source_id == invoice.pk and movement.batch_id == batch.pk
                    and movement.medicine_id == line.medicine_id
                    and movement.quantity_delta_base == line.received_quantity_base
                    and movement.unit_cost_snapshot == cost
                    and movement.reference_number == invoice.invoice_number
                    and movement.performed_by_id == invoice.posted_by_id
                    and movement.occurred_at == invoice.posted_at,
                    "purchase movement traceability",
                )
                subtotal, tax, total = compute_line_amounts(
                    quantity=line.quantity, unit_cost=line.unit_cost,
                    discount_amount=line.discount_amount, tax_rate_percent=line.tax_rate_percent,
                )
                require((tax, total) == (line.tax_amount, line.line_total), "line totals")
                totals = [a + b for a, b in zip(totals, (subtotal, line.discount_amount, tax, total))]
            require(totals == [invoice.subtotal, invoice.discount_total, invoice.tax_total, invoice.grand_total], "invoice totals")
            require(invoice.remaining_balance == invoice.grand_total - invoice.paid_total, "invoice balance")
            if (index + 1) % 5 == 0:
                self._progress(f"  Verified purchase invoices: {index + 1}/{len(groups)}")
        self._progress(self.style.SUCCESS(f"OK: Inventory traceability verified for {len(lines)} purchase lines"))

    def _verify_initial_scenarios(self):
        summary = self._summary(self._expected_ids(invoice_groups()))
        required = ("Healthy sellable stock", "Low stock (0 < qty <= limit)", "No sellable stock", "Medicines without batches", "Multiple-batch medicines", "Expired batches", "Expiry 0-30 days", "Expiry 31-90 days")
        if any(summary[label] == 0 for label in required):
            raise CommandError("Initial demo scenario coverage failed; transaction rolled back.")

    def _summary(self, expected):
        labels = ("Categories", "Manufacturers", "Medicines", "Medicine units", "Barcodes", "Suppliers", "Purchase invoices", "Purchase lines")
        summary = {label: model.objects.filter(pk__in=expected[model]).count() for label, model in zip(labels, expected)}
        batches = MedicineBatch.objects.filter(purchase_invoice_lines__pk__in=expected[PurchaseInvoiceLine]).distinct()
        summary["Batches"] = batches.count()
        summary["Purchase movements"] = StockMovement.objects.filter(source_id__in=expected[PurchaseInvoice]).count()
        medicines = Medicine.objects.filter(pk__in=expected[Medicine]).prefetch_related("batches")
        today = timezone.localdate()
        summary.update({label: 0 for label in ("Healthy sellable stock", "Low stock (0 < qty <= limit)", "No sellable stock", "Medicines without batches", "Multiple-batch medicines")})
        for medicine in medicines:
            rows = list(medicine.batches.all())
            qty = sum((batch.quantity_available_base for batch in rows if batch.is_active and batch.expiry_date >= today), ZERO)
            # All seeded medicines initially have explicit thresholds; preserve
            # later user edits, including choosing the pharmacy fallback.
            limit = medicine.low_stock_threshold_base
            if limit is None:
                pharmacy = PharmacySettings.objects.filter(singleton_key=1).first()
                limit = pharmacy.default_low_stock_threshold if pharmacy else ZERO
            label = "No sellable stock" if qty == 0 else "Low stock (0 < qty <= limit)" if qty <= limit else "Healthy sellable stock"
            summary[label] += 1
            summary["Medicines without batches"] += not rows
            summary["Multiple-batch medicines"] += len(rows) > 1
        summary["Expired batches"] = batches.filter(expiry_date__lt=today).count()
        summary["Expiry 0-30 days"] = batches.filter(expiry_date__range=(today, today + timedelta(days=30))).count()
        summary["Expiry 31-90 days"] = batches.filter(expiry_date__range=(today + timedelta(days=31), today + timedelta(days=90))).count()
        summary["Expiry 91-730 days"] = batches.filter(expiry_date__range=(today + timedelta(days=91), today + timedelta(days=730))).count()
        summary["Expiry over 730 days"] = batches.filter(expiry_date__gt=today + timedelta(days=730)).count()
        summary["Inactive medicines"] = medicines.filter(is_active=False).count()
        return summary
