from datetime import timedelta
from decimal import ROUND_HALF_UP
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Prefetch, Q, prefetch_related_objects
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from apps.catalog.models import Medicine
from apps.catalog.unit_economics import selected_unit_selling_price
from apps.core.models import PharmacySettings
from apps.core.pagination import pagination_context
from apps.finance.forms import CustomerPaymentForm
from apps.inventory.services import InsufficientStockError

from .forms import DraftSaleForm, DraftSaleLineFormSet, PosBarcodeLookupForm, PosMedicineSearchForm
from .queries import (
    active_pos_medicine_queryset,
    find_active_pos_barcode,
    get_draft_sale,
    get_pos_medicine,
)
from .models import SaleBatchAllocation, SalesInvoice
from .services import MONEY_QUANTUM, complete_sale, process_draft_sale


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
        # Aggregate Decimal exponents vary by database (not quantity precision).
        "available_stock_base": format(medicine.available_stock_base, ".3f"),
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
        "invoice_number": invoice.invoice_number,
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
        "completed_at": invoice.completed_at.isoformat() if invoice.completed_at else None,
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
    page_size = form.cleaned_data.get("limit") or 20
    page = form.cleaned_data.get("page") or 1
    start = (page - 1) * page_size
    # One look-ahead row is cheaper than counting the complete lookup queryset.
    page_rows = list(
        active_pos_medicine_queryset(form.cleaned_data.get("q") or "")[
            start : start + page_size + 1
        ]
    )
    return JsonResponse(
        {
            "results": [
                _medicine_payload(medicine) for medicine in page_rows[:page_size]
            ],
            "page": page,
            "page_size": page_size,
            "has_previous": page > 1,
            "has_next": len(page_rows) > page_size,
        }
    )


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


@login_required
@permission_required("sales.complete_sale", raise_exception=True)
@require_POST
def pos_sale_complete(request, pk):
    get_object_or_404(SalesInvoice, pk=pk)
    payment_fields = ("payment_method", "amount", "reference", "paid_at")
    initial_payment_data = (
        {field: request.POST.get(field, "") for field in payment_fields}
        if any(field in request.POST for field in payment_fields)
        else None
    )

    try:
        result = complete_sale(
            actor=request.user,
            sales_invoice_id=pk,
            initial_payment_data=initial_payment_data,
        )
    except InsufficientStockError as error:
        return JsonResponse({"errors": {"__all__": [str(error)]}}, status=400)
    except ValidationError as error:
        errors = (
            error.message_dict
            if hasattr(error, "message_dict")
            else {"__all__": error.messages}
        )
        return JsonResponse({"errors": errors}, status=400)

    payload = _draft_payload(result.invoice)
    payload["initial_payment_id"] = (
        str(result.initial_payment.pk) if result.initial_payment else None
    )
    return JsonResponse(payload)


def _can_edit(user, *, existing=False):
    operation = "change" if existing else "add"
    return user.has_perms((f"sales.{operation}_salesinvoice", f"sales.{operation}_salesinvoiceline"))


def _pos_rows(formset, invoice):
    """Render only selected medicines, using the existing eligible-stock query."""
    medicine_ids = set()
    for form in formset:
        try:
            medicine_ids.add(UUID(str(form["medicine"].value())))
        except (ValueError, TypeError, AttributeError):
            pass
    medicines = {str(pk): medicine for pk, medicine in Medicine.objects.in_bulk(medicine_ids).items()}
    available = {medicine.pk: medicine for medicine in active_pos_medicine_queryset().filter(pk__in=medicine_ids)}
    saved_lines = list(invoice.lines.all()) if invoice and not formset.is_bound else []
    rows = []
    for index, form in enumerate(formset):
        medicine = medicines.get(str(form["medicine"].value()))
        stock = available.get(medicine.pk) if medicine else None
        units = stock.pos_sale_units if stock else []
        rows.append({
            "form": form,
            "medicine": medicine,
            "stock": stock,
            "base_unit": next((unit.name for unit in units if unit.is_base_unit), "base units"),
            "unit_options": [{"value": str(unit.pk), "label": unit.name} for unit in units],
            "saved_line": saved_lines[index] if index < len(saved_lines) else None,
        })
    return rows, [_medicine_payload(medicine) for medicine in available.values()]


@login_required
@permission_required("sales.view_salesinvoice", raise_exception=True)
@require_http_methods(["GET", "POST"])
def pos_workspace(request, pk=None):
    invoice = None
    if pk:
        if not request.user.has_perm("sales.view_salesinvoiceline"):
            raise PermissionDenied
        existing = get_object_or_404(SalesInvoice.objects.only("status"), pk=pk)
        if existing.status != SalesInvoice.Status.DRAFT:
            messages.info(request, "This sale is no longer a draft. Review its transaction record.")
            return redirect("sales:invoice-detail", pk=pk)
        invoice = get_draft_sale(pk)
    can_edit = _can_edit(request.user, existing=invoice is not None)
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied
        form, formset, saved = process_draft_sale(actor=request.user, data=request.POST, instance=invoice)
        if saved is not None:
            messages.success(request, "Draft saved. Review the server-calculated totals before completing the sale.")
            if request.user.has_perm("sales.view_salesinvoiceline"):
                return redirect("sales:pos-workspace", pk=saved.pk)
            return redirect("sales:invoice-list")
    else:
        form = DraftSaleForm(initial={"customer": invoice.customer_id, "prescription": invoice.prescription_id} if invoice else None)
        initial = [{
            "medicine": line.medicine_id,
            "medicine_unit": line.medicine_unit_id,
            "quantity": line.quantity,
            "discount_amount": line.discount_amount,
            "prescription_warning_acknowledged": line.prescription_warning_acknowledged,
        } for line in invoice.lines.all()] if invoice else []
        formset = DraftSaleLineFormSet(initial=initial, prefix="lines")
        if not invoice:
            # Empty presentation only; the service still requires at least one line.
            formset.min_num = 0
    rows, medicine_data = _pos_rows(formset, invoice)
    payment_form = CustomerPaymentForm()
    methods = list(payment_form.fields["payment_method"].queryset)
    settings_row = PharmacySettings.objects.filter(singleton_key=1).first()
    return render(request, "sales/pos.html", {
        "breadcrumbs": [{"label": "Sales"}, {"label": "Checkout"}],
        "invoice": invoice, "form": form, "formset": formset, "rows": rows,
        "medicine_data": medicine_data, "can_edit": can_edit,
        "can_create": _can_edit(request.user),
        "can_complete": bool(invoice and not formset.is_bound and request.user.has_perm("sales.complete_sale")),
        "currency_code": invoice.currency_code if invoice else (settings_row.currency_code if settings_row else ""),
        "customer_options": [{"value": str(customer.pk), "label": str(customer)} for customer in form.fields["customer"].queryset],
        "prescription_options": [{"value": str(prescription.pk), "label": f"{prescription} · {prescription.prescription_date}"} for prescription in form.fields["prescription"].queryset],
        "method_options": [{"value": str(method.pk), "label": method.name + (" — reference required" if method.requires_reference else "")} for method in methods],
        "reference_methods": [str(method.pk) for method in methods if method.requires_reference],
        "paid_at_value": timezone.localtime().strftime("%Y-%m-%dT%H:%M:%S"),
        "time_zone": timezone.get_current_timezone_name(),
        "requires_full_payment": bool(invoice and invoice.customer_id is None and invoice.grand_total > 0),
    }, status=400 if formset.is_bound else 200)


@login_required
@permission_required("sales.view_salesinvoice", raise_exception=True)
@require_GET
def invoice_list(request):
    invoices = SalesInvoice.objects.select_related("customer", "pharmacist").order_by(Coalesce("completed_at", "created_at").desc(), "-id")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    payment_status = request.GET.get("payment_status", "")
    period = request.GET.get("period", "")
    if query:
        invoices = invoices.filter(Q(invoice_number__icontains=query) | Q(customer_name_snapshot__icontains=query) | Q(customer__name__icontains=query))
    if status in SalesInvoice.Status.values:
        invoices = invoices.filter(status=status)
    if payment_status in SalesInvoice.PaymentStatus.values:
        invoices = invoices.filter(payment_status=payment_status)
    if period in {"1", "7", "30"}:
        invoices = invoices.filter(completed_at__date__gte=timezone.localdate() - timedelta(days=int(period) - 1), completed_at__date__lte=timezone.localdate())
    return render(request, "sales/invoice_list.html", {
        "breadcrumbs": [{"label": "Sales invoices"}],
        **pagination_context(request, invoices, context_name="invoices"),
        "query": query, "status": status, "payment_status": payment_status, "period": period,
        "has_filters": bool(payment_status or period),
        "can_create": _can_edit(request.user),
        "status_options": [{"value": "", "label": "All statuses"}] + [{"value": value, "label": label} for value, label in SalesInvoice.Status.choices],
        "payment_options": [{"value": "", "label": "All payments"}] + [{"value": value, "label": label} for value, label in SalesInvoice.PaymentStatus.choices],
        "period_options": [{"value": "", "label": "Any date"}, {"value": "1", "label": "Today"}, {"value": "7", "label": "Last 7 days"}, {"value": "30", "label": "Last 30 days"}],
    })


def _invoice_context(request, pk):
    invoice = get_object_or_404(SalesInvoice.objects.select_related("customer", "pharmacist", "prescription").prefetch_related("lines"), pk=pk)
    show_allocations = request.user.has_perm("sales.view_salebatchallocation")
    lines = list(invoice.lines.all())
    if show_allocations:
        prefetch_related_objects(lines, Prefetch("batch_allocations", queryset=SaleBatchAllocation.objects.select_related("batch").order_by("batch__expiry_date", "batch__first_received_at", "batch__id")))
    return {
        "invoice": invoice, "lines": lines,
        "breadcrumbs": [{"label": "Sales invoices", "url": reverse("sales:invoice-list")}, {"label": invoice.invoice_number or "Draft sale"}],
        "show_allocations": show_allocations,
        "can_edit": invoice.status == SalesInvoice.Status.DRAFT and _can_edit(request.user, existing=True),
        "can_create": _can_edit(request.user),
        "can_record_payment": invoice.status == SalesInvoice.Status.COMPLETED and invoice.customer_id is not None and invoice.balance_due > 0 and request.user.has_perm("finance.post_customerpayment"),
        "pharmacy": PharmacySettings.objects.filter(singleton_key=1).first(),
    }


@login_required
@permission_required(("sales.view_salesinvoice", "sales.view_salesinvoiceline"), raise_exception=True)
@require_GET
def invoice_detail(request, pk):
    return render(request, "sales/invoice_detail.html", _invoice_context(request, pk))


@login_required
@permission_required(("sales.view_salesinvoice", "sales.view_salesinvoiceline"), raise_exception=True)
@require_GET
def invoice_print(request, pk):
    context = _invoice_context(request, pk)
    if context["invoice"].status != SalesInvoice.Status.COMPLETED:
        return redirect("sales:invoice-detail", pk=pk)
    context["receipt"] = request.GET.get("format") == "receipt"
    return render(request, "sales/invoice_print.html", context)
