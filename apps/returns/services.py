"""Supplier return creation and posting services.

Posting is the authoritative, concurrency-safe workflow described in BRD
5.11 and 8: lock the supplier return and every affected batch cost layer
before validation, then deduct stock from the exact batches through
``apps.inventory`` and record matching ``SUPPLIER_RETURN`` movements
atomically with targeted row locking.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.document_numbers import supplier_return_number_for_creation
from apps.inventory.models import MedicineBatch
from apps.inventory.services import deduct_supplier_return

from .models import ReturnStatus, SupplierReturn, SupplierReturnLine

MONEY_QUANTUM = Decimal("0.01")


def _require_permission(actor, permission):
    if not getattr(actor, "is_authenticated", False) or not actor.has_perm(permission):
        raise PermissionDenied


def _quantize_money(value):
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def compute_line_total(*, returned_quantity_base, unit_cost_snapshot):
    """Return the money-quantized line total for a supplier return line."""
    return _quantize_money(returned_quantity_base * unit_cost_snapshot)


def create_draft_supplier_return(
    *,
    actor,
    supplier,
    reason,
    lines_data,
    purchase_invoice=None,
):
    """Create a DRAFT supplier return referencing exact batches per BRD 5.11.

    Each line's ``unit_cost_snapshot`` is taken from its exact batch cost
    layer, which is immutable for the life of that batch row, so the
    snapshot and line total stay traceable even if the batch is later
    deactivated or fully depleted.
    """
    _require_permission(actor, "returns.add_supplierreturn")

    if not lines_data:
        raise ValidationError("A supplier return needs at least one line.")
    if not supplier.is_active:
        raise ValidationError("An active supplier is required.")
    if purchase_invoice is not None and purchase_invoice.supplier_id != supplier.pk:
        raise ValidationError("The purchase invoice must belong to the supplier.")

    with transaction.atomic():
        supplier_return = SupplierReturn(
            supplier=supplier,
            purchase_invoice=purchase_invoice,
            reason=reason,
            status=ReturnStatus.DRAFT,
            processed_by=actor,
        )
        # The return number is a required, deterministic identifier assigned
        # at creation (unlike a purchase invoice number, which is deferred
        # to posting), so it must be set before the first save.
        supplier_return.return_number = supplier_return_number_for_creation(
            supplier_return.id
        )

        return_total = Decimal("0.00")
        lines = []

        for line_data in lines_data:
            medicine = line_data["medicine"]
            batch = line_data["batch"]
            returned_quantity_base = line_data["returned_quantity_base"]

            if batch.medicine_id != medicine.pk:
                raise ValidationError("The batch must belong to the selected medicine.")

            unit_cost_snapshot = batch.acquisition_cost_per_base_unit
            line_total = compute_line_total(
                returned_quantity_base=returned_quantity_base,
                unit_cost_snapshot=unit_cost_snapshot,
            )

            lines.append(
                SupplierReturnLine(
                    supplier_return=supplier_return,
                    medicine=medicine,
                    batch=batch,
                    returned_quantity_base=returned_quantity_base,
                    unit_cost_snapshot=unit_cost_snapshot,
                    line_total=line_total,
                )
            )
            return_total += line_total

        supplier_return.return_total = return_total
        supplier_return.full_clean()
        supplier_return.save()

        for line in lines:
            line.full_clean()
            line.save()

    return supplier_return


def post_supplier_return(*, actor, supplier_return_id):
    """Post a draft supplier return atomically with targeted row locks.

    Locks the supplier return and every affected batch cost layer, in
    deterministic id order, before any validation or mutation, so
    concurrent postings that touch the same batches cannot deadlock or
    push a batch's available quantity negative. Deductions and their
    matching ``SUPPLIER_RETURN`` stock movements are then committed
    through ``apps.inventory`` in one transaction; any failure — including
    insufficient stock on a later line — rolls back every write from this
    posting.
    """
    _require_permission(actor, "returns.post_supplierreturn")

    with transaction.atomic():
        supplier_return = (
            SupplierReturn.objects.select_for_update()
            .select_related("supplier")
            .get(pk=supplier_return_id)
        )
        # Recheck permission after acquiring the lock in case it changed
        # while this transaction was waiting, mirroring purchase posting.
        _require_permission(actor, "returns.post_supplierreturn")

        if supplier_return.status != ReturnStatus.DRAFT:
            raise ValidationError("Only a draft supplier return can be posted.")
        if not supplier_return.supplier.is_active:
            raise ValidationError("The supplier return's supplier is inactive.")

        lines = list(
            supplier_return.lines.select_related("medicine", "batch").order_by("id")
        )
        if not lines:
            raise ValidationError("A posted supplier return requires at least one line.")

        batch_ids = {line.batch_id for line in lines}
        locked_batches = {
            batch.pk: batch
            for batch in MedicineBatch.objects.select_for_update()
            .filter(pk__in=batch_ids)
            .order_by("id")
        }

        expected_return_total = Decimal("0.00")
        for line in lines:
            line.full_clean()
            batch = locked_batches.get(line.batch_id)
            if batch is None:
                raise ValidationError("A supplier return line references an unknown batch.")
            if batch.medicine_id != line.medicine_id:
                raise ValidationError(
                    "A supplier return line's batch no longer matches its medicine."
                )
            expected_line_total = compute_line_total(
                returned_quantity_base=line.returned_quantity_base,
                unit_cost_snapshot=line.unit_cost_snapshot,
            )
            if line.line_total != expected_line_total:
                raise ValidationError(
                    "A supplier return line's stored total no longer matches its inputs."
                )
            expected_return_total += expected_line_total

        if supplier_return.return_total != expected_return_total:
            raise ValidationError(
                "The supplier return total no longer matches its stored lines."
            )

        occurred_at = timezone.now()

        # Exact-batch deductions and their SUPPLIER_RETURN movements are
        # delegated to apps.inventory, the only app allowed to change batch
        # quantities; it re-validates available quantity per line under the
        # lock already held here, so over-return attempts (including two
        # lines against the same batch) are rejected and roll back the
        # whole posting.
        for line in lines:
            deduct_supplier_return(
                actor=actor,
                batch=locked_batches[line.batch_id],
                quantity_base=line.returned_quantity_base,
                source_type="SUPPLIER_RETURN",
                source_id=supplier_return.id,
                source_line_id=line.id,
                reference_number=supplier_return.return_number,
                occurred_at=occurred_at,
            )

        supplier_return.status = ReturnStatus.POSTED
        supplier_return.posted_at = occurred_at
        supplier_return.full_clean()
        supplier_return.save()

    return supplier_return
