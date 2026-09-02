from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.catalog.models import Medicine
from apps.core.pagination import pagination_context
from apps.parties.models import Customer, Prescriber

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
    prescriptions = prescription_list_queryset()
    query = request.GET.get("q", "").strip()
    if query:
        prescriptions = prescriptions.filter(
            Q(reference_number__icontains=query)
            | Q(customer__name__icontains=query)
            | Q(customer__code__icontains=query)
            | Q(prescriber__name__icontains=query)
            | Q(items__medicine__name__icontains=query)
        ).distinct()
    page = pagination_context(request, prescriptions, context_name="prescriptions")
    return render(
        request,
        "prescriptions/prescription_list.html",
        {
            "page_context": "Prescriptions",
            "breadcrumbs": [{"label": "Prescriptions"}],
            **page,
            "query": query,
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
    prescription = get_prescription_for_detail(pk)
    return render(
        request,
        "prescriptions/prescription_detail.html",
        {
            "page_context": "Prescription details",
            "breadcrumbs": [
                {"label": "Prescriptions", "url": reverse("prescriptions:list")},
                {"label": prescription.reference_number or "Prescription"},
            ],
            "prescription": prescription,
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
    return _prescription_form(request)


@login_required
@permission_required(
    (
        "prescriptions.change_prescription",
        "prescriptions.change_prescriptionitem",
    ),
    raise_exception=True,
)
@require_http_methods(["GET", "POST"])
def prescription_update(request, pk):
    return _prescription_form(request, instance=get_prescription_for_detail(pk))


def _prescription_form(request, instance=None):
    creating = instance is None
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
                instance=instance,
            )
    else:
        form = PrescriptionForm(instance=instance)
        item_formset = PrescriptionItemFormSet(instance=instance)

    if saved_prescription is not None:
        messages.success(
            request,
            "Prescription created." if creating else "Prescription updated.",
        )
        return redirect("prescriptions:detail", pk=saved_prescription.pk)

    customer_options = [
        {"value": str(customer.pk), "label": f"{customer.code} — {customer.name}"}
        for customer in Customer.objects.filter(is_active=True).order_by("name", "id")
    ]
    prescriber_options = [
        {"value": str(prescriber.pk), "label": prescriber.name}
        for prescriber in Prescriber.objects.filter(is_active=True).order_by("name", "id")
    ]
    medicine_options = [
        {"value": str(medicine.pk), "label": medicine.name}
        for medicine in Medicine.objects.filter(is_active=True).order_by("name", "id")
    ]
    root = {"label": "Prescriptions", "url": reverse("prescriptions:list")}

    return render(
        request,
        "prescriptions/prescription_form.html",
        {
            "page_context": "New prescription" if creating else "Edit prescription",
            "breadcrumbs": [
                root,
                {"label": "New" if creating else (instance.reference_number or "Edit")},
            ],
            "form": form,
            "item_formset": item_formset,
            "attachment_upload_enabled": False,
            "creating": creating,
            "prescription": instance,
            "customer_options": customer_options,
            "prescriber_options": prescriber_options,
            "medicine_options": medicine_options,
        },
    )
