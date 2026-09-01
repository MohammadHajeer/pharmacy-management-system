"""Authoritative inventory services.

``apps.inventory`` is the only app allowed to change
``MedicineBatch.quantity_available_base``. Every mutation here happens inside
``transaction.atomic()`` together with a matching ``StockMovement`` row, using
targeted ``select_for_update()`` locking as required by the BRD/ERD.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import MedicineBatch, StockMovement

QUANTITY_QUANTUM = Decimal("0.001")


class InsufficientStockError(Exception):
    """Raised when eligible stock cannot cover the requested quantity."""


class InvalidStockOperationError(Exception):
    """Raised for programmer errors: bad quantities, mismatched medicine, etc."""


@dataclass(frozen=True)
class StockAllocation:
    """One batch's contribution to a larger stock movement."""

    batch: MedicineBatch
    quantity_base: Decimal
    unit_cost_snapshot: Decimal


def _require_positive_quantity(quantity_base):
    if not isinstance(quantity_base, Decimal):
        raise InvalidStockOperationError("quantity_base must be a Decimal.")
    if quantity_base <= 0:
        raise InvalidStockOperationError("quantity_base must be greater than zero.")


def _require_reference_number(reference_number):
    if not isinstance(reference_number, str) or not reference_number.strip():
        raise InvalidStockOperationError("reference_number is required.")


def _create_stock_movement(
    *,
    actor,
    medicine,
    batch,
    movement_type,
    quantity_delta_base,
    unit_cost_snapshot,
    source_type,
    source_id,
    source_line_id,
    reference_number,
    occurred_at,
):
    if source_line_id is None:
        raise InvalidStockOperationError(
            "An authoritative source_line_id is required for Phase 1 stock movements."
        )
    if source_type != movement_type:
        raise InvalidStockOperationError(
            "source_type must match the authoritative stock movement type."
        )
    movement = StockMovement(
        medicine=medicine,
        batch=batch,
        movement_type=movement_type,
        quantity_delta_base=quantity_delta_base,
        unit_cost_snapshot=unit_cost_snapshot,
        source_type=source_type,
        source_id=source_id,
        source_line_id=source_line_id,
        reference_number=reference_number,
        performed_by=actor,
        occurred_at=occurred_at,
    )
    movement.full_clean()
    movement.save()
    return movement


def get_fefo_eligible_batches(medicine, *, as_of_date=None, lock=False):
    """Return active, unexpired, in-stock batches for ``medicine`` in FEFO order.

    FEFO order is earliest ``expiry_date`` first, then earliest
    ``first_received_at``, then ``id`` to break ties deterministically.
    Pass ``lock=True`` to acquire ``select_for_update()`` row locks before a
    caller revalidates availability inside its own ``transaction.atomic()``.
    """
    as_of_date = as_of_date or timezone.localdate()
    queryset = MedicineBatch.objects.filter(
        medicine=medicine,
        is_active=True,
        expiry_date__gte=as_of_date,
        quantity_available_base__gt=0,
    ).order_by("expiry_date", "first_received_at", "id")

    if lock:
        queryset = queryset.select_for_update()

    return queryset


def receive_purchase_stock(
    *,
    actor,
    medicine,
    batch_number,
    expiry_date,
    acquisition_cost_per_base_unit,
    quantity_base,
    source_type,
    source_id,
    reference_number,
    source_line_id=None,
    occurred_at=None,
):
    """Receive purchased stock into a batch cost layer and record the movement.

    Locates the existing batch cost layer (same medicine, batch number,
    expiry date, and acquisition cost) under a row lock, or creates it if it
    does not yet exist, then increases its available quantity and writes the
    matching ``PURCHASE_RECEIPT`` movement in the same transaction.
    """
    _require_positive_quantity(quantity_base)
    _require_reference_number(reference_number)
    occurred_at = occurred_at or timezone.now()

    with transaction.atomic():
        batch_lookup = {
            "medicine": medicine,
            "batch_number": batch_number,
            "expiry_date": expiry_date,
            "acquisition_cost_per_base_unit": acquisition_cost_per_base_unit,
        }
        batch = MedicineBatch.objects.select_for_update().filter(**batch_lookup).first()

        if batch is None:
            try:
                with transaction.atomic():
                    batch = MedicineBatch(
                        **batch_lookup,
                        quantity_available_base=Decimal("0.000"),
                        first_received_at=occurred_at,
                        is_active=True,
                    )
                    batch.full_clean()
                    batch.save()
            except IntegrityError:
                # A concurrent receipt may have created this cost layer while
                # this transaction was waiting. Lock that committed row before
                # rechecking and increasing its quantity.
                batch = MedicineBatch.objects.select_for_update().get(**batch_lookup)

        if not batch.is_active:
            raise InvalidStockOperationError(
                "Purchased stock cannot be received into an inactive batch cost layer."
            )

        batch.quantity_available_base = batch.quantity_available_base + quantity_base
        batch.full_clean()
        batch.save(update_fields=["quantity_available_base", "updated_at"])

        _create_stock_movement(
            actor=actor,
            medicine=medicine,
            batch=batch,
            movement_type=StockMovement.MovementType.PURCHASE_RECEIPT,
            quantity_delta_base=quantity_base,
            unit_cost_snapshot=acquisition_cost_per_base_unit,
            source_type=source_type,
            source_id=source_id,
            source_line_id=source_line_id,
            reference_number=reference_number,
            occurred_at=occurred_at,
        )

    return batch


def deduct_stock_fefo(
    *,
    actor,
    medicine,
    quantity_base,
    source_type,
    source_id,
    source_line_id_factory,
    reference_number,
    occurred_at=None,
    as_of_date=None,
):
    """Deduct ``quantity_base`` from ``medicine`` using First-Expired-First-Out.

    Locks eligible batches in deterministic FEFO order, revalidates
    availability under the lock, then decrements across as many batches as
    needed and writes one ``SALE`` movement per batch touched. The caller's
    ``source_line_id_factory`` creates or identifies one authoritative sale
    allocation for each locked batch allocation and returns its distinct UUID.
    Raises ``InsufficientStockError`` and rolls back if eligible stock cannot
    cover the request.
    """
    _require_positive_quantity(quantity_base)
    _require_reference_number(reference_number)
    if not callable(source_line_id_factory):
        raise InvalidStockOperationError("source_line_id_factory must be callable.")
    occurred_at = occurred_at or timezone.now()
    as_of_date = as_of_date or timezone.localdate()

    with transaction.atomic():
        eligible_batches = list(
            get_fefo_eligible_batches(medicine, as_of_date=as_of_date, lock=True)
        )

        remaining = quantity_base
        allocations = []

        for batch in eligible_batches:
            if remaining <= 0:
                break
            take = min(batch.quantity_available_base, remaining)
            if take <= 0:
                continue
            allocations.append(
                StockAllocation(
                    batch=batch,
                    quantity_base=take,
                    unit_cost_snapshot=batch.acquisition_cost_per_base_unit,
                )
            )
            remaining -= take

        if remaining > 0:
            raise InsufficientStockError(
                f"Only {quantity_base - remaining} of {quantity_base} requested base "
                f"units are available for medicine {medicine.pk}."
            )

        source_line_ids = set()
        for allocation in allocations:
            batch = allocation.batch
            batch.quantity_available_base = (
                batch.quantity_available_base - allocation.quantity_base
            )
            batch.full_clean()
            batch.save(update_fields=["quantity_available_base", "updated_at"])

            source_line_id = source_line_id_factory(allocation)
            if source_line_id is None or source_line_id in source_line_ids:
                raise InvalidStockOperationError(
                    "Each FEFO allocation requires a distinct authoritative source line."
                )
            source_line_ids.add(source_line_id)

            _create_stock_movement(
                actor=actor,
                medicine=medicine,
                batch=batch,
                movement_type=StockMovement.MovementType.SALE,
                quantity_delta_base=-allocation.quantity_base,
                unit_cost_snapshot=allocation.unit_cost_snapshot,
                source_type=source_type,
                source_id=source_id,
                source_line_id=source_line_id,
                reference_number=reference_number,
                occurred_at=occurred_at,
            )

    return allocations


def restock_customer_return(
    *,
    actor,
    batch,
    quantity_base,
    source_type,
    source_id,
    reference_number,
    source_line_id=None,
    occurred_at=None,
):
    """Restock a resellable customer return into its originating batch.

    Only ever called for lines already validated as resellable by
    ``apps.returns``; this service locks the batch, increases its quantity,
    and writes the matching ``CUSTOMER_RETURN_RESTOCK`` movement.
    """
    _require_positive_quantity(quantity_base)
    _require_reference_number(reference_number)
    occurred_at = occurred_at or timezone.now()

    with transaction.atomic():
        locked_batch = MedicineBatch.objects.select_for_update().get(pk=batch.pk)

        if not locked_batch.is_active or locked_batch.expiry_date < timezone.localdate():
            raise InvalidStockOperationError(
                "Only active, unexpired stock can be returned to saleable inventory."
            )

        locked_batch.quantity_available_base = (
            locked_batch.quantity_available_base + quantity_base
        )
        locked_batch.full_clean()
        locked_batch.save(update_fields=["quantity_available_base", "updated_at"])

        _create_stock_movement(
            actor=actor,
            medicine=locked_batch.medicine,
            batch=locked_batch,
            movement_type=StockMovement.MovementType.CUSTOMER_RETURN_RESTOCK,
            quantity_delta_base=quantity_base,
            unit_cost_snapshot=locked_batch.acquisition_cost_per_base_unit,
            source_type=source_type,
            source_id=source_id,
            source_line_id=source_line_id,
            reference_number=reference_number,
            occurred_at=occurred_at,
        )

    return locked_batch


def deduct_supplier_return(
    *,
    actor,
    batch,
    quantity_base,
    source_type,
    source_id,
    reference_number,
    source_line_id=None,
    occurred_at=None,
):
    """Deduct stock from an exact batch being returned to a supplier.

    Locks the specific batch, revalidates that enough quantity remains
    available, then decrements it and writes the matching
    ``SUPPLIER_RETURN`` movement.
    """
    _require_positive_quantity(quantity_base)
    _require_reference_number(reference_number)
    occurred_at = occurred_at or timezone.now()

    with transaction.atomic():
        locked_batch = MedicineBatch.objects.select_for_update().get(pk=batch.pk)

        if locked_batch.quantity_available_base < quantity_base:
            raise InsufficientStockError(
                f"Batch {locked_batch.pk} has only "
                f"{locked_batch.quantity_available_base} base units available; "
                f"cannot return {quantity_base}."
            )

        locked_batch.quantity_available_base = (
            locked_batch.quantity_available_base - quantity_base
        )
        locked_batch.full_clean()
        locked_batch.save(update_fields=["quantity_available_base", "updated_at"])

        _create_stock_movement(
            actor=actor,
            medicine=locked_batch.medicine,
            batch=locked_batch,
            movement_type=StockMovement.MovementType.SUPPLIER_RETURN,
            quantity_delta_base=-quantity_base,
            unit_cost_snapshot=locked_batch.acquisition_cost_per_base_unit,
            source_type=source_type,
            source_id=source_id,
            source_line_id=source_line_id,
            reference_number=reference_number,
            occurred_at=occurred_at,
        )

    return locked_batch
