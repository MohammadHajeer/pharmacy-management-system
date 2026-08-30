from django.core.exceptions import PermissionDenied
from django.db import transaction

from .forms import PrescriptionForm, PrescriptionItemFormSet
from .models import Prescription


def _require_permissions(actor, permissions):
    if not getattr(actor, "is_authenticated", False) or not actor.has_perms(
        permissions
    ):
        raise PermissionDenied


def process_prescription_forms(*, actor, data, instance=None):
    """Validate and atomically create or update a lightweight prescription."""
    is_create = instance is None or instance._state.adding
    permissions = (
        (
            "prescriptions.add_prescription",
            "prescriptions.add_prescriptionitem",
        )
        if is_create
        else (
            "prescriptions.change_prescription",
            "prescriptions.change_prescriptionitem",
        )
    )
    _require_permissions(actor, permissions)

    prescription = instance or Prescription()
    form = PrescriptionForm(data=data, instance=prescription)
    item_formset = PrescriptionItemFormSet(data=data, instance=prescription)
    form_is_valid = form.is_valid()
    formset_is_valid = item_formset.is_valid()

    if not form_is_valid or not formset_is_valid:
        return form, item_formset, None

    with transaction.atomic():
        saved_prescription = form.save(commit=False)
        if is_create:
            saved_prescription.created_by = actor
        saved_prescription.save()

        item_formset.instance = saved_prescription
        item_formset.save()

    return form, item_formset, saved_prescription
