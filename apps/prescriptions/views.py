from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import PrescriptionForm, PrescriptionItemFormSet
from .queries import get_prescription_for_detail, prescription_list_queryset
from .services import process_prescription_forms


@login_required
@permission_required(
    (
        "prescriptions.view_prescription",
        "prescriptions.view_prescriptionitem",
    ),
    raise_exception=True,
)
def prescription_list(request):
    return render(
        request,
        "prescriptions/prescription_list.html",
        {
            "page_context": "Prescriptions",
            "prescriptions": prescription_list_queryset(),
        },
    )


@login_required
@permission_required(
    (
        "prescriptions.view_prescription",
        "prescriptions.view_prescriptionitem",
    ),
    raise_exception=True,
)
def prescription_detail(request, pk):
    return render(
        request,
        "prescriptions/prescription_detail.html",
        {
            "page_context": "Prescription details",
            "prescription": get_prescription_for_detail(pk),
        },
    )


@login_required
@permission_required(
    (
        "prescriptions.add_prescription",
        "prescriptions.add_prescriptionitem",
    ),
    raise_exception=True,
)
@require_http_methods(["GET", "POST"])
def prescription_create(request):
    saved_prescription = None
    if request.method == "POST":
        if request.FILES:
            form = PrescriptionForm(data=request.POST)
            item_formset = PrescriptionItemFormSet(data=request.POST)
            form.is_valid()
            item_formset.is_valid()
            form.add_error(
                None,
                "Prescription attachment uploads are not enabled in Phase 1.",
            )
        else:
            form, item_formset, saved_prescription = process_prescription_forms(
                actor=request.user,
                data=request.POST,
            )
    else:
        form = PrescriptionForm()
        item_formset = PrescriptionItemFormSet()

    if saved_prescription is not None:
        return redirect("prescriptions:detail", pk=saved_prescription.pk)

    return render(
        request,
        "prescriptions/prescription_form.html",
        {
            "page_context": "New prescription",
            "form": form,
            "item_formset": item_formset,
            "attachment_upload_enabled": False,
        },
    )
