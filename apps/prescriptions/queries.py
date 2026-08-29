from django.db.models import Prefetch
from django.shortcuts import get_object_or_404

from apps.catalog.models import Medicine

from .models import Prescription, PrescriptionItem


def prescription_list_queryset():
    return (
        Prescription.objects.select_related(
            "customer",
            "prescriber",
            "created_by",
        )
        .prefetch_related(
            Prefetch(
                "items",
                queryset=PrescriptionItem.objects.select_related("medicine"),
            )
        )
        .order_by("-prescription_date", "-created_at")
    )


def get_prescription_for_detail(pk):
    return get_object_or_404(prescription_list_queryset(), pk=pk)


def medicine_prescription_warning(medicine_id):
    medicine = Medicine.objects.values("id", "prescription_required").get(
        pk=medicine_id
    )
    return {
        "medicine_id": medicine["id"],
        "prescription_required": medicine["prescription_required"],
    }
