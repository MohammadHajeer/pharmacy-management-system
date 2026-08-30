from decimal import Decimal

from django.db.models import DecimalField, Exists, Min, OuterRef, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.catalog.models import Medicine, MedicineBarcode, MedicineUnit

from .models import SalesInvoice


STOCK_QUANTITY_FIELD = DecimalField(max_digits=14, decimal_places=3)


def active_pos_medicine_queryset(search_text=""):
    """Return active medicines with sale units and query-only eligible stock data."""
    today = timezone.localdate()
    eligible_batches = Q(
        batches__is_active=True,
        batches__expiry_date__gte=today,
        batches__quantity_available_base__gt=0,
    )
    has_sale_unit = MedicineUnit.objects.filter(
        medicine_id=OuterRef("pk"),
        is_active=True,
        sale_allowed=True,
    )
    queryset = (
        Medicine.objects.filter(is_active=True)
        .filter(Exists(has_sale_unit))
        .annotate(
            available_stock_base=Coalesce(
                Sum("batches__quantity_available_base", filter=eligible_batches),
                Value(Decimal("0.000")),
                output_field=STOCK_QUANTITY_FIELD,
            ),
            earliest_expiry_date=Min("batches__expiry_date", filter=eligible_batches),
        )
        .prefetch_related(
            Prefetch(
                "units",
                queryset=MedicineUnit.objects.filter(
                    is_active=True,
                    sale_allowed=True,
                ).order_by("-is_base_unit", "name"),
                to_attr="pos_sale_units",
            )
        )
        .order_by("name", "id")
        .distinct()
    )

    search_text = search_text.strip()
    if search_text:
        queryset = queryset.filter(
            Q(name__icontains=search_text)
            | Q(generic_name__icontains=search_text)
            | Q(strength__icontains=search_text)
        )
    return queryset


def find_active_pos_barcode(barcode):
    """Resolve an exact active barcode without creating or changing any record."""
    barcode = barcode.strip()
    if not barcode:
        return None
    return (
        MedicineBarcode.objects.select_related("medicine_unit", "medicine_unit__medicine")
        .filter(
            barcode=barcode,
            is_active=True,
            medicine_unit__is_active=True,
            medicine_unit__sale_allowed=True,
            medicine_unit__medicine__is_active=True,
        )
        .first()
    )


def get_pos_medicine(medicine_id):
    return get_object_or_404(active_pos_medicine_queryset(), pk=medicine_id)


def get_draft_sale(pk):
    return get_object_or_404(
        SalesInvoice.objects.filter(status=SalesInvoice.Status.DRAFT)
        .select_related("customer", "prescription", "pharmacist")
        .prefetch_related("lines__medicine", "lines__medicine_unit"),
        pk=pk,
    )
