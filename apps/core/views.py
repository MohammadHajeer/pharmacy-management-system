from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .forms import PaymentMethodForm, PharmacySettingsForm, TaxRateForm
from .models import PaymentMethod, PharmacySettings, TaxRate
from .services import (
    process_payment_method_form,
    process_pharmacy_settings_form,
    process_tax_rate_form,
)


def _settings_page_context(
    form,
    *,
    tax_rate_form=None,
    payment_method_form=None,
    editing_tax_rate=None,
    editing_payment_method=None,
    open_modal=None,
):
    selected_tax_rate = form["default_tax_rate"].value()
    selected_tax_rate = str(selected_tax_rate) if selected_tax_rate else ""
    tax_rate_options = [
        {"value": "", "label": "No default tax rate"},
        *(
            {
                "value": str(tax_rate.pk),
                "label": str(tax_rate),
                "disabled": (
                    not tax_rate.is_active
                    and str(tax_rate.pk) != selected_tax_rate
                ),
            }
            for tax_rate in form.fields["default_tax_rate"].queryset
        ),
    ]
    tax_rates = list(TaxRate.objects.order_by("name", "code"))
    payment_methods = list(PaymentMethod.objects.order_by("name", "code"))
    tax_rate_rows = []
    for tax_rate in tax_rates:
        modal_id = f"tax-rate-edit-{tax_rate.pk}"
        row_form = (
            tax_rate_form
            if editing_tax_rate and editing_tax_rate.pk == tax_rate.pk
            else TaxRateForm(instance=tax_rate)
        )
        tax_rate_rows.append(
            {
                "object": tax_rate,
                "form": row_form,
                "modal_id": modal_id,
                "field_prefix": modal_id,
                "action_url": reverse("core:tax-rate-edit", args=[tax_rate.pk]),
            }
        )

    payment_method_rows = []
    for payment_method in payment_methods:
        modal_id = f"payment-method-edit-{payment_method.pk}"
        row_form = (
            payment_method_form
            if editing_payment_method
            and editing_payment_method.pk == payment_method.pk
            else PaymentMethodForm(instance=payment_method)
        )
        payment_method_rows.append(
            {
                "object": payment_method,
                "form": row_form,
                "modal_id": modal_id,
                "field_prefix": modal_id,
                "action_url": reverse(
                    "core:payment-method-edit", args=[payment_method.pk]
                ),
            }
        )

    return {
        "page_context": "Settings",
        "form": form,
        "selected_tax_rate": selected_tax_rate,
        "tax_rate_options": tax_rate_options,
        "tax_rate_rows": tax_rate_rows,
        "payment_method_rows": payment_method_rows,
        "tax_rate_create_form": (
            tax_rate_form
            if editing_tax_rate is None and tax_rate_form is not None
            else TaxRateForm()
        ),
        "payment_method_create_form": (
            payment_method_form
            if editing_payment_method is None and payment_method_form is not None
            else PaymentMethodForm()
        ),
        "open_modal": open_modal,
    }


def _render_settings_page(request, *, settings_form=None, **context_overrides):
    if settings_form is None:
        current_settings = PharmacySettings.objects.filter(singleton_key=1).first()
        settings_form = PharmacySettingsForm(instance=current_settings)
    return render(
        request,
        "core/settings/index.html",
        _settings_page_context(settings_form, **context_overrides),
    )


@login_required
@permission_required("core.change_pharmacysettings", raise_exception=True)
@require_http_methods(["GET", "POST"])
def settings_overview(request):
    if request.method == "POST":
        form = process_pharmacy_settings_form(actor=request.user, data=request.POST)
        if form.is_valid():
            messages.success(request, "Pharmacy settings saved successfully.")
            return redirect("core:settings")
    else:
        current_settings = PharmacySettings.objects.filter(singleton_key=1).first()
        form = PharmacySettingsForm(instance=current_settings)

    return _render_settings_page(request, settings_form=form)


@login_required
@permission_required("core.add_taxrate", raise_exception=True)
@require_http_methods(["GET", "POST"])
def tax_rate_create(request):
    if request.method == "POST":
        form = process_tax_rate_form(actor=request.user, data=request.POST)
        if form.is_valid():
            messages.success(request, "Tax rate added successfully.")
            return redirect("core:settings")
        if request.user.has_perm("core.change_pharmacysettings"):
            return _render_settings_page(
                request,
                tax_rate_form=form,
                open_modal="tax-rate-create",
            )
    else:
        form = TaxRateForm()

    return render(
        request,
        "core/tax_rates/form.html",
        {"page_context": "Add tax rate", "form": form, "is_editing": False},
    )


@login_required
@permission_required("core.change_taxrate", raise_exception=True)
@require_http_methods(["GET", "POST"])
def tax_rate_edit(request, pk):
    tax_rate = get_object_or_404(TaxRate, pk=pk)
    if request.method == "POST":
        form = process_tax_rate_form(
            actor=request.user,
            data=request.POST,
            instance=tax_rate,
        )
        if form.is_valid():
            messages.success(request, "Tax rate updated successfully.")
            return redirect("core:settings")
        if request.user.has_perm("core.change_pharmacysettings"):
            return _render_settings_page(
                request,
                tax_rate_form=form,
                editing_tax_rate=tax_rate,
                open_modal=f"tax-rate-edit-{tax_rate.pk}",
            )
    else:
        form = TaxRateForm(instance=tax_rate)

    return render(
        request,
        "core/tax_rates/form.html",
        {"page_context": "Edit tax rate", "form": form, "is_editing": True},
    )


@login_required
@permission_required("core.add_paymentmethod", raise_exception=True)
@require_http_methods(["GET", "POST"])
def payment_method_create(request):
    if request.method == "POST":
        form = process_payment_method_form(actor=request.user, data=request.POST)
        if form.is_valid():
            messages.success(request, "Payment method added successfully.")
            return redirect("core:settings")
        if request.user.has_perm("core.change_pharmacysettings"):
            return _render_settings_page(
                request,
                payment_method_form=form,
                open_modal="payment-method-create",
            )
    else:
        form = PaymentMethodForm()

    return render(
        request,
        "core/payment_methods/form.html",
        {"page_context": "Add payment method", "form": form, "is_editing": False},
    )


@login_required
@permission_required("core.change_paymentmethod", raise_exception=True)
@require_http_methods(["GET", "POST"])
def payment_method_edit(request, pk):
    payment_method = get_object_or_404(PaymentMethod, pk=pk)
    if request.method == "POST":
        form = process_payment_method_form(
            actor=request.user,
            data=request.POST,
            instance=payment_method,
        )
        if form.is_valid():
            messages.success(request, "Payment method updated successfully.")
            return redirect("core:settings")
        if request.user.has_perm("core.change_pharmacysettings"):
            return _render_settings_page(
                request,
                payment_method_form=form,
                editing_payment_method=payment_method,
                open_modal=f"payment-method-edit-{payment_method.pk}",
            )
    else:
        form = PaymentMethodForm(instance=payment_method)

    return render(
        request,
        "core/payment_methods/form.html",
        {"page_context": "Edit payment method", "form": form, "is_editing": True},
    )
