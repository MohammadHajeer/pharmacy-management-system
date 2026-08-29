from django.core.exceptions import PermissionDenied
from django.db import transaction

from .forms import PaymentMethodForm, PharmacySettingsForm, TaxRateForm
from .models import PharmacySettings


def _require_permission(actor, permission):
    if not getattr(actor, "is_authenticated", False) or not actor.has_perm(
        permission
    ):
        raise PermissionDenied


def process_pharmacy_settings_form(*, actor, data):
    """Validate and save the one operational pharmacy-settings record."""
    _require_permission(actor, "core.change_pharmacysettings")

    current_settings = PharmacySettings.objects.filter(singleton_key=1).first()
    form = PharmacySettingsForm(data=data, instance=current_settings)
    if not form.is_valid():
        return form

    defaults = {field_name: form.cleaned_data[field_name] for field_name in form.fields}
    with transaction.atomic():
        saved_settings, _ = PharmacySettings.objects.update_or_create(
            singleton_key=1,
            defaults=defaults,
        )

    form.instance = saved_settings
    return form


def process_tax_rate_form(*, actor, data, instance=None):
    """Validate and create or update a tax rate with Django model permissions."""
    permission = (
        "core.add_taxrate"
        if instance is None or instance._state.adding
        else "core.change_taxrate"
    )
    _require_permission(actor, permission)

    form = TaxRateForm(data=data, instance=instance)
    if form.is_valid():
        with transaction.atomic():
            form.save()
    return form


def process_payment_method_form(*, actor, data, instance=None):
    """Validate and create, update, or deactivate an approved payment method."""
    permission = (
        "core.add_paymentmethod"
        if instance is None or instance._state.adding
        else "core.change_paymentmethod"
    )
    _require_permission(actor, permission)

    form = PaymentMethodForm(data=data, instance=instance)
    if form.is_valid():
        with transaction.atomic():
            form.save()
    return form
