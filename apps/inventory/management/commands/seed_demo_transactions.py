"""Guarded second-wave transactional fixtures for DEVELOPMENT databases only.

The command requires the V1 ``seed_demo_data`` records and never creates or
repairs them. Sales and payments use their production services. Historical
business timestamps are applied only after those services succeed, inside this
single fixture transaction; inventory quantities and movements are never
written directly.
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
from django.db.models import Count, Sum
from django.utils import timezone

from apps.catalog.models import Medicine
from apps.core.models import PaymentMethod, PharmacySettings
from apps.finance.models import CustomerPayment, PaymentStatus, SupplierPayment
from apps.finance.services import (
    post_customer_payment,
    post_supplier_payment,
    reverse_customer_payment,
    reverse_supplier_payment,
)
from apps.inventory.management.demo_dataset import (
    SUPPLIERS,
    identity as base_identity,
    invoice_groups,
)
from apps.inventory.management.transaction_demo_dataset import (
    COMPLETED_SALE_COUNT,
    CUSTOMER_COUNT,
    DRAFT_SALE_COUNT,
    MARKER,
    MULTI_BATCH_SALE_COUNT,
    PAID_PURCHASE_COUNT,
    PAID_SAVED_SALE_COUNT,
    PARTIAL_PURCHASE_COUNT,
    PARTIAL_SAVED_SALE_COUNT,
    PRESCRIBER_COUNT,
    PRESCRIPTION_COUNT,
    PRESCRIPTION_ITEMS_PER_RECORD,
    PRESCRIPTION_LINKED_SALE_COUNT,
    REVERSED_CUSTOMER_PAYMENT_COUNT,
    REVERSED_SUPPLIER_PAYMENT_COUNT,
    UNPAID_SAVED_SALE_COUNT,
    WALK_IN_SALE_COUNT,
    transaction_identity,
)
from apps.inventory.models import MedicineBatch, StockMovement
from apps.inventory.services import InsufficientStockError, get_fefo_eligible_batches
from apps.parties.models import Customer, Prescriber, Supplier
from apps.prescriptions.models import Prescription, PrescriptionItem
from apps.purchasing.models import PurchaseInvoice
from apps.sales.models import SaleBatchAllocation, SalesInvoice, SalesInvoiceLine
from apps.sales.services import complete_sale, process_draft_sale


ZERO_MONEY = Decimal("0.00")
REQUIRED_PERMISSIONS = (
    "sales.change_salesinvoice",
    "sales.change_salesinvoiceline",
    "sales.complete_sale",
    "finance.post_customerpayment",
    "finance.post_supplierpayment",
)


def _save_validated(obj):
    obj.full_clean()
    obj.save()
    return obj


def _completed_sale_days_ago(index):
    """Spread 84 sales over about seven months, after every V1 receipt date."""
    return 220 - index * 2 - index // 2


class Command(BaseCommand):
    help = (
        "Create deterministic DEVELOPMENT sales, prescription and payment fixtures; "
        "requires seed_demo_data and never runs in production."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--actor",
            default="owner",
            help="Existing active, permitted username for transaction provenance.",
        )

    def handle(self, *args, **options):
        self._require_development()
        started_at = perf_counter()
        self.stdout.write("PHARMANEX transactional demo seed\n" + "-" * 38)
        expected = self._expected_ids()

        try:
            with transaction.atomic():
                if connection.vendor == "postgresql":
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [6493251292026])

                self._phase("Preflight and deterministic identities")
                found = {
                    model: model.objects.filter(pk__in=ids).count()
                    for model, ids in expected.items()
                }
                existing = any(found.values())
                if existing and any(
                    found[model] != len(ids) for model, ids in expected.items()
                ):
                    raise CommandError(
                        "Incomplete transactional demo dataset or reserved UUID collision. "
                        "No rows changed; the command never repairs or deletes shared data."
                    )
                actor, pharmacy, payment_method = self._preflight(
                    options["actor"], require_creation=not existing
                )

                if not existing:
                    self._require_unpaid_target_purchases()
                    self.stdout.write(
                        self.style.WARNING(
                            "Creation is provisional until the outer transaction commits."
                        )
                    )
                    candidates, multi_batch_candidates = self._stock_candidates(pharmacy)
                    self._phase("Customers and prescribers")
                    self._create_parties()
                    self._phase("Prescriptions")
                    prescription_medicines = self._create_prescriptions(
                        actor, candidates, multi_batch_candidates
                    )
                    self._phase("Historical sales and customer payments")
                    self._create_sales(
                        actor,
                        pharmacy,
                        payment_method,
                        candidates,
                        multi_batch_candidates,
                        prescription_medicines,
                    )
                    self._phase("Historical supplier payments")
                    self._create_supplier_payments(actor, payment_method)
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            "Complete V2 deterministic records detected; creation skipped."
                        )
                    )

                self._phase("Verification")
                self._verify(expected, pharmacy)
                summary = self._summary(expected)
        except (ValidationError, IntegrityError, InsufficientStockError) as error:
            raise CommandError(
                f"Transactional demo seed rejected during {self._active_phase}; "
                f"the entire transaction was rolled back: {error}"
            ) from error

        self.stdout.write("\n" + "-" * 38)
        self.stdout.write(self.style.SUCCESS("PHARMANEX transactional demo data ready"))
        self.stdout.write("-" * 38)
        self.stdout.write(
            "Existing V2 records preserved; no stock or timestamps changed."
            if existing
            else "Created fictional transactional development data through production services."
        )
        for label, value in summary.items():
            self.stdout.write(f"{label + ':':<36} {value}")
        self.stdout.write(
            "Returns seeded:                      0 (posting/refund services unavailable)"
        )
        self.stdout.write(f"Total time: {perf_counter() - started_at:.1f}s")

    def _phase(self, label):
        self._active_phase = label
        self.stdout.write(f"\n{label}")
        self.stdout.flush()

    def _require_development(self):
        modules = (
            os.getenv("DJANGO_SETTINGS_MODULE", ""),
            getattr(settings, "SETTINGS_MODULE", ""),
        )
        if any("production" in str(module).lower() for module in modules) or os.getenv(
            "RENDER", ""
        ).lower() == "true":
            raise CommandError(
                "seed_demo_transactions refused the production settings/deployment environment."
            )
        allowed = {"", "dev", "development", "local", "test", "testing"}
        if not settings.DEBUG:
            raise CommandError(
                "seed_demo_transactions is development-only and requires DEBUG=True."
            )
        for name in ("ENVIRONMENT", "APP_ENV", "DJANGO_ENV", "ENV", "NODE_ENV"):
            values = (os.environ.get(name, ""), getattr(settings, name, ""))
            if any(str(value).strip().lower() not in allowed for value in values):
                raise CommandError(
                    f"seed_demo_transactions refused non-development environment marker {name}."
                )

    def _expected_ids(self):
        sale_total = COMPLETED_SALE_COUNT + DRAFT_SALE_COUNT
        return {
            Customer: [transaction_identity("customer", i) for i in range(CUSTOMER_COUNT)],
            Prescriber: [
                transaction_identity("prescriber", i) for i in range(PRESCRIBER_COUNT)
            ],
            Prescription: [
                transaction_identity("prescription", i)
                for i in range(PRESCRIPTION_COUNT)
            ],
            PrescriptionItem: [
                transaction_identity("prescription-item", f"{i}:{slot}")
                for i in range(PRESCRIPTION_COUNT)
                for slot in range(PRESCRIPTION_ITEMS_PER_RECORD)
            ],
            SalesInvoice: [
                transaction_identity("sale", i) for i in range(sale_total)
            ],
        }

    def _preflight(self, username, *, require_creation):
        pharmacy = PharmacySettings.objects.filter(singleton_key=1).first()
        if pharmacy is None:
            raise CommandError("Configure PharmacySettings before seeding transactions.")

        base_checks = (
            (Medicine, [base_identity("medicine", i) for i in range(120)]),
            (Supplier, [base_identity("supplier", i) for i in range(len(SUPPLIERS))]),
            (
                PurchaseInvoice,
                [base_identity("invoice", i) for i in range(len(invoice_groups()))],
            ),
        )
        for model, ids in base_checks:
            if model.objects.filter(pk__in=ids).count() != len(ids):
                raise CommandError(
                    "The complete V1 seed_demo_data dataset is required before V2 transactions."
                )

        if not require_creation:
            return None, pharmacy, None

        actor = get_user_model().objects.filter(username=username, is_active=True).first()
        if actor is None:
            raise CommandError("An existing active --actor is required.")
        missing = [
            permission
            for permission in REQUIRED_PERMISSIONS
            if not actor.has_perm(permission)
        ]
        if missing:
            raise CommandError(
                "The transaction actor lacks required service permissions: "
                + ", ".join(missing)
            )
        payment_method = (
            PaymentMethod.objects.filter(is_active=True).order_by("name", "pk").first()
        )
        if payment_method is None:
            raise CommandError("At least one active PaymentMethod is required.")
        return actor, pharmacy, payment_method

    def _require_unpaid_target_purchases(self):
        target_purchase_ids = [
            base_identity("invoice", i)
            for i in range(PAID_PURCHASE_COUNT + PARTIAL_PURCHASE_COUNT)
        ]
        if SupplierPayment.objects.filter(
            purchase_invoice_id__in=target_purchase_ids
        ).exists():
            raise CommandError(
                "Target demo purchases already have payments but V2 identities are absent; "
                "no payments were adopted or changed."
            )

    def _stock_candidates(self, pharmacy):
        today = timezone.localdate()
        candidates = []
        multi_batch = []
        for index in range(111):
            medicine = Medicine.objects.get(pk=base_identity("medicine", index))
            batches = list(get_fefo_eligible_batches(medicine))
            sellable = sum(
                (batch.quantity_available_base for batch in batches), Decimal("0.000")
            )
            threshold = (
                medicine.low_stock_threshold_base
                if medicine.low_stock_threshold_base is not None
                else pharmacy.default_low_stock_threshold
            )
            if (
                batches
                and batches[0].expiry_date > today + timedelta(days=90)
                and sellable - threshold >= Decimal("30.000")
            ):
                candidates.append(medicine)
                if (
                    len(batches) > 1
                    and sellable - batches[0].quantity_available_base > threshold
                ):
                    multi_batch.append(medicine)
        if len(candidates) < 24 or len(multi_batch) < MULTI_BATCH_SALE_COUNT:
            raise CommandError(
                "Current V1 stock cannot support the conservative V2 sales while preserving "
                "low/out-of-stock and expiry scenarios."
            )
        if not any(medicine.prescription_required for medicine in candidates):
            raise CommandError(
                "No safely stocked prescription-required demo medicine is available."
            )
        return candidates, multi_batch[:MULTI_BATCH_SALE_COUNT]

    def _create_parties(self):
        for index in range(CUSTOMER_COUNT):
            _save_validated(
                Customer(
                    id=transaction_identity("customer", index),
                    code=f"DEMO-CUST-{index + 1:03d}",
                    name=f"Demo Customer {index + 1:02d} [Demo]",
                    phone=f"+000555{index + 1:04d}",
                    email=f"customer{index + 1:02d}@example.invalid",
                    notes=f"{MARKER}: fictional customer for UI and reporting tests.",
                )
            )
        for index in range(PRESCRIBER_COUNT):
            _save_validated(
                Prescriber(
                    id=transaction_identity("prescriber", index),
                    name=f"Demo Prescriber {index + 1:02d} [Demo]",
                    phone=f"+000777{index + 1:04d}",
                    professional_identifier=f"DEMO-LIC-{index + 1:04d}",
                    notes=f"{MARKER}: fictional prescriber; not a clinical identity.",
                )
            )
        self.stdout.write(
            f"Created {CUSTOMER_COUNT} customers and {PRESCRIBER_COUNT} prescribers."
        )

    def _prescription_medicines(self, candidates, multi_batch_candidates, index):
        first = (
            multi_batch_candidates[index]
            if index < len(multi_batch_candidates)
            else candidates[(index * 5) % len(candidates)]
        )
        if (
            index >= len(multi_batch_candidates)
            and index % 2 == 0
            and not first.prescription_required
        ):
            first = next(
                medicine
                for medicine in candidates
                if medicine.prescription_required and medicine not in multi_batch_candidates
            )
        second = candidates[(index * 5 + 11) % len(candidates)]
        if second.pk == first.pk:
            second = candidates[(index * 5 + 12) % len(candidates)]
        return first, second

    def _create_prescriptions(self, actor, candidates, multi_batch_candidates):
        today = timezone.localdate()
        result = {}
        for index in range(PRESCRIPTION_COUNT):
            days_ago = (
                _completed_sale_days_ago(index) + 5
                if index < PRESCRIPTION_LINKED_SALE_COUNT
                else 150 - (index - PRESCRIPTION_LINKED_SALE_COUNT) * 10
            )
            prescription_date = today - timedelta(days=days_ago)
            created_at = timezone.make_aware(
                datetime.combine(prescription_date, time(9, 15)),
                timezone.get_default_timezone(),
            )
            prescription = _save_validated(
                Prescription(
                    id=transaction_identity("prescription", index),
                    reference_number=f"{MARKER}-RX-{index + 1:03d}",
                    customer_id=transaction_identity("customer", index % CUSTOMER_COUNT),
                    prescriber_id=transaction_identity(
                        "prescriber", index % PRESCRIBER_COUNT
                    ),
                    prescription_date=prescription_date,
                    notes=f"{MARKER}: fictional prescription record for interface testing only.",
                    created_by=actor,
                )
            )
            medicines = self._prescription_medicines(
                candidates, multi_batch_candidates, index
            )
            result[index] = medicines
            for slot, medicine in enumerate(medicines):
                _save_validated(
                    PrescriptionItem(
                        id=transaction_identity("prescription-item", f"{index}:{slot}"),
                        prescription=prescription,
                        medicine=medicine,
                        quantity_prescribed=Decimal(f"{slot + 1}.000"),
                        dosage_instructions="Demo directions — testing fixture only.",
                        notes=f"{MARKER}: no medical advice.",
                    )
                )
            Prescription.objects.filter(pk=prescription.pk).update(
                created_at=created_at, updated_at=created_at
            )
            PrescriptionItem.objects.filter(prescription=prescription).update(
                created_at=created_at, updated_at=created_at
            )
        self.stdout.write(
            f"Created {PRESCRIPTION_COUNT} prescriptions and "
            f"{PRESCRIPTION_COUNT * PRESCRIPTION_ITEMS_PER_RECORD} items."
        )
        return result

    def _available_quantity(self, medicine):
        return sum(
            (batch.quantity_available_base for batch in get_fefo_eligible_batches(medicine)),
            Decimal("0.000"),
        )

    def _ordinary_line(self, candidates, start, used, pharmacy, prefer_pack):
        for offset in range(len(candidates)):
            medicine = candidates[(start + offset) % len(candidates)]
            if medicine.pk in used:
                continue
            units = list(
                medicine.units.filter(is_active=True, sale_allowed=True).order_by(
                    "-conversion_to_base", "pk"
                )
            )
            unit = units[0] if prefer_pack and len(units) > 1 else next(
                value for value in units if value.is_base_unit
            )
            requested = unit.conversion_to_base
            threshold = medicine.low_stock_threshold_base or pharmacy.default_low_stock_threshold
            if self._available_quantity(medicine) - requested > threshold:
                return medicine, unit, Decimal("1.000")
        raise CommandError("Safe sale-line planning exhausted the reserved healthy stock pool.")

    def _sale_form_data(self, customer, prescription, lines):
        data = {
            "customer": str(customer.pk) if customer else "",
            "prescription": str(prescription.pk) if prescription else "",
            "lines-TOTAL_FORMS": str(len(lines)),
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
        }
        for slot, (medicine, unit, quantity) in enumerate(lines):
            data.update(
                {
                    f"lines-{slot}-medicine": str(medicine.pk),
                    f"lines-{slot}-medicine_unit": str(unit.pk),
                    f"lines-{slot}-quantity": str(quantity),
                    f"lines-{slot}-discount_amount": "0.00",
                }
            )
            if medicine.prescription_required:
                data[f"lines-{slot}-prescription_warning_acknowledged"] = "on"
        return data

    def _raise_form_error(self, label, form, formset=None):
        details = form.errors.as_json()
        if formset is not None:
            details += " " + str(formset.errors) + " " + str(formset.non_form_errors())
        raise CommandError(f"{label} was rejected by the production service: {details}")

    def _post_customer_payment(self, actor, invoice, method, amount, paid_at, reference):
        try:
            form, payment = post_customer_payment(
                actor=actor,
                sales_invoice=invoice,
                data={
                    "payment_method": str(method.pk),
                    "amount": str(amount),
                    "reference": reference,
                    "paid_at": paid_at,
                },
            )
        except ValidationError as error:
            raise CommandError(
                f"Customer payment service failed for {invoice.pk}: "
                f"grand_total={invoice.grand_total}, amount={amount}, error={error}"
            ) from error
        if payment is None:
            self._raise_form_error("Customer payment", form)
        CustomerPayment.objects.filter(pk=payment.pk).update(created_at=paid_at)
        return payment

    def _create_sales(
        self,
        actor,
        pharmacy,
        payment_method,
        candidates,
        multi_batch_candidates,
        prescription_medicines,
    ):
        today = timezone.localdate()
        saved_sale_count = COMPLETED_SALE_COUNT - WALK_IN_SALE_COUNT
        if saved_sale_count != (
            PAID_SAVED_SALE_COUNT
            + PARTIAL_SAVED_SALE_COUNT
            + UNPAID_SAVED_SALE_COUNT
        ):
            raise CommandError("Transactional sale distribution constants are inconsistent.")

        higher_value_candidates = [
            medicine
            for medicine in candidates
            if any(
                unit.conversion_to_base > 1
                and (
                    medicine.default_selling_price * unit.conversion_to_base
                )
                % Decimal("1.0000")
                == 0
                for unit in medicine.units.filter(is_active=True, sale_allowed=True)
            )
        ]
        if len(higher_value_candidates) < 3:
            raise CommandError("Not enough higher-value healthy stock for partial-payment sales.")

        for index in range(COMPLETED_SALE_COUNT + DRAFT_SALE_COUNT):
            is_completed = index < COMPLETED_SALE_COUNT
            customer = (
                Customer.objects.get(pk=transaction_identity("customer", index % CUSTOMER_COUNT))
                if index < saved_sale_count or not is_completed
                else None
            )
            prescription = None
            if index < PRESCRIPTION_LINKED_SALE_COUNT:
                prescription = Prescription.objects.get(
                    pk=transaction_identity("prescription", index)
                )
                customer = prescription.customer

            line_count = 1 + index % 3
            lines = []
            used = set()
            for slot in range(line_count):
                if index < MULTI_BATCH_SALE_COUNT and slot == 0:
                    medicine = multi_batch_candidates[index]
                    batches = list(get_fefo_eligible_batches(medicine))
                    unit = medicine.units.get(is_active=True, is_base_unit=True)
                    quantity = (batches[0].quantity_available_base + Decimal("1.000")).quantize(
                        Decimal("0.001")
                    )
                elif index < PRESCRIPTION_LINKED_SALE_COUNT and slot == 0:
                    medicine = prescription_medicines[index][0]
                    unit = medicine.units.get(is_active=True, is_base_unit=True)
                    quantity = Decimal("1.000")
                else:
                    line_candidates = (
                        higher_value_candidates
                        if PAID_SAVED_SALE_COUNT
                        <= index
                        < PAID_SAVED_SALE_COUNT + PARTIAL_SAVED_SALE_COUNT
                        else candidates
                    )
                    medicine, unit, quantity = self._ordinary_line(
                        line_candidates,
                        index * 7 + slot * 13,
                        used,
                        pharmacy,
                        prefer_pack=(
                            PAID_SAVED_SALE_COUNT
                            <= index
                            < PAID_SAVED_SALE_COUNT + PARTIAL_SAVED_SALE_COUNT
                            or (index + slot) % 11 == 0
                        ),
                    )
                used.add(medicine.pk)
                lines.append((medicine, unit, quantity))

            placeholder = _save_validated(
                SalesInvoice(
                    id=transaction_identity("sale", index),
                    pharmacist=actor,
                    currency_code=pharmacy.currency_code,
                )
            )
            form, formset, invoice = process_draft_sale(
                actor=actor,
                data=self._sale_form_data(customer, prescription, lines),
                instance=placeholder,
            )
            if invoice is None:
                self._raise_form_error("Draft sale", form, formset)

            if not is_completed:
                draft_at = timezone.now() - timedelta(days=index - COMPLETED_SALE_COUNT + 1)
                SalesInvoice.objects.filter(pk=invoice.pk).update(
                    created_at=draft_at, updated_at=draft_at
                )
                SalesInvoiceLine.objects.filter(sales_invoice=invoice).update(
                    created_at=draft_at, updated_at=draft_at
                )
                continue

            sale_date = today - timedelta(days=_completed_sale_days_ago(index))
            sale_at = timezone.make_aware(
                datetime.combine(sale_date, time(9 + index % 9, (index * 7) % 60)),
                timezone.get_default_timezone(),
            )
            initial_payment_data = None
            if customer is None:
                initial_payment_data = {
                    "payment_method": str(payment_method.pk),
                    "amount": str(invoice.grand_total),
                    "reference": f"{MARKER}-CP-WALKIN-{index + 1:03d}",
                    "paid_at": sale_at,
                }
            result = complete_sale(
                actor=actor,
                sales_invoice_id=invoice.pk,
                initial_payment_data=initial_payment_data,
            )
            invoice = result.invoice
            if result.initial_payment is not None:
                CustomerPayment.objects.filter(pk=result.initial_payment.pk).update(
                    created_at=sale_at
                )

            if customer is not None:
                payment_at = sale_at + timedelta(hours=1)
                if index < PAID_SAVED_SALE_COUNT:
                    if index < REVERSED_CUSTOMER_PAYMENT_COUNT:
                        trial_amount = Decimal("1.00")
                        if trial_amount >= invoice.grand_total:
                            raise CommandError(
                                "A planned reversible customer payment is not representable."
                            )
                        trial = self._post_customer_payment(
                            actor,
                            invoice,
                            payment_method,
                            trial_amount,
                            payment_at,
                            f"{MARKER}-CP-TRIAL-{index + 1:03d}",
                        )
                        reversal_form, reversed_payment = reverse_customer_payment(
                            actor=actor,
                            payment=trial,
                            data={"reversal_reason": f"{MARKER}: deterministic demo reversal."},
                        )
                        if reversed_payment is None:
                            self._raise_form_error("Customer payment reversal", reversal_form)
                        CustomerPayment.objects.filter(pk=trial.pk).update(
                            reversed_at=payment_at + timedelta(minutes=15)
                        )
                        invoice.refresh_from_db()
                    self._post_customer_payment(
                        actor,
                        invoice,
                        payment_method,
                        invoice.grand_total,
                        payment_at + timedelta(minutes=30),
                        f"{MARKER}-CP-FULL-{index + 1:03d}",
                    )
                elif index < PAID_SAVED_SALE_COUNT + PARTIAL_SAVED_SALE_COUNT:
                    # Whole-unit partials also avoid SQLite's binary NUMERIC
                    # subtraction edge in CheckConstraint validation while the
                    # production PostgreSQL path remains exact Decimal math.
                    partial = Decimal("1.00")
                    if partial <= ZERO_MONEY or partial >= invoice.grand_total:
                        raise CommandError("A planned partial sale payment is not representable.")
                    self._post_customer_payment(
                        actor,
                        invoice,
                        payment_method,
                        partial,
                        payment_at,
                        f"{MARKER}-CP-PART-{index + 1:03d}",
                    )

            SalesInvoice.objects.filter(pk=invoice.pk).update(
                created_at=sale_at - timedelta(minutes=5),
                completed_at=sale_at,
                updated_at=sale_at + timedelta(hours=2),
            )
            SalesInvoiceLine.objects.filter(sales_invoice=invoice).update(
                created_at=sale_at, updated_at=sale_at
            )
            SaleBatchAllocation.objects.filter(
                sales_invoice_line__sales_invoice=invoice
            ).update(created_at=sale_at)
            StockMovement.objects.filter(
                movement_type=StockMovement.MovementType.SALE,
                source_id=invoice.pk,
            ).update(occurred_at=sale_at, created_at=sale_at)

            if (index + 1) % 14 == 0:
                self.stdout.write(
                    f"Completed historical sales: {index + 1}/{COMPLETED_SALE_COUNT}"
                )
                self.stdout.flush()

        self.stdout.write(
            f"Created {COMPLETED_SALE_COUNT} completed sales and {DRAFT_SALE_COUNT} drafts."
        )

    def _post_supplier_payment(self, actor, invoice, method, amount, paid_at, reference):
        form, payment = post_supplier_payment(
            actor=actor,
            purchase_invoice=invoice,
            data={
                "payment_method": str(method.pk),
                "amount": str(amount),
                "reference": reference,
                "paid_at": paid_at,
            },
        )
        if payment is None:
            self._raise_form_error("Supplier payment", form)
        SupplierPayment.objects.filter(pk=payment.pk).update(created_at=paid_at)
        return payment

    def _create_supplier_payments(self, actor, payment_method):
        for index in range(PAID_PURCHASE_COUNT + PARTIAL_PURCHASE_COUNT):
            invoice = PurchaseInvoice.objects.get(pk=base_identity("invoice", index))
            paid_at = invoice.posted_at + timedelta(days=25 + index % 4 * 7)
            if index < PAID_PURCHASE_COUNT:
                if index < REVERSED_SUPPLIER_PAYMENT_COUNT:
                    trial_amount = Decimal("10.00")
                    if trial_amount >= invoice.grand_total:
                        raise CommandError(
                            "A planned reversible supplier payment is not representable."
                        )
                    trial = self._post_supplier_payment(
                        actor,
                        invoice,
                        payment_method,
                        trial_amount,
                        paid_at,
                        f"{MARKER}-SP-TRIAL-{index + 1:03d}",
                    )
                    reversal_form, reversed_payment = reverse_supplier_payment(
                        actor=actor,
                        payment=trial,
                        data={"reversal_reason": f"{MARKER}: deterministic demo reversal."},
                    )
                    if reversed_payment is None:
                        self._raise_form_error("Supplier payment reversal", reversal_form)
                    SupplierPayment.objects.filter(pk=trial.pk).update(
                        reversed_at=paid_at + timedelta(hours=1)
                    )
                    invoice.refresh_from_db()
                self._post_supplier_payment(
                    actor,
                    invoice,
                    payment_method,
                    invoice.grand_total,
                    paid_at + timedelta(hours=2),
                    f"{MARKER}-SP-FULL-{index + 1:03d}",
                )
            else:
                partial = Decimal("10.00")
                if partial >= invoice.grand_total:
                    raise CommandError("A planned partial supplier payment is not representable.")
                self._post_supplier_payment(
                    actor,
                    invoice,
                    payment_method,
                    partial,
                    paid_at,
                    f"{MARKER}-SP-PART-{index + 1:03d}",
                )
        self.stdout.write(
            f"Paid {PAID_PURCHASE_COUNT} demo purchases in full and "
            f"{PARTIAL_PURCHASE_COUNT} partially; remaining purchases stay unpaid."
        )

    def _stock_state(self, pharmacy):
        today = timezone.localdate()
        result = {"healthy": 0, "low": 0, "no_sellable": 0}
        for medicine in Medicine.objects.filter(is_active=True).prefetch_related("batches"):
            quantity = sum(
                (
                    batch.quantity_available_base
                    for batch in medicine.batches.all()
                    if batch.is_active and batch.expiry_date >= today
                ),
                Decimal("0.000"),
            )
            threshold = medicine.low_stock_threshold_base or pharmacy.default_low_stock_threshold
            key = "no_sellable" if quantity == 0 else "low" if quantity <= threshold else "healthy"
            result[key] += 1
        return result

    def _verify(self, expected, pharmacy):
        def require(condition, message):
            if not condition:
                raise CommandError(
                    f"Transactional demo integrity check failed: {message}."
                )

        for model, ids in expected.items():
            require(
                model.objects.filter(pk__in=ids).count() == len(ids), model.__name__
            )

        sale_ids = expected[SalesInvoice]
        completed_ids = sale_ids[:COMPLETED_SALE_COUNT]
        completed = SalesInvoice.objects.filter(pk__in=completed_ids)
        require(
            completed.filter(status=SalesInvoice.Status.COMPLETED).count()
            == COMPLETED_SALE_COUNT,
            "completed sales",
        )
        require(
            completed.filter(
                customer__isnull=True,
                balance_due=0,
                payment_status=SalesInvoice.PaymentStatus.PAID,
            ).count()
            == WALK_IN_SALE_COUNT,
            "walk-in settlement",
        )
        require(
            completed.filter(prescription__isnull=False).count()
            == PRESCRIPTION_LINKED_SALE_COUNT,
            "prescription links",
        )
        require(
            completed.filter(lines__prescription_required_snapshot=True)
            .distinct()
            .exists(),
            "prescription-required sales",
        )

        multi_batch_lines = SalesInvoiceLine.objects.filter(
            sales_invoice_id__in=completed_ids
        ).annotate(allocation_count=Count("batch_allocations")).filter(
            allocation_count__gt=1
        )
        require(
            multi_batch_lines.count() >= MULTI_BATCH_SALE_COUNT,
            "multi-batch FEFO examples",
        )

        allocations = SaleBatchAllocation.objects.filter(
            sales_invoice_line__sales_invoice_id__in=completed_ids
        ).select_related("sales_invoice_line__sales_invoice", "batch")
        movements = list(
            StockMovement.objects.filter(
                movement_type=StockMovement.MovementType.SALE,
                source_id__in=completed_ids,
            )
        )
        require(allocations.count() == len(movements), "allocation/movement count")
        movements_by_line = {movement.source_line_id: movement for movement in movements}
        for allocation in allocations:
            movement = movements_by_line.get(allocation.pk)
            require(movement is not None, "missing SALE movement")
            require(
                movement.source_type == StockMovement.MovementType.SALE
                and movement.batch_id == allocation.batch_id
                and movement.medicine_id == allocation.sales_invoice_line.medicine_id
                and movement.quantity_delta_base == -allocation.allocated_quantity_base
                and movement.unit_cost_snapshot == allocation.acquisition_cost_snapshot,
                "SALE traceability",
            )
            require(
                allocation.batch.first_received_at
                <= allocation.sales_invoice_line.sales_invoice.completed_at,
                "sale before batch receipt",
            )

        for invoice in completed.select_related("prescription"):
            if invoice.prescription_id:
                require(
                    invoice.prescription.prescription_date
                    <= timezone.localdate(invoice.completed_at),
                    "sale before linked prescription",
                )

        for invoice in completed.prefetch_related("payments"):
            posted_total = sum(
                (
                    payment.amount
                    for payment in invoice.payments.all()
                    if payment.status == PaymentStatus.POSTED
                ),
                ZERO_MONEY,
            )
            require(posted_total == invoice.paid_total, "customer paid total")
            require(
                invoice.balance_due == invoice.grand_total - posted_total,
                "customer balance",
            )
            require(posted_total <= invoice.grand_total, "customer overpayment")

        target_purchase_ids = [
            base_identity("invoice", i)
            for i in range(PAID_PURCHASE_COUNT + PARTIAL_PURCHASE_COUNT)
        ]
        for invoice in PurchaseInvoice.objects.filter(
            pk__in=target_purchase_ids
        ).prefetch_related("payments"):
            posted_total = sum(
                (
                    payment.amount
                    for payment in invoice.payments.all()
                    if payment.status == PaymentStatus.POSTED
                ),
                ZERO_MONEY,
            )
            require(posted_total == invoice.paid_total, "supplier paid total")
            require(
                invoice.remaining_balance == invoice.grand_total - posted_total,
                "supplier balance",
            )
            require(posted_total <= invoice.grand_total, "supplier overpayment")

        batch_totals = dict(
            StockMovement.objects.values("batch_id")
            .annotate(total=Sum("quantity_delta_base"))
            .values_list("batch_id", "total")
        )
        for batch in MedicineBatch.objects.all():
            require(batch.quantity_available_base >= 0, "negative stock")
            require(
                batch.quantity_available_base == batch_totals.get(batch.pk),
                "stock reconciliation",
            )

        state = self._stock_state(pharmacy)
        require(all(state.values()), "healthy/low/no-sellable coverage")
        today = timezone.localdate()
        require(
            MedicineBatch.objects.filter(expiry_date__lt=today).exists(),
            "expired batches",
        )
        require(
            MedicineBatch.objects.filter(
                expiry_date__range=(today, today + timedelta(days=90))
            ).exists(),
            "near-expiry batches",
        )

    def _summary(self, expected):
        sale_ids = expected[SalesInvoice]
        completed_ids = sale_ids[:COMPLETED_SALE_COUNT]
        completed = SalesInvoice.objects.filter(pk__in=completed_ids)
        customer_payments = CustomerPayment.objects.filter(
            sales_invoice_id__in=completed_ids
        )
        target_purchase_ids = [
            base_identity("invoice", i)
            for i in range(PAID_PURCHASE_COUNT + PARTIAL_PURCHASE_COUNT)
        ]
        supplier_payments = SupplierPayment.objects.filter(
            purchase_invoice_id__in=target_purchase_ids
        )
        pharmacy = PharmacySettings.objects.get(singleton_key=1)
        state = self._stock_state(pharmacy)
        sale_line_count = SalesInvoiceLine.objects.filter(
            sales_invoice_id__in=sale_ids
        ).count()
        allocation_count = SaleBatchAllocation.objects.filter(
            sales_invoice_line__sales_invoice_id__in=completed_ids
        ).count()
        summary = {
            "Customers (V2)": len(expected[Customer]),
            "Prescribers (V2)": len(expected[Prescriber]),
            "Prescriptions / items": (
                f"{len(expected[Prescription])} / {len(expected[PrescriptionItem])}"
            ),
            "Completed / draft sales": (
                f"{completed.count()} / "
                f"{SalesInvoice.objects.filter(pk__in=sale_ids[COMPLETED_SALE_COUNT:]).count()}"
            ),
            "Walk-in / saved-customer sales": (
                f"{completed.filter(customer__isnull=True).count()} / "
                f"{completed.filter(customer__isnull=False).count()}"
            ),
            "Paid / partial / unpaid sales": " / ".join(
                str(completed.filter(payment_status=status).count())
                for status in (
                    SalesInvoice.PaymentStatus.PAID,
                    SalesInvoice.PaymentStatus.PARTIAL,
                    SalesInvoice.PaymentStatus.UNPAID,
                )
            ),
            "Prescription-linked sales": completed.filter(
                prescription__isnull=False
            ).count(),
            "Sales lines / allocations": (
                f"{sale_line_count} / {allocation_count}"
            ),
            "Customer payments posted/reversed": (
                f"{customer_payments.filter(status=PaymentStatus.POSTED).count()} / "
                f"{customer_payments.filter(status=PaymentStatus.REVERSED).count()}"
            ),
            "Supplier payments posted/reversed": (
                f"{supplier_payments.filter(status=PaymentStatus.POSTED).count()} / "
                f"{supplier_payments.filter(status=PaymentStatus.REVERSED).count()}"
            ),
            "Paid / partial / unpaid purchases": " / ".join(
                str(PurchaseInvoice.objects.filter(payment_status=status).count())
                for status in (
                    PurchaseInvoice.PaymentStatus.PAID,
                    PurchaseInvoice.PaymentStatus.PARTIAL,
                    PurchaseInvoice.PaymentStatus.UNPAID,
                )
            ),
            "SALE stock movements (V2)": StockMovement.objects.filter(
                movement_type=StockMovement.MovementType.SALE,
                source_id__in=completed_ids,
            ).count(),
            "Active stock healthy/low/none": (
                f"{state['healthy']} / {state['low']} / {state['no_sellable']}"
            ),
        }
        methods = list(
            customer_payments.filter(status=PaymentStatus.POSTED)
            .values("payment_method__name")
            .annotate(count=Count("pk"))
            .order_by("payment_method__name")
        )
        summary["Posted customer methods"] = ", ".join(
            f"{row['payment_method__name']}={row['count']}" for row in methods
        )
        return summary
