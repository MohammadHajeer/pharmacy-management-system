"""Purchase invoice creation and posting services.

Posting is the authoritative, concurrency-safe workflow described in BRD 5.5
and 8: lock the invoice and any existing batch cost layers that will be
increased, revalidate, then commit inventory increases and matching
``PURCHASE_RECEIPT`` movements atomically through ``apps.inventory``.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.catalog.unit_economics import acquisition_cost_per_base_unit, base_quantity
from apps.core.document_numbers import purchase_invoice_number_for_posting
from apps.inventory.services import receive_purchase_stock

from .models import PurchaseInvoice, PurchaseInvoiceLine

MONEY_QUANTUM = Decimal("0.01")


def _require_permission(actor, permission):
    if not getattr(actor, "is_authenticated", False) or not actor.has_perm(permission):
        raise PermissionDenied


def _quantize_money(value):
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def compute_line_amounts(*, quantity, unit_cost, discount_amount, tax_rate_percent):
    """Return ``(line_subtotal, tax_amount, line_total)`` per BRD 9.1."""
    line_subtotal = _quantize_money(quantity * unit_cost)
    if discount_amount > line_subtotal:
        raise ValidationError("The discount cannot exceed the line subtotal.")
    taxable_amount = line_subtotal - discount_amount
    tax_amount = _quantize_money(taxable_amount * tax_rate_percent / Decimal("100"))
    line_total = _quantize_money(taxable_amount + tax_amount)
    return line_subtotal, tax_amount, line_total


def create_draft_purchase_invoice(
    *,
    actor,
    supplier,
    invoice_date,
    currency_code,
    lines_data,
    due_date=None,
    supplier_invoice_reference="",
):
    """Create a DRAFT purchase invoice with its lines and computed totals."""
    _require_permission(actor, "purchasing.add_purchaseinvoice")

    if not lines_data:
        raise ValidationError("A purchase invoice needs at least one line.")

    with transaction.atomic():
        invoice = PurchaseInvoice(
            supplier=supplier,
            supplier_invoice_reference=supplier_invoice_reference,
            invoice_date=invoice_date,
            due_date=due_date,
            status=PurchaseInvoice.Status.DRAFT,
            supplier_name_snapshot=supplier.name,
            currency_code=currency_code,
            created_by=actor,
        )
        invoice.full_clean(exclude=["invoice_number"])
        invoice.save()

        subtotal = Decimal("0.00")
        discount_total = Decimal("0.00")
        tax_total = Decimal("0.00")
        grand_total = Decimal("0.00")

        for line_data in lines_data:
            medicine = line_data["medicine"]
            medicine_unit = line_data["medicine_unit"]
            quantity = line_data["quantity"]
            unit_cost = line_data["unit_cost"]
            discount_amount = line_data.get("discount_amount") or Decimal("0.00")
            tax_rate_percent = line_data.get("tax_rate_percent") or Decimal("0.0000")

            if medicine_unit.medicine_id != medicine.pk:
                raise ValidationError("The unit must belong to the selected medicine.")
            if not medicine_unit.purchase_allowed:
                raise ValidationError(
                    f"{medicine_unit.name} is not allowed for purchases."
                )

            conversion_to_base_snapshot = medicine_unit.conversion_to_base
            received_quantity_base = base_quantity(quantity, conversion_to_base_snapshot)
            line_subtotal, tax_amount, line_total = compute_line_amounts(
                quantity=quantity,
                unit_cost=unit_cost,
                discount_amount=discount_amount,
                tax_rate_percent=tax_rate_percent,
            )

            line = PurchaseInvoiceLine(
                purchase_invoice=invoice,
                medicine=medicine,
                medicine_description_snapshot=medicine.name,
                medicine_unit=medicine_unit,
                unit_name_snapshot=medicine_unit.name,
                quantity=quantity,
                conversion_to_base_snapshot=conversion_to_base_snapshot,
                received_quantity_base=received_quantity_base,
                unit_cost=unit_cost,
                discount_amount=discount_amount,
                tax_rate_percent=tax_rate_percent,
                tax_amount=tax_amount,
                line_total=line_total,
                batch_number=line_data["batch_number"],
                expiry_date=line_data["expiry_date"],
            )
            line.full_clean()
            line.save()

            subtotal += line_subtotal
            discount_total += discount_amount
            tax_total += tax_amount
            grand_total += line_total

        invoice.subtotal = subtotal
        invoice.discount_total = discount_total
        invoice.tax_total = tax_total
        invoice.grand_total = grand_total
        invoice.remaining_balance = grand_total - invoice.paid_total
        invoice.full_clean(exclude=["invoice_number"])
        invoice.save()

    return invoice


def post_purchase_invoice(*, actor, purchase_invoice_id):
    """Post/receive a draft purchase invoice atomically with targeted locks.

    Locks the invoice, revalidates its lines, then increases inventory
    through ``apps.inventory`` in a deterministic order (grouped by the
    same medicine/batch/expiry/cost key used for the batch cost layer) so
    concurrent postings touching the same batch cannot deadlock or oversell.
    """
    _require_permission(actor, "purchasing.post_purchaseinvoice")

    with transaction.atomic():
        invoice = PurchaseInvoice.objects.select_for_update().get(pk=purchase_invoice_id)

        if invoice.status != PurchaseInvoice.Status.DRAFT:
            raise ValidationError("Only a draft purchase invoice can be posted.")

        lines = list(
            invoice.lines.select_related("medicine", "medicine_unit").order_by("id")
        )
        if not lines:
            raise ValidationError("A posted purchase invoice requires at least one line.")

        for line in lines:
            if not line.medicine_unit.purchase_allowed:
                raise ValidationError(
                    f"{line.unit_name_snapshot} is no longer allowed for purchases."
                )
            expected_base_quantity = base_quantity(
                line.quantity, line.conversion_to_base_snapshot
            )
            if line.received_quantity_base != expected_base_quantity:
                raise ValidationError(
                    "A purchase line's received base quantity no longer matches "
                    "its quantity and conversion snapshot."
                )

        # Deterministic order across lines/batches, mirroring the FEFO
        # ordering convention used elsewhere, to keep lock acquisition order
        # consistent across concurrent postings that touch the same batches.
        ordered_lines = sorted(
            lines,
            key=lambda line: (str(line.medicine_id), line.batch_number, line.expiry_date),
        )

        occurred_at = timezone.now()

        for line in ordered_lines:
            cost_per_base_unit = acquisition_cost_per_base_unit(
                line.unit_cost, line.conversion_to_base_snapshot
            )

            batch = receive_purchase_stock(
                actor=actor,
                medicine=line.medicine,
                batch_number=line.batch_number,
                expiry_date=line.expiry_date,
                acquisition_cost_per_base_unit=cost_per_base_unit,
                quantity_base=line.received_quantity_base,
                source_type="PURCHASE_RECEIPT",
                source_id=invoice.id,
                source_line_id=line.id,
                occurred_at=occurred_at,
            )

            line.medicine_batch = batch
            line.full_clean()
            line.save(update_fields=["medicine_batch", "updated_at"])

        if not invoice.invoice_number:
            invoice.invoice_number = purchase_invoice_number_for_posting(invoice.id)

        invoice.status = PurchaseInvoice.Status.POSTED
        invoice.posted_by = actor
        invoice.posted_at = occurred_at
        invoice.full_clean()
        invoice.save()

    return invoice
