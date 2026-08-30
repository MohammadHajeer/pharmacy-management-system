from decimal import ROUND_HALF_UP

from django.contrib.auth.decorators import login_required, permission_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from apps.catalog.unit_economics import selected_unit_selling_price

from .forms import PosBarcodeLookupForm, PosMedicineSearchForm
from .queries import (
    active_pos_medicine_queryset,
    find_active_pos_barcode,
    get_draft_sale,
    get_pos_medicine,
)
from .services import MONEY_QUANTUM, process_draft_sale


def _unit_payload(unit):
    return {
        "id": str(unit.pk),
        "name": unit.name,
        "conversion_to_base": str(unit.conversion_to_base),
        "selected_unit_price": str(
            selected_unit_selling_price(
                unit.medicine.default_selling_price,
                unit.conversion_to_base,
            )
        ),
        "is_base_unit": unit.is_base_unit,
    }


def _medicine_payload(medicine):
    return {
        "id": str(medicine.pk),
        "name": medicine.name,
        "generic_name": medicine.generic_name,
        "strength": medicine.strength,
        "prescription_required": medicine.prescription_required,
        "default_selling_price": str(medicine.default_selling_price),
        "available_stock_base": str(medicine.available_stock_base),
        "earliest_expiry_date": (
            medicine.earliest_expiry_date.isoformat()
            if medicine.earliest_expiry_date
            else None
        ),
        "units": [_unit_payload(unit) for unit in medicine.pos_sale_units],
    }


def _draft_payload(invoice):
    lines = []
    for line in invoice.lines.all():
        line_subtotal = (line.quantity * line.unit_price).quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        lines.append(
            {
                "id": str(line.pk),
                "medicine_id": str(line.medicine_id),
                "medicine_description": line.medicine_description_snapshot,
                "medicine_unit_id": str(line.medicine_unit_id),
                "unit_name": line.unit_name_snapshot,
                "quantity": str(line.quantity),
                "conversion_to_base": str(line.conversion_to_base_snapshot),
                "requested_quantity_base": str(line.requested_quantity_base),
                "unit_price": str(line.unit_price),
                "line_subtotal": str(line_subtotal),
                "discount_amount": str(line.discount_amount),
                "tax_rate_percent": str(line.tax_rate_percent),
                "tax_amount": str(line.tax_amount),
                "line_total": str(line.line_total),
                "prescription_required": line.prescription_required_snapshot,
                "prescription_warning_acknowledged": (
                    line.prescription_warning_acknowledged
                ),
            }
        )
    return {
        "id": str(invoice.pk),
        "status": invoice.status,
        "customer_id": str(invoice.customer_id) if invoice.customer_id else None,
        "prescription_id": (
            str(invoice.prescription_id) if invoice.prescription_id else None
        ),
        "currency_code": invoice.currency_code,
        "subtotal": str(invoice.subtotal),
        "discount_total": str(invoice.discount_total),
        "tax_total": str(invoice.tax_total),
        "grand_total": str(invoice.grand_total),
        "paid_total": str(invoice.paid_total),
        "balance_due": str(invoice.balance_due),
        "payment_status": invoice.payment_status,
        "lines": lines,
    }


def _error_payload(form, line_formset):
    return {
        "errors": form.errors.get_json_data(),
        "line_errors": [line_form.errors.get_json_data() for line_form in line_formset.forms],
        "line_non_form_errors": list(line_formset.non_form_errors()),
    }


@login_required
@permission_required("sales.view_salesinvoice", raise_exception=True)
@require_GET
def pos_medicine_search(request):
    form = PosMedicineSearchForm(request.GET)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    medicines = active_pos_medicine_queryset(form.cleaned_data.get("q") or "")[
        : form.cleaned_data.get("limit") or 20
    ]
    return JsonResponse({"results": [_medicine_payload(medicine) for medicine in medicines]})


@login_required
@permission_required("sales.view_salesinvoice", raise_exception=True)
@require_GET
def pos_barcode_lookup(request):
    form = PosBarcodeLookupForm(request.GET)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    barcode = find_active_pos_barcode(form.cleaned_data["barcode"])
    if barcode is None:
        return JsonResponse({"detail": "Barcode not found."}, status=404)
    medicine = get_pos_medicine(barcode.medicine_unit.medicine_id)
    payload = _medicine_payload(medicine)
    payload["barcode"] = barcode.barcode
    payload["matched_unit_id"] = str(barcode.medicine_unit_id)
    return JsonResponse(payload)


@login_required
@permission_required(
    ("sales.add_salesinvoice", "sales.add_salesinvoiceline"),
    raise_exception=True,
)
@require_POST
def pos_draft_create(request):
    form, line_formset, invoice = process_draft_sale(
        actor=request.user,
        data=request.POST,
    )
    if invoice is None:
        return JsonResponse(_error_payload(form, line_formset), status=400)
    return JsonResponse(_draft_payload(invoice), status=201)


@login_required
@permission_required(
    ("sales.view_salesinvoice", "sales.view_salesinvoiceline"),
    raise_exception=True,
)
@require_GET
def pos_draft_detail(request, pk):
    return JsonResponse(_draft_payload(get_draft_sale(pk)))


@login_required
@permission_required(
    ("sales.change_salesinvoice", "sales.change_salesinvoiceline"),
    raise_exception=True,
)
@require_POST
def pos_draft_update(request, pk):
    invoice = get_draft_sale(pk)
    form, line_formset, saved_invoice = process_draft_sale(
        actor=request.user,
        data=request.POST,
        instance=invoice,
    )
    if saved_invoice is None:
        return JsonResponse(_error_payload(form, line_formset), status=400)
    return JsonResponse(_draft_payload(saved_invoice))
