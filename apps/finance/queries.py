"""Finance query services: invoice search and derived party statements.

Implements ticket E4-T03 / 4300 ("Provide invoice search and derived
customer/supplier statements") per BRD 5.9 and ERD Section 14 (Reports and
Balances):

- Invoice search is a permission-scoped, filterable read over the existing
  ``SalesInvoice``/``PurchaseInvoice`` tables. No invoice data is copied or
  duplicated.
- A party statement is a *derived*, read-only projection built by walking
  the same authoritative events every time it is requested: completed/
  posted invoices, active (``POSTED``) payments, posted returns, and
  posted refunds. It is never stored, and it never substitutes for the
  payment-only invoice balance fields (``SalesInvoice.balance_due`` /
  ``PurchaseInvoice.remaining_balance``), which remain authoritative on
  their own models and are recalculated only by ``apps.finance.services``.
- Statement amounts follow the pharmacy's-perspective sign convention from
  BRD 5.9 / ERD 14: positive means the party owes the pharmacy, negative
  means the pharmacy owes the party. A sales invoice is positive, a
  customer payment is negative, a posted customer return is negative, and
  a posted customer refund is positive (it settles a return credit). A
  purchase invoice is negative, a supplier payment is positive, and a
  posted supplier return is positive (it reduces the payable).
- Every event source (invoices, payments, returns, refunds) is read from
  its own table exactly once, so each event contributes to the statement
  exactly one time; nothing here writes a balance back anywhere.

No new model, migration, or mutable balance/summary table is introduced.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from django.core.exceptions import PermissionDenied
from django.db.models import Q

from apps.purchasing.models import PurchaseInvoice
from apps.returns.models import CustomerRefund, CustomerReturn, RefundStatus, ReturnStatus, SupplierReturn
from apps.sales.models import SalesInvoice

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


# ---------------------------------------------------------------------------
# Invoice search
# ---------------------------------------------------------------------------


def search_sales_invoices(*, actor, customer=None, status="", payment_status="", query=""):
    """Permission-scoped, filterable search over sales invoices.

    Requires ``sales.view_salesinvoice``. Read-only: does not create,
    change, or duplicate any invoice data.
    """
    _require_permission(actor, "sales.view_salesinvoice")

    invoices = SalesInvoice.objects.select_related("customer").order_by("-created_at", "-id")
    if customer is not None:
        invoices = invoices.filter(customer=customer)
    if status:
        invoices = invoices.filter(status=status)
    if payment_status:
        invoices = invoices.filter(payment_status=payment_status)
    query = (query or "").strip()
    if query:
        invoices = invoices.filter(
            Q(invoice_number__icontains=query)
            | Q(customer__name__icontains=query)
            | Q(customer__code__icontains=query)
            | Q(customer_name_snapshot__icontains=query)
        )
    return invoices


def search_purchase_invoices(*, actor, supplier=None, status="", payment_status="", query=""):
    """Permission-scoped, filterable search over purchase invoices.

    Requires ``purchasing.view_purchaseinvoice``. Read-only: does not
    create, change, or duplicate any invoice data.
    """
    _require_permission(actor, "purchasing.view_purchaseinvoice")

    invoices = PurchaseInvoice.objects.select_related("supplier").order_by("-created_at", "-id")
    if supplier is not None:
        invoices = invoices.filter(supplier=supplier)
    if status:
        invoices = invoices.filter(status=status)
    if payment_status:
        invoices = invoices.filter(payment_status=payment_status)
    query = (query or "").strip()
    if query:
        invoices = invoices.filter(
            Q(invoice_number__icontains=query)
            | Q(supplier__name__icontains=query)
            | Q(supplier__code__icontains=query)
            | Q(supplier_invoice_reference__icontains=query)
        )
    return invoices


# ---------------------------------------------------------------------------
# Derived party statements
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StatementEntry:
    """One chronological, immutable statement line.

    ``amount`` already carries the pharmacy's-perspective sign described in
    the module docstring; ``running_balance`` is computed by the caller
    while walking the sorted entries and is never persisted.
    """

    event_type: str
    occurred_at: object
    reference: str
    amount: Decimal
    source_id: object
    running_balance: Optional[Decimal] = None


def _with_running_balance(entries):
    entries = sorted(entries, key=lambda entry: (entry.occurred_at, entry.event_type, str(entry.source_id)))
    balance = ZERO_MONEY
    rows = []
    for entry in entries:
        balance = _quantize_money(balance + entry.amount)
        rows.append(
            StatementEntry(
                event_type=entry.event_type,
                occurred_at=entry.occurred_at,
                reference=entry.reference,
                amount=_quantize_money(entry.amount),
                source_id=entry.source_id,
                running_balance=balance,
            )
        )
    return rows, balance


def customer_statement(*, actor, customer):
    """Chronological derived statement for one customer, plus its net
    balance.

    Requires ``parties.view_customer`` (party visibility) and
    ``finance.view_customerpayment`` (payment visibility), keeping party
    financial detail isolated by permission. Returns ``(entries,
    net_balance)``; ``net_balance`` is a separate derived figure from
    ``SalesInvoice.balance_due`` and is never written back to any model.
    """
    _require_permission(actor, "parties.view_customer")
    _require_permission(actor, "finance.view_customerpayment")

    entries = []

    invoices = SalesInvoice.objects.filter(
        customer=customer,
        status=SalesInvoice.Status.COMPLETED,
    )
    for invoice in invoices:
        entries.append(
            StatementEntry(
                event_type="SALES_INVOICE",
                occurred_at=invoice.completed_at or invoice.created_at,
                reference=invoice.invoice_number,
                amount=invoice.grand_total,
                source_id=invoice.id,
            )
        )

    payments = CustomerPayment.objects.filter(
        customer=customer,
        status=PaymentStatus.POSTED,
    ).select_related("sales_invoice")
    for payment in payments:
        entries.append(
            StatementEntry(
                event_type="CUSTOMER_PAYMENT",
                occurred_at=payment.paid_at,
                reference=payment.sales_invoice.invoice_number,
                amount=-payment.amount,
                source_id=payment.id,
            )
        )

    returns = CustomerReturn.objects.filter(
        customer=customer,
        status=ReturnStatus.POSTED,
    )
    for customer_return in returns:
        entries.append(
            StatementEntry(
                event_type="CUSTOMER_RETURN",
                occurred_at=customer_return.posted_at,
                reference=customer_return.return_number,
                amount=-customer_return.return_total,
                source_id=customer_return.id,
            )
        )

    refunds = CustomerRefund.objects.filter(
        customer_return__customer=customer,
        status=RefundStatus.POSTED,
    ).select_related("customer_return")
    for refund in refunds:
        entries.append(
            StatementEntry(
                event_type="CUSTOMER_REFUND",
                occurred_at=refund.refunded_at,
                reference=refund.refund_number,
                amount=refund.amount,
                source_id=refund.id,
            )
        )

    return _with_running_balance(entries)


def supplier_statement(*, actor, supplier):
    """Chronological derived statement for one supplier, plus its net
    balance.

    Requires ``parties.view_supplier`` (party visibility) and
    ``finance.view_supplierpayment`` (payment visibility). Returns
    ``(entries, net_balance)``; ``net_balance`` is a separate derived
    figure from ``PurchaseInvoice.remaining_balance`` and is never written
    back to any model. Supplier returns have no separate refund record in
    Phase 1; the posted return itself reduces the payable.
    """
    _require_permission(actor, "parties.view_supplier")
    _require_permission(actor, "finance.view_supplierpayment")

    entries = []

    invoices = PurchaseInvoice.objects.filter(
        supplier=supplier,
        status=PurchaseInvoice.Status.POSTED,
    )
    for invoice in invoices:
        entries.append(
            StatementEntry(
                event_type="PURCHASE_INVOICE",
                occurred_at=invoice.posted_at or invoice.created_at,
                reference=invoice.invoice_number,
                amount=-invoice.grand_total,
                source_id=invoice.id,
            )
        )

    payments = SupplierPayment.objects.filter(
        supplier=supplier,
        status=PaymentStatus.POSTED,
    ).select_related("purchase_invoice")
    for payment in payments:
        entries.append(
            StatementEntry(
                event_type="SUPPLIER_PAYMENT",
                occurred_at=payment.paid_at,
                reference=payment.purchase_invoice.invoice_number,
                amount=payment.amount,
                source_id=payment.id,
            )
        )

    returns = SupplierReturn.objects.filter(
        supplier=supplier,
        status=ReturnStatus.POSTED,
    )
    for supplier_return in returns:
        entries.append(
            StatementEntry(
                event_type="SUPPLIER_RETURN",
                occurred_at=supplier_return.posted_at,
                reference=supplier_return.return_number,
                amount=supplier_return.return_total,
                source_id=supplier_return.id,
            )
        )

    return _with_running_balance(entries)
