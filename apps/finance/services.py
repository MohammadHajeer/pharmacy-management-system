"""Finance service layer: post/reverse customer and supplier payments.

Implements BRD 5.9 (Payments and Balances) and BRD 8 (Transaction and
Service Rules) using the targeted ``select_for_update()`` + ``atomic()``
pattern required for Phase 1:

- posting locks the affected invoice, then rechecks invoice status, the
  outstanding balance, and the submitted amount/method before creating the
  payment;
- reversal locks the affected invoice and then the payment row, then
  rechecks the payment's current status before recording reversal
  metadata;
- in both cases the invoice's payment-only balance fields
  (``paid_total``/``balance_due`` or ``paid_total``/``remaining_balance``,
  plus ``payment_status``) are recalculated from the sum of active
  ``POSTED`` payments inside the same atomic transaction.

Locking the invoice row first is what prevents concurrent payments from
exceeding the balance: every posting/reversal attempt against the same
invoice serializes on that row, so the outstanding-balance check that
follows always sees the latest committed state.

Returns are ``(form, payment)`` tuples, matching the ``apps.core.services``
convention: ``payment`` is ``None`` when validation/business rules reject
the request, in which case the errors are on ``form``.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.purchasing.models import PurchaseInvoice
from apps.sales.models import SalesInvoice

from .forms import CustomerPaymentForm, PaymentReversalForm, SupplierPaymentForm
from .models import CustomerPayment, PaymentStatus, SupplierPayment

MONEY_QUANTUM = Decimal("0.01")
ZERO_MONEY = Decimal("0.00")


def _require_permission(actor, permission):
    if not getattr(actor, "is_authenticated", False) or not actor.has_perm(permission):
        raise PermissionDenied


def _quantize_money(value):
    return (value if value is not None else ZERO_MONEY).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def _active_payments_total(payment_queryset):
    """Sum of active POSTED payments; caller's queryset must already be
    scoped to a single locked invoice."""
    total = payment_queryset.filter(status=PaymentStatus.POSTED).aggregate(
        total=Sum("amount")
    )["total"]
    return _quantize_money(total)


def _recalculate_sales_invoice(invoice):
    """Recompute ``paid_total``/``balance_due``/``payment_status`` for a
    sales invoice from its active posted customer payments.

    The invoice row must already be locked with ``select_for_update()`` in
    the caller's open transaction; this function does not lock or re-fetch
    it, so callers must not use it outside that transaction.
    """
    paid_total = _active_payments_total(invoice.payments)
    balance_due = _quantize_money(invoice.grand_total - paid_total)
    if balance_due <= ZERO_MONEY:
        payment_status = SalesInvoice.PaymentStatus.PAID
    elif paid_total > ZERO_MONEY:
        payment_status = SalesInvoice.PaymentStatus.PARTIAL
    else:
        payment_status = SalesInvoice.PaymentStatus.UNPAID

    invoice.paid_total = paid_total
    invoice.balance_due = balance_due
    invoice.payment_status = payment_status
    invoice.full_clean()
    invoice.save(update_fields=["paid_total", "balance_due", "payment_status", "updated_at"])
    return invoice


def _recalculate_purchase_invoice(invoice):
    """Recompute ``paid_total``/``remaining_balance``/``payment_status`` for
    a purchase invoice from its active posted supplier payments.

    The invoice row must already be locked with ``select_for_update()`` in
    the caller's open transaction; this function does not lock or re-fetch
    it, so callers must not use it outside that transaction.
    """
    paid_total = _active_payments_total(invoice.payments)
    remaining_balance = _quantize_money(invoice.grand_total - paid_total)
    if remaining_balance <= ZERO_MONEY:
        payment_status = PurchaseInvoice.PaymentStatus.PAID
    elif paid_total > ZERO_MONEY:
        payment_status = PurchaseInvoice.PaymentStatus.PARTIAL
    else:
        payment_status = PurchaseInvoice.PaymentStatus.UNPAID

    invoice.paid_total = paid_total
    invoice.remaining_balance = remaining_balance
    invoice.payment_status = payment_status
    invoice.full_clean()
    invoice.save(
        update_fields=["paid_total", "remaining_balance", "payment_status", "updated_at"]
    )
    return invoice


def post_customer_payment(*, actor, sales_invoice, data):
    """Post a customer payment against a completed sales invoice.

    ``sales_invoice`` may be an unlocked instance (e.g. from a prior query);
    it is re-fetched with a row lock before any check runs. See module
    docstring for the full rule set.
    """
    _require_permission(actor, "finance.post_customerpayment")

    with transaction.atomic():
        invoice = SalesInvoice.objects.select_for_update().get(pk=sales_invoice.pk)

        form = CustomerPaymentForm(data=data)
        if not form.is_valid():
            return form, None

        if invoice.status != SalesInvoice.Status.COMPLETED:
            form.add_error(
                None,
                "Payments can only be posted against a completed sales invoice.",
            )
            return form, None

        current_balance = _quantize_money(
            invoice.grand_total - _active_payments_total(invoice.payments)
        )
        amount = form.cleaned_data["amount"]
        if amount > current_balance:
            form.add_error(
                "amount",
                f"The payment amount cannot exceed the outstanding balance of "
                f"{current_balance}.",
            )
            return form, None

        payment = form.save(commit=False)
        payment.sales_invoice = invoice
        payment.customer = invoice.customer
        payment.processed_by = actor
        payment.status = PaymentStatus.POSTED
        payment.full_clean()
        payment.save()

        _recalculate_sales_invoice(invoice)

    return form, payment


def reverse_customer_payment(*, actor, payment, data=None):
    """Reverse a posted customer payment and recalculate the invoice balance.

    ``payment`` may be an unlocked instance; the invoice and the payment row
    are re-fetched with row locks (invoice first) before any check runs.
    """
    _require_permission(actor, "finance.post_customerpayment")

    form = PaymentReversalForm(data=data if data is not None else {})
    if not form.is_valid():
        return form, None

    with transaction.atomic():
        invoice = SalesInvoice.objects.select_for_update().get(pk=payment.sales_invoice_id)
        locked_payment = CustomerPayment.objects.select_for_update().get(pk=payment.pk)

        if locked_payment.status != PaymentStatus.POSTED:
            form.add_error(None, "Only a posted payment can be reversed.")
            return form, None

        remaining_paid_total = _active_payments_total(
            invoice.payments.exclude(pk=locked_payment.pk)
        )
        if (
            invoice.status == SalesInvoice.Status.COMPLETED
            and invoice.customer_id is None
            and remaining_paid_total < invoice.grand_total
        ):
            form.add_error(
                None,
                "A payment cannot be reversed when it would leave a completed "
                "walk-in sale with an outstanding balance.",
            )
            return form, None

        locked_payment.status = PaymentStatus.REVERSED
        locked_payment.reversed_by = actor
        locked_payment.reversed_at = timezone.now()
        locked_payment.reversal_reason = form.cleaned_data.get("reversal_reason", "")
        locked_payment.full_clean()
        locked_payment.save(
            update_fields=["status", "reversed_by", "reversed_at", "reversal_reason"]
        )

        _recalculate_sales_invoice(invoice)

    return form, locked_payment


def post_supplier_payment(*, actor, purchase_invoice, data):
    """Post a supplier payment against a posted purchase invoice.

    ``purchase_invoice`` may be an unlocked instance; it is re-fetched with
    a row lock before any check runs. See module docstring for the full
    rule set.
    """
    _require_permission(actor, "finance.post_supplierpayment")

    with transaction.atomic():
        invoice = PurchaseInvoice.objects.select_for_update().get(pk=purchase_invoice.pk)

        form = SupplierPaymentForm(data=data)
        if not form.is_valid():
            return form, None

        if invoice.status != PurchaseInvoice.Status.POSTED:
            form.add_error(
                None,
                "Payments can only be posted against a posted purchase invoice.",
            )
            return form, None

        current_balance = _quantize_money(
            invoice.grand_total - _active_payments_total(invoice.payments)
        )
        amount = form.cleaned_data["amount"]
        if amount > current_balance:
            form.add_error(
                "amount",
                f"The payment amount cannot exceed the outstanding balance of "
                f"{current_balance}.",
            )
            return form, None

        payment = form.save(commit=False)
        payment.purchase_invoice = invoice
        payment.supplier = invoice.supplier
        payment.processed_by = actor
        payment.status = PaymentStatus.POSTED
        payment.full_clean()
        payment.save()

        _recalculate_purchase_invoice(invoice)

    return form, payment


def reverse_supplier_payment(*, actor, payment, data=None):
    """Reverse a posted supplier payment and recalculate the invoice balance.

    ``payment`` may be an unlocked instance; the invoice and the payment row
    are re-fetched with row locks (invoice first) before any check runs.
    """
    _require_permission(actor, "finance.post_supplierpayment")

    form = PaymentReversalForm(data=data if data is not None else {})
    if not form.is_valid():
        return form, None

    with transaction.atomic():
        invoice = PurchaseInvoice.objects.select_for_update().get(
            pk=payment.purchase_invoice_id
        )
        locked_payment = SupplierPayment.objects.select_for_update().get(pk=payment.pk)

        if locked_payment.status != PaymentStatus.POSTED:
            form.add_error(None, "Only a posted payment can be reversed.")
            return form, None

        locked_payment.status = PaymentStatus.REVERSED
        locked_payment.reversed_by = actor
        locked_payment.reversed_at = timezone.now()
        locked_payment.reversal_reason = form.cleaned_data.get("reversal_reason", "")
        locked_payment.full_clean()
        locked_payment.save(
            update_fields=["status", "reversed_by", "reversed_at", "reversal_reason"]
        )

        _recalculate_purchase_invoice(invoice)

    return form, locked_payment
