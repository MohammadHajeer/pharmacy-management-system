from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Medicine, MedicineUnit
from apps.core.models import PharmacySettings
from apps.inventory.services import InsufficientStockError
from apps.parties.models import Supplier

from .forms import PurchaseInvoiceHeaderForm, PurchaseInvoiceLineFormSet
from .models import PurchaseInvoice
from .services import create_draft_purchase_invoice, post_purchase_invoice


def _default_currency_code():
    settings_row = PharmacySettings.objects.filter(singleton_key=1).first()
    return settings_row.currency_code if settings_row else ""


def _select_options():
    supplier_options = [
        {"value": str(supplier.pk), "label": f"{supplier.code} — {supplier.name}"}
        for supplier in Supplier.objects.filter(is_active=True).order_by("name")
    ]
    medicine_options = [
        {"value": str(medicine.pk), "label": medicine.name}
        for medicine in Medicine.objects.filter(is_active=True).order_by("name")
    ]
    unit_options = [
        {
            "value": str(unit.pk),
            "label": f"{unit.medicine.name} — {unit.name}",
        }
        for unit in MedicineUnit.objects.filter(
            is_active=True, purchase_allowed=True
        ).select_related("medicine").order_by("medicine__name", "name")
    ]
    return supplier_options, medicine_options, unit_options


def _validation_error_message(error):
    if hasattr(error, "message_dict"):
        return "; ".join(f"{field}: {', '.join(messages_)}" for field, messages_ in error.message_dict.items())
    return "; ".join(error.messages) if hasattr(error, "messages") else str(error)


@login_required
@permission_required("purchasing.view_purchaseinvoice", raise_exception=True)
def purchase_invoice_list(request):
    invoices = PurchaseInvoice.objects.select_related("supplier").order_by("-created_at")
    return render(request, "purchasing/purchase_invoices/list.html", {"invoices": invoices})


@login_required
@permission_required("purchasing.view_purchaseinvoice", raise_exception=True)
def purchase_invoice_detail(request, pk):
    invoice = get_object_or_404(PurchaseInvoice.objects.select_related("supplier"), pk=pk)
    lines = invoice.lines.select_related("medicine", "medicine_unit")
    return render(
        request,
        "purchasing/purchase_invoices/detail.html",
        {"invoice": invoice, "lines": lines},
    )


@login_required
@permission_required("purchasing.add_purchaseinvoice", raise_exception=True)
def purchase_invoice_create(request):
    header_form = PurchaseInvoiceHeaderForm(
        data=request.POST or None,
        initial={"currency_code": _default_currency_code()},
    )
    formset = PurchaseInvoiceLineFormSet(data=request.POST or None, prefix="lines")

    if request.method == "POST" and header_form.is_valid() and formset.is_valid():
        lines_data = []
        for line_form in formset:
            cleaned = line_form.cleaned_data
            if not cleaned or cleaned.get("DELETE"):
                continue
            lines_data.append(
                {
                    "medicine": cleaned["medicine"],
                    "medicine_unit": cleaned["medicine_unit"],
                    "quantity": cleaned["quantity"],
                    "unit_cost": cleaned["unit_cost"],
                    "discount_amount": cleaned.get("discount_amount") or Decimal("0.00"),
                    "tax_rate_percent": cleaned.get("tax_rate_percent") or Decimal("0.0000"),
                    "batch_number": cleaned["batch_number"],
                    "expiry_date": cleaned["expiry_date"],
                }
            )

        try:
            invoice = create_draft_purchase_invoice(
                actor=request.user,
                supplier=header_form.cleaned_data["supplier"],
                invoice_date=header_form.cleaned_data["invoice_date"],
                due_date=header_form.cleaned_data.get("due_date"),
                supplier_invoice_reference=header_form.cleaned_data.get(
                    "supplier_invoice_reference", ""
                ),
                currency_code=header_form.cleaned_data["currency_code"],
                lines_data=lines_data,
            )
        except ValidationError as error:
            messages.error(request, _validation_error_message(error))
        except PermissionDenied:
            raise
        else:
            messages.success(request, "Purchase invoice draft created.")
            return redirect("purchasing:purchase-invoice-detail", pk=invoice.pk)

    supplier_options, medicine_options, unit_options = _select_options()
    return render(
        request,
        "purchasing/purchase_invoices/form.html",
        {
            "header_form": header_form,
            "formset": formset,
            "supplier_options": supplier_options,
            "medicine_options": medicine_options,
            "unit_options": unit_options,
        },
    )


@login_required
@permission_required("purchasing.post_purchaseinvoice", raise_exception=True)
@require_POST
def purchase_invoice_post(request, pk):
    try:
        invoice = post_purchase_invoice(actor=request.user, purchase_invoice_id=pk)
    except ValidationError as error:
        messages.error(request, _validation_error_message(error))
    except InsufficientStockError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Purchase invoice {invoice.invoice_number} posted.")
    return redirect("purchasing:purchase-invoice-detail", pk=pk)
