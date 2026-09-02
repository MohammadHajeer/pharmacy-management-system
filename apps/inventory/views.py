from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from apps.core.models import PharmacySettings
from apps.core.pagination import pagination_context

from .models import MedicineBatch, StockMovement


def _settings():
    return PharmacySettings.objects.filter(singleton_key=1).first() or PharmacySettings()


def _navigation_context(request, label=None):
    root = {"label": "Inventory"}
    if label and request.user.has_perm("inventory.view_medicinebatch"):
        root["url"] = reverse("inventory:batch-list")
    breadcrumbs = [root] + ([{"label": label}] if label else [])
    return {"breadcrumbs": breadcrumbs}


def _batch_queryset(today, default_threshold):
    quantity_field = DecimalField(max_digits=14, decimal_places=3)
    eligible_quantity = (
        MedicineBatch.objects.filter(
            medicine_id=OuterRef("medicine_id"),
            medicine__is_active=True,
            is_active=True,
            expiry_date__gte=today,
        )
        .order_by()
        .values("medicine_id")
        .annotate(total=Sum("quantity_available_base"))
        .values("total")
    )
    return MedicineBatch.objects.select_related("medicine").annotate(
        sellable_quantity=Coalesce(
            Subquery(eligible_quantity, output_field=quantity_field),
            Value(Decimal("0.000"), output_field=quantity_field),
        ),
        stock_threshold=Coalesce(
            "medicine__low_stock_threshold_base",
            Value(default_threshold, output_field=quantity_field),
        ),
    )


def _batch_state(batch, today, warning_end):
    if batch.quantity_available_base == 0:
        return "Empty", "outline"
    if batch.expiry_date < today:
        return "Expired", "destructive"
    if not batch.is_active or not batch.medicine.is_active:
        return "Inactive", "outline"
    if batch.expiry_date <= warning_end:
        return "Near expiry", "warning"
    if batch.sellable_quantity <= batch.stock_threshold:
        return "Low stock", "warning"
    return "Available", "success"


@login_required
@permission_required("inventory.view_medicinebatch", raise_exception=True)
def batch_list(request):
    today = timezone.localdate()
    pharmacy = _settings()
    warning_end = today + timedelta(days=pharmacy.expiry_warning_days)
    batches = _batch_queryset(today, pharmacy.default_low_stock_threshold).order_by(
        "expiry_date", "medicine__name", "batch_number", "id"
    )
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if query:
        batches = batches.filter(
            Q(batch_number__icontains=query)
            | Q(medicine__name__icontains=query)
            | Q(medicine__generic_name__icontains=query)
        )
    filters = {
        "available": Q(quantity_available_base__gt=0, expiry_date__gte=today, is_active=True, medicine__is_active=True),
        "low": Q(sellable_quantity__gt=0, sellable_quantity__lte=F("stock_threshold")),
        "empty": Q(quantity_available_base=0),
        "near_expiry": Q(quantity_available_base__gt=0, expiry_date__range=(today, warning_end)),
        "expired": Q(quantity_available_base__gt=0, expiry_date__lt=today),
        "inactive": Q(is_active=False) | Q(medicine__is_active=False),
    }
    invalid_filter = bool(status and status not in filters)
    if invalid_filter:
        batches = batches.none()
    elif status:
        batches = batches.filter(filters[status])
    page = pagination_context(request, batches, context_name="batches")
    for batch in page["batches"]:
        batch.ui_state, batch.ui_variant = _batch_state(batch, today, warning_end)
    return render(request, "inventory/batch_list.html", {
        **_navigation_context(request),
        **page,
        "query": query,
        "status": status,
        "invalid_filter": invalid_filter,
        "warning_days": pharmacy.expiry_warning_days,
        "status_options": [
            {"value": "", "label": "All batch states"},
            {"value": "available", "label": "Available"},
            {"value": "low", "label": "Low stock medicines"},
            {"value": "empty", "label": "Empty layers"},
            {"value": "near_expiry", "label": "Near expiry"},
            {"value": "expired", "label": "Expired stock"},
            {"value": "inactive", "label": "Inactive"},
        ],
    })


@login_required
@permission_required("inventory.view_medicinebatch", raise_exception=True)
def batch_detail(request, pk):
    today = timezone.localdate()
    pharmacy = _settings()
    batch = get_object_or_404(
        _batch_queryset(today, pharmacy.default_low_stock_threshold), pk=pk
    )
    batch.ui_state, batch.ui_variant = _batch_state(
        batch, today, today + timedelta(days=pharmacy.expiry_warning_days)
    )
    page = {}
    if request.user.has_perm("inventory.view_stockmovement"):
        movements = batch.stock_movements.select_related("performed_by").order_by(
            "-occurred_at", "-id"
        )
        page = pagination_context(request, movements, context_name="movements")
    return render(request, "inventory/batch_detail.html", {
        **_navigation_context(request, batch.batch_number),
        **page,
        "batch": batch,
        "warning_days": pharmacy.expiry_warning_days,
    })


@login_required
@permission_required("inventory.view_stockmovement", raise_exception=True)
def movement_list(request):
    movements = StockMovement.objects.select_related(
        "medicine", "batch", "performed_by"
    ).order_by("-occurred_at", "-id")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if query:
        movements = movements.filter(
            Q(reference_number__icontains=query)
            | Q(batch__batch_number__icontains=query)
            | Q(medicine__name__icontains=query)
            | Q(source_type__icontains=query)
        )
    invalid_filter = bool(status and status not in StockMovement.MovementType.values)
    if invalid_filter:
        movements = movements.none()
    elif status:
        movements = movements.filter(movement_type=status)
    page = pagination_context(request, movements, context_name="movements")
    return render(request, "inventory/movement_list.html", {
        **_navigation_context(request, "Stock movements"),
        **page,
        "query": query,
        "status": status,
        "invalid_filter": invalid_filter,
        "status_options": [{"value": "", "label": "All movement types"}] + [
            {"value": value, "label": label}
            for value, label in StockMovement.MovementType.choices
        ],
    })
