"""Read-only dashboard projections; permissions are checked before querying data."""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Medicine
from apps.core.models import PharmacySettings
from apps.inventory.models import MedicineBatch
from apps.inventory.services import get_fefo_eligible_batches
from apps.purchasing.models import PurchaseInvoice


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
            # There is no batch registry/detail route yet; do not invent a link.
        })
    return {
        "inventory_metrics": stock, "stock_chart_data": stock_chart,
        "expiry_chart_data": expiry_chart, "kpis": kpis,
        "attention_items": attention, "charts": [stock_chart, expiry_chart],
    }


def _purchase_context():
    posted = PurchaseInvoice.objects.filter(status=PurchaseInvoice.Status.POSTED, posted_at__isnull=False)
    # Seed insertion time is not receipt time. Order by the actual posting event.
    recent = list(posted.select_related("supplier").order_by("-posted_at", "-pk")[:5])
    activity = [{
        "reference": invoice.invoice_number, "activity": "Purchase received",
        "party": invoice.supplier_name_snapshot or invoice.supplier.name,
        "when": timezone.localtime(invoice.posted_at),
        "amount": f"{invoice.currency_code} {invoice.grand_total:,.2f}",
        "status": invoice.get_status_display(), "status_variant": "secondary", "icon": "purchases",
        "url": reverse("purchasing:purchase-invoice-detail", args=[invoice.pk]),
    } for invoice in recent]
    if not recent:
        return activity, None
    latest = timezone.localdate(recent[0].posted_at).replace(day=1)
    months = []
    for offset in range(-11, 1):
        index = latest.year * 12 + latest.month - 1 + offset
        months.append(date(index // 12, index % 12 + 1, 1))
    counts = {
        timezone.localdate(row["month"]): row["count"]
        for row in posted.filter(posted_at__date__gte=months[0])
        .annotate(month=TruncMonth("posted_at")).values("month")
        .annotate(count=Count("pk")).order_by("month")
    }
    # One occupied month is not a useful trend. Leave the ledger as its source.
    if len(counts) < 2:
        return activity, None
    chart = _chart(
        "purchase-activity-data", "Purchase Activity", "Receiving history",
        "Posted purchase invoices per month, dated by actual receipt posting time.",
        [month.strftime("%b %Y") for month in months], [counts.get(month, 0) for month in months],
        ["healthy"] * len(months), "invoices", horizontal=False,
    )
    chart["context"] = f"{months[0]:%b %Y}–{latest:%b %Y}: twelve months ending with the latest receipt, including months with no receipts."
    chart["summary"] = f"{sum(chart['values'])} posted purchase invoices across this twelve-month period."
    chart["focus_index"] = len(months) - 1
    chart["focus"] = {
        "label": f"{latest:%b %Y}", "value": chart["values"][-1], "tone": "healthy",
    }
    chart["rows"] = [
        {"month": label, "count": count}
        for label, count in zip(chart["labels"], chart["values"])
    ]
    return activity, chart


def dashboard_context(user):
    context = {"kpis": [], "attention_items": [], "recent_activity": [], "charts": []}
    if user.has_perm("inventory.view_medicinebatch"):
        context.update(_inventory_context(user, timezone.localdate()))
    if user.has_perm("purchasing.view_purchaseinvoice"):
        activity, chart = _purchase_context()
        context["recent_activity"] = activity
        if chart:
            context["purchase_chart_data"] = chart
            context["charts"].append(chart)
    if user.has_perm("sales.view_salesinvoice") or user.has_perm("finance.view_financial_reports"):
        context["dashboard_data_notice"] = (
            "Sales, payments, and net receivables are not included in this inventory-focused dashboard yet."
        )
    return context
