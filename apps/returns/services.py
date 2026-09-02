"""Customer return and refund service layer.

Implements BRD 5.10 (Customer Returns and Refunds) and BRD 8 (Transaction
and Service Rules) using the targeted ``select_for_update()`` +
``transaction.atomic()`` pattern required for Phase 1:

- ``create_customer_return`` creates a ``DRAFT`` return with its lines over
  an original completed sale. A draft has no stock or balance effect, so it
  does not take any lock; the return/refund number is still assigned at
  creation (BRD 19.3), unlike deferred draft sales/purchase numbers.
- ``post_customer_return`` locks the return and then every affected batch,
  in deterministic ``id`` order, *before* any quantity or restock
  validation runs. It revalidates each line's cumulative returned quantity
  against the original ``SaleBatchAllocation`` and each line's cumulative
  refund value against the original ``SalesInvoiceLine.line_total`` —
  counting only other already-``POSTED`` returns, so concurrent postings
  against the same allocation cannot together exceed it. Safe, non-expired,
  resellable lines are restocked into their original batch through
  ``apps.inventory``; unsafe/damaged/expired or non-restocked lines create
  no stock movement.
- ``process_customer_refund`` locks the ``CustomerReturn`` before checking
  the eligible remaining amount, so concurrent refund requests against the
  same return cannot together exceed its total. Refunds are separate
  posted-only records (BRD 13.3/19.9): the original ``SalesInvoice`` is
  never written to by any function in this module.

Every function wraps its writes in one ``transaction.atomic()`` block, so a
failure at any point (a validation error, a permission check, an inventory
error) rolls back every write made so far in that call.

Returns follow the ``apps.core.services`` convention: functions that accept
submitted form data return a ``(form, instance)`` tuple, where ``instance``
is ``None`` when validation/business rules reject the request and the
errors are attached to ``form``.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.document_numbers import (
    customer_refund_number_for_creation,
    customer_return_number_for_creation,
)
from apps.inventory.models import MedicineBatch
from apps.inventory.services import restock_customer_return
from apps.sales.models import SalesInvoice, SaleBatchAllocation

from .forms import CustomerRefundForm
from .models import CustomerReturn, CustomerReturnLine, RefundStatus, ReturnStatus

MONEY_QUANTUM = Decimal("0.01")
ZERO_MONEY = Decimal("0.00")
ZERO_QUANTITY = Decimal("0.000")


def _require_permission(actor, permission):
    if not getattr(actor, "is_authenticated", False) or not actor.has_perm(permission):
        raise PermissionDenied


def _quantize_money(value):
    return (value if value is not None else ZERO_MONEY).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def _posted_returned_quantity(*, sales_invoice_line, batch_id, exclude_return_id):
    """Cumulative returned quantity for one sales-line/batch pair, counting
    only other already-``POSTED`` returns (drafts have no effect)."""
    total = (
        CustomerReturnLine.objects.filter(
            sales_invoice_line=sales_invoice_line,
            batch_id=batch_id,
            customer_return__status=ReturnStatus.POSTED,
        )
        .exclude(customer_return_id=exclude_return_id)
        .aggregate(total=Sum("returned_quantity_base"))["total"]
    )
    return total if total is not None else ZERO_QUANTITY


def _posted_returned_value(*, sales_invoice_line, exclude_return_id):
    """Cumulative refund value already recorded for one sales line, counting
    only other already-``POSTED`` returns (drafts have no effect)."""
    total = (
        CustomerReturnLine.objects.filter(
            sales_invoice_line=sales_invoice_line,
            customer_return__status=ReturnStatus.POSTED,
        )
        .exclude(customer_return_id=exclude_return_id)
        .aggregate(total=Sum("refund_amount"))["total"]
    )
    return _quantize_money(total) if total is not None else ZERO_MONEY


def create_customer_return(*, actor, sales_invoice, reason, lines_data):
    """Create a ``DRAFT`` customer return with its lines.

    ``lines_data`` is a list of dicts with ``sales_invoice_line``, ``batch``,
    ``returned_quantity_base``, ``condition``, ``restock``, and
    ``refund_amount``. This performs light per-line sanity checks only
    (matching allocation, non-negative amounts via model constraints); the
    authoritative cumulative-quantity/value caps are enforced by
    ``post_customer_return`` under lock, matching the draft/post split
    already used for purchase and sales invoices — a draft return has no
    stock or balance effect.

    ``customer`` is deliberately not accepted as input: the return's
    customer must exactly match the original sale's customer
    (``CustomerReturn.clean``), so it is always derived from
    ``sales_invoice`` here instead of trusting separate input.
    """
    _require_permission(actor, "returns.add_customerreturn")

    if sales_invoice.status != SalesInvoice.Status.COMPLETED:
        raise ValidationError(
            "A customer return must reference an original completed sale."
        )
    if not lines_data:
        raise ValidationError("A customer return needs at least one line.")

    with transaction.atomic():
        customer_return = CustomerReturn(
            sales_invoice=sales_invoice,
            customer=sales_invoice.customer,
            reason=reason,
            status=ReturnStatus.DRAFT,
            processed_by=actor,
        )
        # Return/refund numbers are assigned at creation (BRD 19.3), unlike
        # draft sales/purchase numbers, which stay blank until completion or
        # posting. ``customer_return.id`` is already populated at this point
        # because ``UUIDField(default=uuid.uuid4)`` assigns it in __init__.
        customer_return.return_number = customer_return_number_for_creation(customer_return.id)
        customer_return.full_clean()
        customer_return.save()

        return_total = ZERO_MONEY
        for line_data in lines_data:
            sales_invoice_line = line_data["sales_invoice_line"]
            batch = line_data["batch"]
            refund_amount = line_data["refund_amount"]

            if sales_invoice_line.sales_invoice_id != sales_invoice.pk:
                raise ValidationError(
                    "Every return line must belong to the original sales invoice."
                )
            if not sales_invoice_line.batch_allocations.filter(batch_id=batch.pk).exists():
                raise ValidationError(
                    "The batch must have been allocated to the original sales line."
                )

            line = CustomerReturnLine(
                customer_return=customer_return,
                sales_invoice_line=sales_invoice_line,
                batch=batch,
                returned_quantity_base=line_data["returned_quantity_base"],
                condition=line_data["condition"],
                restock=bool(line_data.get("restock")),
                refund_amount=refund_amount,
            )
            line.full_clean()
            line.save()
            return_total += refund_amount

        customer_return.return_total = _quantize_money(return_total)
        customer_return.full_clean()
        customer_return.save(update_fields=["return_total", "updated_at"])

    return customer_return


def post_customer_return(*, actor, customer_return):
    """Post a draft customer return atomically with targeted row locks.

    ``customer_return`` may be an unlocked instance (e.g. from a prior
    query); it is re-fetched with a row lock before any check runs, the
    same convention used by ``apps.finance.services.post_customer_payment``.
    Locks the return, then every affected batch in deterministic ``id``
    order, before revalidating quantity/restock rules (acceptance criterion
    1). Safe, non-expired, resellable lines are restocked into their
    original batch through ``apps.inventory``; unsafe/damaged/expired or
    non-restocked lines create no stock movement. Any error — a caught
    validation failure or an unexpected exception — rolls back every write
    made in this call, including any restocking already performed for
    earlier lines in the same return.
    """
    _require_permission(actor, "returns.post_customerreturn")

    with transaction.atomic():
        locked_return = (
            CustomerReturn.objects.select_for_update()
            .select_related("sales_invoice")
            .get(pk=customer_return.pk)
        )
        # Re-check permission now that the row is locked, mirroring the
        # purchasing/sales posting services.
        _require_permission(actor, "returns.post_customerreturn")

        if locked_return.status != ReturnStatus.DRAFT:
            raise ValidationError("Only a draft customer return can be posted.")
        if locked_return.sales_invoice.status != SalesInvoice.Status.COMPLETED:
            raise ValidationError(
                "The original sales invoice is no longer completed."
            )

        lines = list(
            locked_return.lines.select_related(
                "sales_invoice_line", "batch"
            ).order_by("id")
        )
        if not lines:
            raise ValidationError("A posted customer return requires at least one line.")

        # Lock every affected batch, in deterministic order, before any
        # quantity/restock validation runs (acceptance criterion 1).
        batch_ids = sorted({line.batch_id for line in lines}, key=str)
        locked_batches = {
            batch.pk: batch
            for batch in MedicineBatch.objects.select_for_update()
            .filter(pk__in=batch_ids)
            .order_by("id")
        }

        occurred_at = timezone.now()
        business_date = timezone.localdate()
        expected_return_total = ZERO_MONEY

        for line in lines:
            line.full_clean()
            sales_invoice_line = line.sales_invoice_line
            if sales_invoice_line.sales_invoice_id != locked_return.sales_invoice_id:
                raise ValidationError(
                    "A return line no longer belongs to the original sales invoice."
                )

            allocation = SaleBatchAllocation.objects.filter(
                sales_invoice_line=sales_invoice_line, batch_id=line.batch_id
            ).first()
            if allocation is None:
                raise ValidationError(
                    "The batch was not part of the original sale allocation."
                )

            # Cumulative returned quantity cannot exceed the original sale
            # allocation (acceptance criterion 2; ERD 13.2).
            already_returned = _posted_returned_quantity(
                sales_invoice_line=sales_invoice_line,
                batch_id=line.batch_id,
                exclude_return_id=locked_return.pk,
            )
            if (
                already_returned + line.returned_quantity_base
                > allocation.allocated_quantity_base
            ):
                raise ValidationError(
                    "Cumulative returned quantity would exceed the originally "
                    f"sold allocation for {sales_invoice_line.medicine_description_snapshot}."
                )

            # Cumulative refund value cannot exceed the original sale line's
            # value (acceptance criterion 2).
            already_refunded_value = _posted_returned_value(
                sales_invoice_line=sales_invoice_line,
                exclude_return_id=locked_return.pk,
            )
            if already_refunded_value + line.refund_amount > sales_invoice_line.line_total:
                raise ValidationError(
                    "Cumulative refund value would exceed the original sale "
                    f"line value for {sales_invoice_line.medicine_description_snapshot}."
                )

            if line.restock:
                if line.condition != CustomerReturnLine.Condition.RESELLABLE:
                    raise ValidationError("Only resellable items may be restocked.")
                locked_batch = locked_batches.get(line.batch_id)
                if (
                    locked_batch is None
                    or not locked_batch.is_active
                    or locked_batch.expiry_date < business_date
                ):
                    raise ValidationError(
                        "Only active, unexpired stock can be returned to saleable inventory."
                    )

            expected_return_total += line.refund_amount

        if _quantize_money(expected_return_total) != locked_return.return_total:
            raise ValidationError(
                "The customer return total no longer matches its stored lines."
            )

        for line in lines:
            # Safe, non-expired, resellable lines restore the original
            # batch with a movement (acceptance criterion 3); unsafe,
            # damaged, expired, or non-restocked lines create none.
            if line.restock and line.condition == CustomerReturnLine.Condition.RESELLABLE:
                restock_customer_return(
                    actor=actor,
                    batch=locked_batches[line.batch_id],
                    quantity_base=line.returned_quantity_base,
                    source_type="CUSTOMER_RETURN_RESTOCK",
                    source_id=locked_return.id,
                    source_line_id=line.id,
                    reference_number=locked_return.return_number,
                    occurred_at=occurred_at,
                )

        locked_return.status = ReturnStatus.POSTED
        locked_return.posted_at = occurred_at
        locked_return.full_clean()
        locked_return.save(update_fields=["status", "posted_at", "updated_at"])

    return locked_return


def process_customer_refund(*, actor, customer_return, data):
    """Post a refund against an already-posted customer return.

    ``customer_return`` may be an unlocked instance (e.g. from a prior
    query); it is re-fetched with a row lock before any check runs.
    Locking it first — before computing the eligible remaining amount — is
    what prevents concurrent refund requests from together exceeding the
    return total, the same pattern used for invoice-balance locking in
    ``apps.finance.services``. The refund is a separate posted-only record
    (BRD 13.3); this function never writes to the original ``SalesInvoice``
    (acceptance criterion 4).
    """
    _require_permission(actor, "returns.process_refund")

    with transaction.atomic():
        locked_return = (
            CustomerReturn.objects.select_for_update()
            .select_related("sales_invoice")
            .get(pk=customer_return.pk)
        )
        _require_permission(actor, "returns.process_refund")

        form = CustomerRefundForm(data=data)
        if not form.is_valid():
            return form, None

        if locked_return.status != ReturnStatus.POSTED:
            form.add_error(
                None, "Refunds can only be processed for a posted customer return."
            )
            return form, None

        already_refunded = locked_return.refunds.aggregate(total=Sum("amount"))["total"]
        already_refunded = _quantize_money(already_refunded) if already_refunded else ZERO_MONEY
        eligible_remaining = _quantize_money(locked_return.return_total - already_refunded)

        amount = form.cleaned_data["amount"]
        if amount > eligible_remaining:
            form.add_error(
                "amount",
                "The refund amount cannot exceed the eligible refundable amount "
                f"of {eligible_remaining}.",
            )
            return form, None

        refund = form.save(commit=False)
        refund.customer_return = locked_return
        refund.sales_invoice = locked_return.sales_invoice
        refund.processed_by = actor
        refund.status = RefundStatus.POSTED
        # ``refund.id`` is already populated because the ModelForm builds an
        # unsaved instance (``UUIDField(default=uuid.uuid4)``) at
        # construction time, so the deterministic number can be assigned
        # before the first save, matching the return-number pattern above.
        refund.refund_number = customer_refund_number_for_creation(refund.id)
        refund.full_clean()
        refund.save()

    return form, refund
