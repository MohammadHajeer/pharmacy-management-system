"""Essential Phase 1 report queries.

Implements ticket E4-T04 / 4400 ("Deliver the essential Phase 1 report
queries") per BRD 5.13 and ERD Section 14 (Reports and Balances).

``apps.reports`` has no database models (BRD 7 / ERD Section 14): every
function here is a derived, permission-scoped read over the existing
owning-app models. Nothing is written, cached in a summary table, or
introduced as a new source of truth, and reports sum already-stored
posted/completed monetary snapshots rather than recalculating historical
tax (BRD 9.1).

Permission scoping follows the BRD 6 capability matrix:

- operational reports (sales, purchases, inventory, low stock,
  near-expiry, expired stock) use the same owning-app ``view_*``
  permission Pharmacist/Inventory Manager already hold for that data;
- financial reports (receivables, payables, customer/supplier payments,
  COGS/gross profit) require ``finance.view_financial_reports``, assigned
  only to Owner / Admin and Accountant.

Receivables/payables report both the payment-only invoice balance (the
authoritative ``SalesInvoice.balance_due`` / ``PurchaseInvoice.
remaining_balance`` fields, untouched by returns/refunds) and the
separate net party statement balance built from ``apps.finance.queries``,
which applies every invoice/payment/return/refund event exactly once.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied
from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.catalog.models import Medicine
from apps.core.models import PharmacySettings
from apps.finance.models import CustomerPayment, PaymentStatus, SupplierPayment
from apps.inventory.models import MedicineBatch
from apps.parties.models import Customer, Supplier
from apps.purchasing.models import PurchaseInvoice
from apps.returns.models import CustomerRefund, CustomerReturn, RefundStatus, ReturnStatus, SupplierReturn
from apps.sales.models import SalesInvoice, SalesInvoiceLine

MONEY_QUANTUM = Decimal("0.01")
ZERO_MONEY = Decimal("0.00")
MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)
QUANTITY_FIELD = DecimalField(max_digits=14, decimal_places=3)
VALUATION_FIELD = DecimalField(max_digits=18, decimal_places=4)

FINANCIAL_REPORT_PERMISSION = "finance.view_financial_reports"


def _require_permission(actor, permission):
    if not getattr(actor, "is_authenticated", False) or not actor.has_perm(permission):
        raise PermissionDenied


def _quantize_money(value):
    return (value if value is not None else ZERO_MONEY).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def _date_bounds(queryset, field, date_from, date_to):
    if date_from is not None:
        queryset = queryset.filter(**{f"{field}__date__gte": date_from})
    if date_to is not None:
        queryset = queryset.filter(**{f"{field}__date__lte": date_to})
    return queryset


# ---------------------------------------------------------------------------
# Sales / purchases
# ---------------------------------------------------------------------------


def sales_report(*, actor, date_from=None, date_to=None):
    """Completed-sales summary reconciled to stored invoice snapshots.

    Requires ``sales.view_salesinvoice``.
    """
    _require_permission(actor, "sales.view_salesinvoice")

    invoices = SalesInvoice.objects.filter(status=SalesInvoice.Status.COMPLETED)
    invoices = _date_bounds(invoices, "completed_at", date_from, date_to)

    totals = invoices.aggregate(
        invoice_count=Count("id"),
        subtotal_total=Coalesce(Sum("subtotal"), Value(ZERO_MONEY), output_field=MONEY_FIELD),
        discount_total=Coalesce(Sum("discount_total"), Value(ZERO_MONEY), output_field=MONEY_FIELD),
        tax_total=Coalesce(Sum("tax_total"), Value(ZERO_MONEY), output_field=MONEY_FIELD),
        grand_total=Coalesce(Sum("grand_total"), Value(ZERO_MONEY), output_field=MONEY_FIELD),
    )
    return {
        "invoice_count": totals["invoice_count"],
        "subtotal_total": _quantize_money(totals["subtotal_total"]),
        "discount_total": _quantize_money(totals["discount_total"]),
        "tax_total": _quantize_money(totals["tax_total"]),
        "grand_total": _quantize_money(totals["grand_total"]),
        "invoices": invoices.order_by("-completed_at", "-id"),
    }


def purchases_report(*, actor, date_from=None, date_to=None):
    """Posted-purchases summary reconciled to stored invoice snapshots.

    Requires ``purchasing.view_purchaseinvoice``.
    """
    _require_permission(actor, "purchasing.view_purchaseinvoice")

    invoices = PurchaseInvoice.objects.filter(status=PurchaseInvoice.Status.POSTED)
    invoices = _date_bounds(invoices, "posted_at", date_from, date_to)

    totals = invoices.aggregate(
        invoice_count=Count("id"),
        subtotal_total=Coalesce(Sum("subtotal"), Value(ZERO_MONEY), output_field=MONEY_FIELD),
        discount_total=Coalesce(Sum("discount_total"), Value(ZERO_MONEY), output_field=MONEY_FIELD),
        tax_total=Coalesce(Sum("tax_total"), Value(ZERO_MONEY), output_field=MONEY_FIELD),
        grand_total=Coalesce(Sum("grand_total"), Value(ZERO_MONEY), output_field=MONEY_FIELD),
    )
    return {
        "invoice_count": totals["invoice_count"],
        "subtotal_total": _quantize_money(totals["subtotal_total"]),
        "discount_total": _quantize_money(totals["discount_total"]),
        "tax_total": _quantize_money(totals["tax_total"]),
        "grand_total": _quantize_money(totals["grand_total"]),
        "invoices": invoices.order_by("-posted_at", "-id"),
    }


# ---------------------------------------------------------------------------
# Inventory / expiry
# ---------------------------------------------------------------------------


def current_inventory_report(*, actor):
    """On-hand quantity and acquisition-cost valuation from current active
    batches.

    Requires ``inventory.view_medicinebatch``.
    """
    _require_permission(actor, "inventory.view_medicinebatch")

    batches = MedicineBatch.objects.filter(is_active=True, quantity_available_base__gt=0)

    by_medicine = (
        batches.values("medicine_id", "medicine__name")
        .annotate(
            quantity_on_hand_base=Sum("quantity_available_base"),
            valuation=Coalesce(
                Sum(F("quantity_available_base") * F("acquisition_cost_per_base_unit")),
                Value(Decimal("0.0000")),
                output_field=VALUATION_FIELD,
            ),
        )
        .order_by("medicine__name")
    )
    total_valuation = batches.aggregate(
        total=Coalesce(
            Sum(F("quantity_available_base") * F("acquisition_cost_per_base_unit")),
            Value(Decimal("0.0000")),
            output_field=VALUATION_FIELD,
        )
    )["total"]
    return {
        "by_medicine": list(by_medicine),
        "batches": batches.select_related("medicine").order_by("medicine__name", "expiry_date", "id"),
        "total_valuation": _quantize_money(total_valuation),
    }


def _default_low_stock_threshold():
    settings_row = PharmacySettings.objects.filter(singleton_key=1).first()
    return settings_row.default_low_stock_threshold if settings_row else Decimal("0.000")


def low_stock_report(*, actor):
    """Active medicines whose current stock is at or below their low-stock
    threshold (own threshold, falling back to the pharmacy default).

    Requires ``inventory.view_medicinebatch``.
    """
    _require_permission(actor, "inventory.view_medicinebatch")

    default_threshold = _default_low_stock_threshold()
    eligible = Q(batches__is_active=True)
    medicines = Medicine.objects.filter(is_active=True).annotate(
        available_stock_base=Coalesce(
            Sum("batches__quantity_available_base", filter=eligible),
            Value(Decimal("0.000")),
            output_field=QUANTITY_FIELD,
        )
    )

    rows = []
    for medicine in medicines:
        threshold = (
            medicine.low_stock_threshold_base
            if medicine.low_stock_threshold_base is not None
            else default_threshold
        )
        if medicine.available_stock_base <= threshold:
            rows.append(
                {
                    "medicine": medicine,
                    "available_stock_base": medicine.available_stock_base,
                    "threshold": threshold,
                }
            )
    rows.sort(key=lambda row: row["medicine"].name)
    return rows


def near_expiry_report(*, actor, as_of=None):
    """Active, non-expired batches expiring within the pharmacy's expiry-
    warning window (UTC business timezone, BRD 9).

    Requires ``inventory.view_medicinebatch``.
    """
    _require_permission(actor, "inventory.view_medicinebatch")

    today = as_of or timezone.localdate()
    settings_row = PharmacySettings.objects.filter(singleton_key=1).first()
    warning_days = settings_row.expiry_warning_days if settings_row else 90
    horizon = today + timedelta(days=warning_days)

    return (
        MedicineBatch.objects.filter(
            is_active=True,
            quantity_available_base__gt=0,
            expiry_date__gte=today,
            expiry_date__lte=horizon,
        )
        .select_related("medicine")
        .order_by("expiry_date", "first_received_at", "id")
    )


def expired_stock_report(*, actor, as_of=None):
    """Active batches that are already expired (UTC business timezone) and
    still carry on-hand quantity.

    Requires ``inventory.view_medicinebatch``.
    """
    _require_permission(actor, "inventory.view_medicinebatch")

    today = as_of or timezone.localdate()
    return (
        MedicineBatch.objects.filter(
            is_active=True,
            quantity_available_base__gt=0,
            expiry_date__lt=today,
        )
        .select_related("medicine")
        .order_by("expiry_date", "first_received_at", "id")
    )


# ---------------------------------------------------------------------------
# Financial reports (require finance.view_financial_reports)
# ---------------------------------------------------------------------------


def customer_receivables_report(*, actor):
    """Customer receivables from two distinct, non-substitutable angles
    (BRD 5.9 / ERD 14, AC #4):

    - ``invoice_balance_total``: the sum of payment-only
      ``SalesInvoice.balance_due`` (unaffected by returns/refunds);
    - ``net_receivables_total`` / ``by_customer``: the separate net
      party-statement balance, built from invoices, active payments,
      posted returns, and posted refunds, each applied exactly once.

    Requires ``finance.view_financial_reports``.
    """
    _require_permission(actor, FINANCIAL_REPORT_PERMISSION)

    invoice_balance_total = SalesInvoice.objects.filter(
        status=SalesInvoice.Status.COMPLETED,
        balance_due__gt=0,
    ).aggregate(total=Coalesce(Sum("balance_due"), Value(ZERO_MONEY), output_field=MONEY_FIELD))["total"]

    invoice_totals = _grouped_sum(
        SalesInvoice.objects.filter(status=SalesInvoice.Status.COMPLETED, customer__isnull=False),
        "customer_id",
        "grand_total",
    )
    payment_totals = _grouped_sum(
        CustomerPayment.objects.filter(status=PaymentStatus.POSTED, customer__isnull=False),
        "customer_id",
        "amount",
    )
    return_totals = _grouped_sum(
        CustomerReturn.objects.filter(status=ReturnStatus.POSTED, customer__isnull=False),
        "customer_id",
        "return_total",
    )
    refund_totals = _grouped_sum(
        CustomerRefund.objects.filter(status=RefundStatus.POSTED, customer_return__customer__isnull=False),
        "customer_return__customer_id",
        "amount",
    )

    customer_ids = set(invoice_totals) | set(payment_totals) | set(return_totals) | set(refund_totals)
    customer_names = dict(
        Customer.objects.filter(id__in=customer_ids).values_list("id", "name")
    )
    by_customer = []
    net_receivables_total = ZERO_MONEY
    for customer_id in customer_ids:
        net_balance = _quantize_money(
            invoice_totals.get(customer_id, ZERO_MONEY)
            - payment_totals.get(customer_id, ZERO_MONEY)
            - return_totals.get(customer_id, ZERO_MONEY)
            + refund_totals.get(customer_id, ZERO_MONEY)
        )
        net_receivables_total += net_balance
        by_customer.append(
            {
                "customer_id": customer_id,
                "customer_name": customer_names.get(customer_id, ""),
                "net_balance": net_balance,
            }
        )
    by_customer.sort(key=lambda row: row["customer_name"])

    return {
        "invoice_balance_total": _quantize_money(invoice_balance_total),
        "net_receivables_total": _quantize_money(net_receivables_total),
        "by_customer": by_customer,
    }


def supplier_payables_report(*, actor):
    """Supplier payables from two distinct, non-substitutable angles,
    mirroring ``customer_receivables_report`` for the supplier side.

    Requires ``finance.view_financial_reports``.
    """
    _require_permission(actor, FINANCIAL_REPORT_PERMISSION)

    invoice_balance_total = PurchaseInvoice.objects.filter(
        status=PurchaseInvoice.Status.POSTED,
        remaining_balance__gt=0,
    ).aggregate(
        total=Coalesce(Sum("remaining_balance"), Value(ZERO_MONEY), output_field=MONEY_FIELD)
    )["total"]

    invoice_totals = _grouped_sum(
        PurchaseInvoice.objects.filter(status=PurchaseInvoice.Status.POSTED),
        "supplier_id",
        "grand_total",
    )
    payment_totals = _grouped_sum(
        SupplierPayment.objects.filter(status=PaymentStatus.POSTED),
        "supplier_id",
        "amount",
    )
    return_totals = _grouped_sum(
        SupplierReturn.objects.filter(status=ReturnStatus.POSTED),
        "supplier_id",
        "return_total",
    )

    supplier_ids = set(invoice_totals) | set(payment_totals) | set(return_totals)
    supplier_names = dict(
        Supplier.objects.filter(id__in=supplier_ids).values_list("id", "name")
    )
    by_supplier = []
    net_payable_total = ZERO_MONEY
    for supplier_id in supplier_ids:
        # Pharmacy's-perspective net balance (invoice negative, payment and
        # return positive); the payable amount is the amount owed, i.e. the
        # negated net balance when it is negative.
        net_balance = _quantize_money(
            -invoice_totals.get(supplier_id, ZERO_MONEY)
            + payment_totals.get(supplier_id, ZERO_MONEY)
            + return_totals.get(supplier_id, ZERO_MONEY)
        )
        payable_amount = _quantize_money(-net_balance) if net_balance < 0 else ZERO_MONEY
        net_payable_total += payable_amount
        by_supplier.append(
            {
                "supplier_id": supplier_id,
                "supplier_name": supplier_names.get(supplier_id, ""),
                "net_balance": net_balance,
                "payable_amount": payable_amount,
            }
        )
    by_supplier.sort(key=lambda row: row["supplier_name"])

    return {
        "invoice_balance_total": _quantize_money(invoice_balance_total),
        "net_payables_total": _quantize_money(net_payable_total),
        "by_supplier": by_supplier,
    }


def _grouped_sum(queryset, group_field, amount_field):
    rows = queryset.values(group_field).annotate(
        total=Coalesce(Sum(amount_field), Value(ZERO_MONEY), output_field=MONEY_FIELD)
    )
    return {row[group_field]: row["total"] for row in rows}


def customer_payments_report(*, actor, date_from=None, date_to=None):
    """Posted customer payments summary.

    Requires ``finance.view_financial_reports``.
    """
    _require_permission(actor, FINANCIAL_REPORT_PERMISSION)

    payments = CustomerPayment.objects.filter(status=PaymentStatus.POSTED)
    payments = _date_bounds(payments, "paid_at", date_from, date_to)
    totals = payments.aggregate(
        payment_count=Count("id"),
        amount_total=Coalesce(Sum("amount"), Value(ZERO_MONEY), output_field=MONEY_FIELD),
    )
    return {
        "payment_count": totals["payment_count"],
        "amount_total": _quantize_money(totals["amount_total"]),
        "payments": payments.select_related("customer", "sales_invoice", "payment_method").order_by(
            "-paid_at", "-id"
        ),
    }


def supplier_payments_report(*, actor, date_from=None, date_to=None):
    """Posted supplier payments summary.

    Requires ``finance.view_financial_reports``.
    """
    _require_permission(actor, FINANCIAL_REPORT_PERMISSION)

    payments = SupplierPayment.objects.filter(status=PaymentStatus.POSTED)
    payments = _date_bounds(payments, "paid_at", date_from, date_to)
    totals = payments.aggregate(
        payment_count=Count("id"),
        amount_total=Coalesce(Sum("amount"), Value(ZERO_MONEY), output_field=MONEY_FIELD),
    )
    return {
        "payment_count": totals["payment_count"],
        "amount_total": _quantize_money(totals["amount_total"]),
        "payments": payments.select_related("supplier", "purchase_invoice", "payment_method").order_by(
            "-paid_at", "-id"
        ),
    }


@dataclass(frozen=True)
class CogsGrossProfitReport:
    revenue_excl_tax: Decimal
    cogs: Decimal
    gross_profit: Decimal
    invoice_count: int


def cogs_and_gross_profit_report(*, actor, date_from=None, date_to=None):
    """Basic COGS and gross profit for completed sales in range.

    COGS is derived from stored ``SaleBatchAllocation.acquisition_cost_
    snapshot`` values: allocation quantity × cost is calculated at full
    Decimal precision, summed per sales line, then quantized to two
    decimals before aggregation (BRD 9.1 / ERD 11.3). Revenue is the
    tax-exclusive stored invoice snapshot (``subtotal - discount_total``);
    reports never recalculate historical tax. Gross profit is revenue
    minus COGS.

    Requires ``finance.view_financial_reports``.
    """
    _require_permission(actor, FINANCIAL_REPORT_PERMISSION)

    invoices = SalesInvoice.objects.filter(status=SalesInvoice.Status.COMPLETED)
    invoices = _date_bounds(invoices, "completed_at", date_from, date_to)

    revenue_totals = invoices.aggregate(
        invoice_count=Count("id"),
        subtotal_total=Coalesce(Sum("subtotal"), Value(ZERO_MONEY), output_field=MONEY_FIELD),
        discount_total=Coalesce(Sum("discount_total"), Value(ZERO_MONEY), output_field=MONEY_FIELD),
    )
    revenue_excl_tax = _quantize_money(
        revenue_totals["subtotal_total"] - revenue_totals["discount_total"]
    )

    lines = SalesInvoiceLine.objects.filter(sales_invoice__in=invoices).prefetch_related(
        "batch_allocations"
    )
    cogs_total = ZERO_MONEY
    for line in lines:
        line_cost = sum(
            (allocation.allocated_quantity_base * allocation.acquisition_cost_snapshot)
            for allocation in line.batch_allocations.all()
        ) or Decimal("0")
        cogs_total += _quantize_money(line_cost)

    gross_profit = revenue_excl_tax - cogs_total

    return CogsGrossProfitReport(
        revenue_excl_tax=revenue_excl_tax,
        cogs=cogs_total,
        gross_profit=gross_profit,
        invoice_count=revenue_totals["invoice_count"],
    )
