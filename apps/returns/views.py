from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.pagination import pagination_context
from apps.inventory.services import InsufficientStockError, InvalidStockOperationError
from apps.sales.models import SaleBatchAllocation, SalesInvoiceLine

from .forms import (
    CustomerRefundForm,
    CustomerReturnHeaderForm,
    CustomerReturnLineFormSet,
    SupplierReturnHeaderForm,
    SupplierReturnLineFormSet,
)
from .models import CustomerReturn, ReturnStatus, SupplierReturn
from .services import (
    create_customer_return,
    create_draft_supplier_return,
    post_customer_return,
    post_supplier_return,
    process_customer_refund,
)


def _validation_error_message(error):
    if hasattr(error, "message_dict"):
        return "; ".join(
            f"{field}: {', '.join(field_messages)}"
            for field, field_messages in error.message_dict.items()
        )
    return "; ".join(error.messages) if hasattr(error, "messages") else str(error)


def _navigation_context(request, *, section, label=None):
    breadcrumbs = [{"label": "Returns & Refunds"}]
    if label:
        list_permission = f"returns.view_{section}return"
        root = {"label": "Customer returns" if section == "customer" else "Supplier returns"}
        if request.user.has_perm(list_permission):
            root["url"] = reverse(f"returns:{section}-return-list")
        breadcrumbs.extend((root, {"label": label}))
    return {"breadcrumbs": breadcrumbs, "returns_section": section}


@login_required
def returns_home(request):
    if request.user.has_perm("returns.view_customerreturn"):
        return redirect("returns:customer-return-list")
    if request.user.has_perm("returns.view_supplierreturn"):
        return redirect("returns:supplier-return-list")
    raise PermissionDenied


@login_required
@permission_required("returns.view_customerreturn", raise_exception=True)
def customer_return_list(request):
    returns = CustomerReturn.objects.select_related(
        "sales_invoice", "customer", "processed_by"
    ).annotate(refunded_total=Sum("refunds__amount")).order_by("-created_at", "-id")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if query:
        returns = returns.filter(
            Q(return_number__icontains=query)
            | Q(sales_invoice__invoice_number__icontains=query)
            | Q(customer__name__icontains=query)
            | Q(customer__code__icontains=query)
        )
    invalid_filter = bool(status and status not in ReturnStatus.values)
    if invalid_filter:
        returns = returns.none()
    elif status:
        returns = returns.filter(status=status)
    page = pagination_context(request, returns, context_name="customer_returns")
    return render(request, "returns/customer/list.html", {
        **_navigation_context(request, section="customer"),
        **page,
        "query": query,
        "status": status,
        "invalid_filter": invalid_filter,
        "status_options": [{"value": "", "label": "All statuses"}] + [
            {"value": value, "label": label} for value, label in ReturnStatus.choices
        ],
    })


def _customer_form_context(request, header_form, line_formset):
    allocations = SaleBatchAllocation.objects.select_related(
        "sales_invoice_line__sales_invoice", "sales_invoice_line__medicine", "batch"
    ).filter(sales_invoice_line__sales_invoice__status="COMPLETED").order_by(
        "sales_invoice_line__sales_invoice__invoice_number",
        "sales_invoice_line__medicine_description_snapshot",
        "batch__batch_number",
    )
    sales_lines = {}
    batches = {}
    for allocation in allocations:
        line = allocation.sales_invoice_line
        sales_lines[line.pk] = {
            "value": str(line.pk),
            "label": (
                f"{line.sales_invoice.invoice_number} — "
                f"{line.medicine_description_snapshot} ({allocation.allocated_quantity_base} base)"
            ),
        }
        batch = allocation.batch
        batches[batch.pk] = {
            "value": str(batch.pk),
            "label": f"{line.medicine_description_snapshot} — {batch.batch_number} · exp {batch.expiry_date:%d %b %Y}",
        }
    return {
        **_navigation_context(request, section="customer", label="New"),
        "header_form": header_form,
        "line_formset": line_formset,
        "invoice_options": [
            {
                "value": str(invoice.pk),
                "label": f"{invoice.invoice_number} — {invoice.customer_name_snapshot or 'Walk-in'}",
            }
            for invoice in header_form.fields["sales_invoice"].queryset.select_related("customer").order_by(
                "-completed_at", "-id"
            )
        ],
        "sales_line_options": list(sales_lines.values()),
        "batch_options": list(batches.values()),
    }


@login_required
@permission_required(
    ("returns.add_customerreturn", "returns.add_customerreturnline"),
    raise_exception=True,
)
def customer_return_create(request):
    header_form = CustomerReturnHeaderForm(data=request.POST or None)
    line_formset = CustomerReturnLineFormSet(data=request.POST or None, prefix="lines")
    if request.method == "POST" and header_form.is_valid() and line_formset.is_valid():
        lines_data = [
            form.cleaned_data
            for form in line_formset
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]
        try:
            customer_return = create_customer_return(
                actor=request.user,
                sales_invoice=header_form.cleaned_data["sales_invoice"],
                reason=header_form.cleaned_data["reason"],
                lines_data=lines_data,
            )
        except ValidationError as error:
            header_form.add_error(None, _validation_error_message(error))
        else:
            messages.success(request, "Customer return draft created for review.")
            return redirect("returns:customer-return-detail", pk=customer_return.pk)
    return render(
        request,
        "returns/customer/form.html",
        _customer_form_context(request, header_form, line_formset),
    )


def _customer_detail_context(request, customer_return, *, refund_form=None):
    refund_form = refund_form or CustomerRefundForm()
    already_refunded = customer_return.refunds.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return {
        **_navigation_context(request, section="customer", label=customer_return.return_number),
        "customer_return": customer_return,
        "lines": customer_return.lines.select_related("sales_invoice_line", "batch", "batch__medicine"),
        "refunds": customer_return.refunds.select_related("payment_method", "processed_by").order_by("-refunded_at", "-id"),
        "already_refunded": already_refunded,
        "refundable_remaining": customer_return.return_total - already_refunded,
        "refund_form": refund_form,
        "refund_method_options": [
            {"value": str(method.pk), "label": method.name}
            for method in refund_form.fields["payment_method"].queryset
        ],
    }


@login_required
@permission_required(
    ("returns.view_customerreturn", "returns.view_customerreturnline"),
    raise_exception=True,
)
def customer_return_detail(request, pk):
    customer_return = get_object_or_404(
        CustomerReturn.objects.select_related("sales_invoice", "customer", "processed_by"),
        pk=pk,
    )
    return render(request, "returns/customer/detail.html", _customer_detail_context(request, customer_return))


@login_required
@permission_required("returns.post_customerreturn", raise_exception=True)
@require_POST
def customer_return_post(request, pk):
    customer_return = get_object_or_404(CustomerReturn, pk=pk)
    try:
        posted = post_customer_return(actor=request.user, customer_return=customer_return)
    except ValidationError as error:
        messages.error(request, _validation_error_message(error))
    except (InsufficientStockError, InvalidStockOperationError) as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Customer return {posted.return_number} posted.")
    return redirect("returns:customer-return-detail", pk=pk)


@login_required
@permission_required("returns.process_refund", raise_exception=True)
@require_POST
def customer_refund_create(request, pk):
    customer_return = get_object_or_404(
        CustomerReturn.objects.select_related("sales_invoice", "customer", "processed_by"), pk=pk
    )
    form, refund = process_customer_refund(
        actor=request.user, customer_return=customer_return, data=request.POST
    )
    if refund is not None:
        messages.success(request, f"Refund {refund.refund_number} posted.")
        return redirect("returns:customer-return-detail", pk=pk)
    customer_return.refresh_from_db()
    return render(
        request,
        "returns/customer/detail.html",
        _customer_detail_context(request, customer_return, refund_form=form),
        status=400,
    )


@login_required
@permission_required("returns.view_supplierreturn", raise_exception=True)
def supplier_return_list(request):
    returns = SupplierReturn.objects.select_related(
        "supplier", "purchase_invoice", "processed_by"
    ).order_by("-created_at", "-id")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if query:
        returns = returns.filter(
            Q(return_number__icontains=query)
            | Q(supplier__name__icontains=query)
            | Q(supplier__code__icontains=query)
            | Q(purchase_invoice__invoice_number__icontains=query)
        )
    invalid_filter = bool(status and status not in ReturnStatus.values)
    if invalid_filter:
        returns = returns.none()
    elif status:
        returns = returns.filter(status=status)
    page = pagination_context(request, returns, context_name="supplier_returns")
    return render(request, "returns/supplier/list.html", {
        **_navigation_context(request, section="supplier"),
        **page,
        "query": query,
        "status": status,
        "invalid_filter": invalid_filter,
        "status_options": [{"value": "", "label": "All statuses"}] + [
            {"value": value, "label": label} for value, label in ReturnStatus.choices
        ],
    })


def _supplier_form_context(request, header_form, line_formset):
    batches = line_formset.forms[0].fields["batch"].queryset if line_formset.forms else []
    medicines = {}
    batch_options = []
    for batch in batches:
        medicines[batch.medicine_id] = {"value": str(batch.medicine_id), "label": batch.medicine.name}
        batch_options.append({
            "value": str(batch.pk),
            "label": f"{batch.medicine.name} — {batch.batch_number} · {batch.quantity_available_base} available",
        })
    return {
        **_navigation_context(request, section="supplier", label="New"),
        "header_form": header_form,
        "line_formset": line_formset,
        "supplier_options": [
            {"value": str(item.pk), "label": f"{item.code} — {item.name}"}
            for item in header_form.fields["supplier"].queryset.order_by("name", "id")
        ],
        "purchase_options": [
            {"value": str(item.pk), "label": f"{item.invoice_number or 'Draft invoice'} — {item.supplier.name}"}
            for item in header_form.fields["purchase_invoice"].queryset.order_by("-created_at", "-id")
        ],
        "medicine_options": sorted(medicines.values(), key=lambda item: item["label"].lower()),
        "batch_options": batch_options,
    }


@login_required
@permission_required(
    ("returns.add_supplierreturn", "returns.add_supplierreturnline"),
    raise_exception=True,
)
def supplier_return_create(request):
    header_form = SupplierReturnHeaderForm(data=request.POST or None)
    line_formset = SupplierReturnLineFormSet(data=request.POST or None, prefix="lines")
    if request.method == "POST" and header_form.is_valid() and line_formset.is_valid():
        lines_data = [
            form.cleaned_data
            for form in line_formset
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]
        try:
            supplier_return = create_draft_supplier_return(
                actor=request.user,
                supplier=header_form.cleaned_data["supplier"],
                purchase_invoice=header_form.cleaned_data.get("purchase_invoice"),
                reason=header_form.cleaned_data["reason"],
                lines_data=lines_data,
            )
        except ValidationError as error:
            header_form.add_error(None, _validation_error_message(error))
        else:
            messages.success(request, "Supplier return draft created for review.")
            return redirect("returns:supplier-return-detail", pk=supplier_return.pk)
    return render(
        request,
        "returns/supplier/form.html",
        _supplier_form_context(request, header_form, line_formset),
    )


@login_required
@permission_required(
    ("returns.view_supplierreturn", "returns.view_supplierreturnline"),
    raise_exception=True,
)
def supplier_return_detail(request, pk):
    supplier_return = get_object_or_404(
        SupplierReturn.objects.select_related("supplier", "purchase_invoice", "processed_by"), pk=pk
    )
    return render(request, "returns/supplier/detail.html", {
        **_navigation_context(request, section="supplier", label=supplier_return.return_number),
        "supplier_return": supplier_return,
        "lines": supplier_return.lines.select_related("medicine", "batch"),
    })


@login_required
@permission_required("returns.post_supplierreturn", raise_exception=True)
@require_POST
def supplier_return_post(request, pk):
    get_object_or_404(SupplierReturn, pk=pk)
    try:
        posted = post_supplier_return(actor=request.user, supplier_return_id=pk)
    except ValidationError as error:
        messages.error(request, _validation_error_message(error))
    except (InsufficientStockError, InvalidStockOperationError) as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Supplier return {posted.return_number} posted.")
    return redirect("returns:supplier-return-detail", pk=pk)
