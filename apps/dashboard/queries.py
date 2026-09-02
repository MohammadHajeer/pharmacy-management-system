"""Read-only dashboard projections; permissions are checked before querying data."""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce, TruncMonth
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Medicine
from apps.core.models import PharmacySettings
from apps.finance.models import CustomerPayment, PaymentStatus
from apps.inventory.models import MedicineBatch
from apps.inventory.services import get_fefo_eligible_batches
from apps.purchasing.models import PurchaseInvoice
from apps.sales.models import SalesInvoice, SalesInvoiceLine


def _chart(key, title, kicker, description, labels, values, tones, unit, *, horizontal=False):
    return {
        "id": key, "title": title, "kicker": kicker, "description": description,
        "labels": labels, "values": values, "tones": tones, "unit": unit,
        "horizontal": horizontal, "has_data": any(values),
        "summary": "; ".join(f"{label}: {value} {unit}" for label, value in zip(labels, values)) + ".",
    }


def _stock_positions(today, default_threshold):
    # Reuse the authoritative FEFO queryset, including eligibility on expiry day.
    # A correlated aggregate keeps medicines without batches and avoids N+1 reads.
    quantities = (
        get_fefo_eligible_batches(OuterRef("pk"), as_of_date=today)
        .order_by().values("medicine")
        .annotate(total=Sum("quantity_available_base")).values("total")
    )
    return Medicine.objects.filter(is_active=True).annotate(
        sellable_quantity=Coalesce(Subquery(quantities), Value(Decimal("0.000"))),
        stock_threshold=Coalesce("low_stock_threshold_base", Value(default_threshold)),
    )


def _expiry_buckets(today, warning_days):
    """Partition remaining stock using the configured inclusive warning window."""
    urgent_days = min(30, warning_days)
    buckets = [
        ("Expired", Q(expiry_date__lt=today), "danger"),
        ("Today" if urgent_days == 0 else f"0–{urgent_days} days",
         Q(expiry_date__range=(today, today + timedelta(days=urgent_days))), "warning"),
    ]
    if warning_days > urgent_days:
        buckets.append((
            f"{urgent_days + 1}–{warning_days} days",
            Q(expiry_date__range=(today + timedelta(days=urgent_days + 1), today + timedelta(days=warning_days))),
            "watch",
        ))
    buckets.append((f"{warning_days + 1}+ days", Q(expiry_date__gt=today + timedelta(days=warning_days)), "neutral"))
    return buckets


def _inventory_context(user, today):
    # An unsaved instance supplies model defaults without get_or_create on a GET.
    pharmacy = PharmacySettings.objects.filter(singleton_key=1).first() or PharmacySettings()
    warning_days = pharmacy.expiry_warning_days
    positions = _stock_positions(today, pharmacy.default_low_stock_threshold)
    stock = positions.aggregate(
        active=Count("pk"),
        healthy=Count("pk", filter=Q(sellable_quantity__gt=F("stock_threshold"))),
        low=Count("pk", filter=Q(sellable_quantity__gt=0, sellable_quantity__lte=F("stock_threshold"))),
        out=Count("pk", filter=Q(sellable_quantity=0)),
    )
    # Disabling a batch/catalog item does not remove the physical stock still held.
    remaining_batches = MedicineBatch.objects.filter(quantity_available_base__gt=0)
    buckets = _expiry_buckets(today, warning_days)
    expiry = remaining_batches.aggregate(**{
        f"bucket_{index}": Count("pk", filter=condition)
        for index, (_, condition, _) in enumerate(buckets)
    })
    expiry_values = list(expiry.values())
    stock.update(expired=expiry_values[0], near_expiry=sum(expiry_values[1:-1]))
    stock_chart = _chart(
        "stock-health-data", "Stock Health", "Inventory health",
        "Active medicines grouped by their current sellable stock state.",
        ["Healthy", "Low stock", "Out of stock"],
        [stock["healthy"], stock["low"], stock["out"]],
        ["healthy", "warning", "danger"], "medicines",
    )
    stock_chart["context"] = (
        "Low stock includes positive sellable quantities at or below the medicine's "
        "threshold; an unset threshold uses the pharmacy default. Expiry today remains sellable."
    )
    # Presentation emphasis only: preserve the existing stock partition and queries.
    stock_focus = 2 if stock["out"] else 1 if stock["low"] else 0
    stock_chart["focus_index"] = stock_focus
    stock_chart["focus"] = {
        "label": stock_chart["labels"][stock_focus],
        "value": stock_chart["values"][stock_focus],
        "tone": stock_chart["tones"][stock_focus],
    }
    expiry_chart = _chart(
        "expiry-exposure-data", "Expiry Exposure", "Stock protection",
        "Batch cost layers with remaining quantity, including inactive batches and medicines.",
        [label for label, _, _ in buckets], expiry_values,
        [tone for _, _, tone in buckets], "batches",
    )
    expiry_chart["context"] = f"Warning window: {warning_days} days, including today and the final day. Empty batches are excluded."
    expiry_focus = next((index for index, value in enumerate(expiry_values) if value), 0)
    expiry_chart["focus_index"] = expiry_focus
    expiry_chart["focus"] = {
        "label": expiry_chart["labels"][expiry_focus],
        "value": expiry_values[expiry_focus],
        "tone": expiry_chart["tones"][expiry_focus],
    }
    kpis = [
        {"label": "Active Medicines", "value": stock["active"], "context": "Active catalog records, with or without stock", "tone": "neutral"},
        {"label": "Low Stock", "value": stock["low"], "context": "Positive sellable stock at or below threshold", "tone": "warning" if stock["low"] else "neutral"},
        {"label": "Out of Stock", "value": stock["out"], "context": "Active medicines without sellable stock", "tone": "destructive" if stock["out"] else "neutral"},
        {"label": "Expiring Soon", "value": stock["near_expiry"], "context": f"Remaining batches within {warning_days} days", "tone": "warning" if stock["near_expiry"] else "neutral"},
    ]
    attention = []
    can_link_medicine = user.has_perm("catalog.view_medicine")
    for medicine in positions.filter(sellable_quantity__lte=F("stock_threshold")).order_by("sellable_quantity", "name", "pk")[:3]:
        out = medicine.sellable_quantity == 0
        attention.append({
            "title": medicine.name,
            "detail": f"{medicine.sellable_quantity:,.3f} sellable base units · threshold {medicine.stock_threshold:,.3f}",
            "status": "Out of stock" if out else "Low stock",
            "status_variant": "destructive" if out else "warning", "group": "Stock",
            "url": reverse("catalog:medicine-detail", args=[medicine.pk]) if can_link_medicine else None,
        })
    for batch in remaining_batches.filter(expiry_date__lte=today + timedelta(days=warning_days)).select_related("medicine").order_by("expiry_date", "pk")[:3]:
        expired = batch.expiry_date < today
        attention.append({
            "title": batch.medicine.name,
            "batch_number": batch.batch_number,
            "detail": f"Expiry {batch.expiry_date:%d %b %Y} · {batch.quantity_available_base:,.3f} base units remaining",
            "status": "Expired" if expired else "Near expiry",
            "status_variant": "destructive" if expired else "warning", "group": "Expiry",
            "url": reverse("inventory:batch-detail", args=[batch.pk]) if user.has_perm("inventory.view_medicinebatch") else None,
        })
    return {
        "inventory_metrics": stock, "stock_chart_data": stock_chart,
        "expiry_chart_data": expiry_chart, "kpis": kpis,
        "attention_items": attention, "charts": [stock_chart, expiry_chart],
    }


def _local_month(value):
    return timezone.localdate(value).replace(day=1)


def _month_range(first, last):
    months = []
    index = first.year * 12 + first.month - 1
    final = last.year * 12 + last.month - 1
    while index <= final:
        months.append(date(index // 12, index % 12 + 1, 1))
        index += 1
    return months


def _money(currency_code, value):
    amount = value or Decimal("0.00")
    return f"{currency_code + ' ' if currency_code else ''}{amount:,.2f}"


def _analytics_chart(
    *,
    key,
    title,
    kicker,
    description,
    labels,
    values,
    unit,
    variant="bar",
    tones=None,
    datasets=None,
    currency_code="",
    horizontal=False,
    empty_message,
    context="",
    summary="",
    rows=None,
    table_headers=None,
    legend=None,
):
    plotted_values = values
    if datasets:
        plotted_values = [
            value for dataset in datasets for value in dataset["values"]
        ]
    return {
        "id": key,
        "title": title,
        "kicker": kicker,
        "description": description,
        "labels": labels,
        "values": values,
        "tones": tones or [],
        "datasets": datasets or [],
        "unit": unit,
        "variant": variant,
        "currency_code": currency_code,
        "horizontal": horizontal,
        "has_data": any(value != 0 for value in plotted_values),
        "empty_message": empty_message,
        "context": context,
        "summary": summary,
        "rows": rows or [],
        "table_headers": table_headers or [],
        "legend": legend or [],
    }


def _completed_sales(currency_code):
    queryset = SalesInvoice.objects.filter(
        status=SalesInvoice.Status.COMPLETED,
        completed_at__isnull=False,
    )
    if currency_code:
        queryset = queryset.filter(currency_code=currency_code)
    return queryset


def _sales_series(currency_code):
    rows = list(
        _completed_sales(currency_code)
        .annotate(month=TruncMonth("completed_at"))
        .values("month")
        .annotate(value=Sum("grand_total"), count=Count("pk"))
        .order_by("month")
    )
    if not rows:
        return {"months": [], "values": [], "counts": []}
    values_by_month = {
        _local_month(row["month"]): row["value"] or Decimal("0.00")
        for row in rows
    }
    counts_by_month = {
        _local_month(row["month"]): row["count"] for row in rows
    }
    months = _month_range(min(values_by_month), max(values_by_month))
    return {
        "months": months,
        "values": [values_by_month.get(month, Decimal("0.00")) for month in months],
        "counts": [counts_by_month.get(month, 0) for month in months],
    }


def _sales_context(currency_code, series, current_month):
    labels = [month.strftime("%b %Y") for month in series["months"]]
    total = sum(series["values"], Decimal("0.00"))
    chart = _analytics_chart(
        key="sales-performance-data",
        title="Sales Performance",
        kicker="Completed sales",
        description="Monthly revenue from completed sales only.",
        labels=labels,
        values=series["values"],
        unit="currency",
        variant="line",
        tones=["sales"] * len(labels),
        currency_code=currency_code,
        empty_message="No completed sales yet.",
        context="Draft and void sales are excluded. Months between the first and latest completed sale are zero-filled.",
        summary=(
            f"Completed sales revenue totals {_money(currency_code, total)}"
            f" across {len(labels)} month{'' if len(labels) == 1 else 's'}."
            if labels
            else "No completed sales revenue is available."
        ),
        table_headers=("Month", "Revenue", "Sales"),
        rows=[
            {
                "label": label,
                "values": (_money(currency_code, value), count),
            }
            for label, value, count in zip(labels, series["values"], series["counts"])
        ],
    )

    top_rows = list(
        SalesInvoiceLine.objects.filter(
            sales_invoice__status=SalesInvoice.Status.COMPLETED
        )
        .values("medicine_id", "medicine__name")
        .annotate(quantity=Sum("requested_quantity_base"))
        .order_by("-quantity", "medicine__name", "medicine_id")[:7]
    )
    top_chart = _analytics_chart(
        key="top-selling-data",
        title="Top-Selling Medicines",
        kicker="Dispensing volume",
        description="Medicines ranked by sold base quantity from completed sales.",
        labels=[row["medicine__name"] for row in top_rows],
        values=[row["quantity"] for row in top_rows],
        unit="base units",
        tones=["sales"] * len(top_rows),
        horizontal=True,
        empty_message="No completed sale lines yet.",
        context="Ranking uses requested base quantity snapshots, so different sale units remain comparable. Drafts are excluded.",
        summary=(
            "; ".join(
                f"{row['medicine__name']}: {row['quantity']:,.3f} base units"
                for row in top_rows
            )
            + "."
            if top_rows
            else "No completed medicine sales are available."
        ),
        table_headers=("Medicine", "Sold base quantity"),
        rows=[
            {"label": row["medicine__name"], "values": (f"{row['quantity']:,.3f}",)}
            for row in top_rows
        ],
    )

    month_value = Decimal("0.00")
    if current_month in series["months"]:
        month_value = series["values"][series["months"].index(current_month)]
    kpi = {
        "label": "Sales This Month",
        "value": _money(currency_code, month_value),
        "context": "Completed sales revenue in the current calendar month",
        "tone": "neutral",
    }
    return chart, top_chart, kpi


def _purchase_series(currency_code, months):
    posted = PurchaseInvoice.objects.filter(
        status=PurchaseInvoice.Status.POSTED,
        posted_at__isnull=False,
    )
    if currency_code:
        posted = posted.filter(currency_code=currency_code)
    rows = list(
        posted.annotate(month=TruncMonth("posted_at"))
        .values("month")
        .annotate(value=Sum("grand_total"))
        .order_by("month")
    )
    values_by_month = {
        _local_month(row["month"]): row["value"] or Decimal("0.00")
        for row in rows
    }
    # The commercial comparison uses the completed-sales period so its buckets
    # match Sales Performance. Purchase-only installations fall back to their
    # own observed posted period.
    if not months and values_by_month:
        months = _month_range(min(values_by_month), max(values_by_month))
    return months, [values_by_month.get(month, Decimal("0.00")) for month in months]


def _finance_context(currency_code, sales_series):
    months, purchase_values = _purchase_series(
        currency_code, list(sales_series["months"])
    )
    sales_values_by_month = dict(
        zip(sales_series["months"], sales_series["values"])
    )
    sales_values = [
        sales_values_by_month.get(month, Decimal("0.00")) for month in months
    ]
    labels = [month.strftime("%b %Y") for month in months]
    comparison = _analytics_chart(
        key="purchases-sales-data",
        title="Purchases vs Sales",
        kicker="Commercial activity",
        description="Monthly posted purchasing value compared with completed sales value.",
        labels=labels,
        values=[],
        datasets=[
            {"label": "Completed sales", "values": sales_values, "tone": "sales"},
            {"label": "Posted purchases", "values": purchase_values, "tone": "purchase"},
        ],
        unit="currency",
        variant="grouped-bar",
        currency_code=currency_code,
        empty_message="No completed sales or posted purchases yet.",
        context="This compares transaction values only; the difference is not profit or margin.",
        summary=(
            f"Completed sales total {_money(currency_code, sum(sales_values, Decimal('0.00')))}; "
            f"posted purchases total {_money(currency_code, sum(purchase_values, Decimal('0.00')))}."
            if labels
            else "No monthly commercial activity is available."
        ),
        legend=(
            {"label": "Completed sales", "tone": "sales"},
            {"label": "Posted purchases", "tone": "purchase"},
        ),
        table_headers=("Month", "Completed sales", "Posted purchases"),
        rows=[
            {
                "label": label,
                "values": (
                    _money(currency_code, sales_value),
                    _money(currency_code, purchase_value),
                ),
            }
            for label, sales_value, purchase_value in zip(
                labels, sales_values, purchase_values
            )
        ],
    )

    posted_customer_payments = CustomerPayment.objects.filter(
        status=PaymentStatus.POSTED
    )
    if currency_code:
        posted_customer_payments = posted_customer_payments.filter(
            sales_invoice__currency_code=currency_code
        )
    payment_rows = list(
        posted_customer_payments
        .values("payment_method_id", "payment_method__name")
        .annotate(value=Sum("amount"))
        .order_by("-value", "payment_method__name", "payment_method_id")
    )
    payment_values = [row["value"] for row in payment_rows]
    payment_total = sum(payment_values, Decimal("0.00"))
    payment_tones = [f"series-{index % 5 + 1}" for index in range(len(payment_rows))]
    payment_mix = _analytics_chart(
        key="payment-method-data",
        title="Payment Method Mix",
        kicker="Posted customer payments",
        description="Active customer payment value grouped by the recorded method.",
        labels=[row["payment_method__name"] for row in payment_rows],
        values=payment_values,
        unit="currency",
        variant="doughnut",
        tones=payment_tones,
        currency_code=currency_code,
        empty_message="No posted customer payments yet.",
        context="Reversed customer payments are retained in history but excluded from this active mix.",
        summary=(
            f"Posted customer payments total {_money(currency_code, payment_total)}."
            if payment_rows
            else "No posted customer payment value is available."
        ),
        legend=tuple(
            {"label": row["payment_method__name"], "tone": tone}
            for row, tone in zip(payment_rows, payment_tones)
        ),
        table_headers=("Payment method", "Posted value"),
        rows=[
            {
                "label": row["payment_method__name"],
                "values": (_money(currency_code, row["value"]),),
            }
            for row in payment_rows
        ],
    )

    money_field = DecimalField(max_digits=14, decimal_places=2)
    posted_payments = (
        CustomerPayment.objects.filter(
            sales_invoice_id=OuterRef("pk"),
            status=PaymentStatus.POSTED,
        )
        .values("sales_invoice_id")
        .annotate(total=Sum("amount"))
        .values("total")
    )
    receivable_invoices = _completed_sales(currency_code).filter(
        customer__isnull=False
    ).annotate(
        effective_paid=Coalesce(
            Subquery(posted_payments, output_field=money_field),
            Value(Decimal("0.00"), output_field=money_field),
        )
    ).annotate(
        calculated_balance=ExpressionWrapper(
            F("grand_total") - F("effective_paid"), output_field=money_field
        )
    ).filter(calculated_balance__gt=0)
    receivables = receivable_invoices.aggregate(
        total=Coalesce(
            Sum("calculated_balance"),
            Value(Decimal("0.00"), output_field=money_field),
        ),
        partial=Count("pk", filter=Q(effective_paid__gt=0)),
        unpaid=Count("pk", filter=Q(effective_paid=0)),
    )
    receivables.update(
        formatted_total=_money(currency_code, receivables["total"]),
        has_data=receivables["total"] > 0,
    )
    return comparison, payment_mix, receivables


def _purchase_activity():
    invoices = (
        PurchaseInvoice.objects.filter(
            status=PurchaseInvoice.Status.POSTED, posted_at__isnull=False
        )
        .select_related("supplier")
        .order_by("-posted_at", "-pk")[:5]
    )
    return [
        {
            "reference": invoice.invoice_number,
            "activity": "Purchase received",
            "party": invoice.supplier_name_snapshot or invoice.supplier.name,
            "when": timezone.localtime(invoice.posted_at),
            "amount": _money(invoice.currency_code, invoice.grand_total),
            "status": invoice.get_status_display(),
            "status_variant": "secondary",
            "icon": "purchases",
            "url": reverse("purchasing:purchase-invoice-detail", args=[invoice.pk]),
        }
        for invoice in invoices
    ]


def _sales_activity():
    invoices = _completed_sales("").select_related("customer").order_by(
        "-completed_at", "-pk"
    )[:5]
    return [
        {
            "reference": invoice.invoice_number,
            "activity": "Sale completed",
            "party": invoice.customer_name_snapshot or "Walk-in customer",
            "when": timezone.localtime(invoice.completed_at),
            "amount": _money(invoice.currency_code, invoice.grand_total),
            "status": invoice.get_payment_status_display(),
            "status_variant": (
                "success"
                if invoice.payment_status == SalesInvoice.PaymentStatus.PAID
                else "warning"
                if invoice.payment_status == SalesInvoice.PaymentStatus.PARTIAL
                else "destructive"
            ),
            "icon": "sales",
            "url": reverse("sales:invoice-detail", args=[invoice.pk]),
        }
        for invoice in invoices
    ]


def _customer_payment_activity():
    payments = (
        CustomerPayment.objects.filter(status=PaymentStatus.POSTED)
        .select_related("sales_invoice", "customer", "payment_method")
        .order_by("-paid_at", "-pk")[:5]
    )
    return [
        {
            "reference": payment.reference or payment.sales_invoice.invoice_number,
            "activity": "Customer payment",
            "party": payment.customer.name if payment.customer else "Walk-in customer",
            "when": timezone.localtime(payment.paid_at),
            "amount": _money(payment.sales_invoice.currency_code, payment.amount),
            "status": payment.payment_method.name,
            "status_variant": "secondary",
            "icon": "payments",
            "url": reverse("finance:customer-payment-detail", args=[payment.pk]),
        }
        for payment in payments
    ]


def dashboard_context(user):
    context = {
        "kpis": [],
        "attention_items": [],
        "recent_activity": [],
        "charts": [],
    }
    today = timezone.localdate()
    current_month = today.replace(day=1)
    can_inventory = user.has_perm("inventory.view_medicinebatch")
    can_purchases = user.has_perm("purchasing.view_purchaseinvoice")
    can_sales = user.has_perm("sales.view_salesinvoice")
    can_customer_payments = user.has_perm("finance.view_customerpayment")
    can_finance = user.has_perm("finance.view_financial_reports")

    if can_inventory:
        inventory = _inventory_context(user, today)
        context.update(inventory)
        context["operational_charts"] = list(inventory["charts"])
        context["charts"] = list(inventory["charts"])

    pharmacy = None
    if can_sales or can_finance:
        pharmacy = (
            PharmacySettings.objects.filter(singleton_key=1).first()
            or PharmacySettings()
        )
    currency_code = pharmacy.currency_code if pharmacy else ""

    sales_series = None
    if can_sales or can_finance:
        sales_series = _sales_series(currency_code)
    if can_sales:
        sales_chart, top_chart, sales_kpi = _sales_context(
            currency_code, sales_series, current_month
        )
        context["commercial_charts"] = [sales_chart]
        context["performance_charts"] = [top_chart]
        context["charts"].extend((sales_chart, top_chart))
        context["kpis"].append(sales_kpi)

    if can_finance:
        comparison, payment_mix, receivables = _finance_context(
            currency_code, sales_series
        )
        context["commercial_charts"] = context.get("commercial_charts", []) + [
            comparison
        ]
        context["finance_charts"] = [payment_mix]
        context["receivables"] = receivables
        context["charts"].extend((comparison, payment_mix))

    activity = []
    if can_purchases:
        activity.extend(_purchase_activity())
    if can_sales:
        activity.extend(_sales_activity())
    if can_customer_payments:
        activity.extend(_customer_payment_activity())
    context["recent_activity"] = sorted(
        activity, key=lambda item: item["when"], reverse=True
    )[:5]
    return context
