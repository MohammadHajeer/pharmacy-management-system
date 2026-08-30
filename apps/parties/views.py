from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CustomerForm, PrescriberForm, SupplierForm
from .models import Customer, Prescriber, Supplier


def _search(queryset, query, fields):
    if not query:
        return queryset
    condition = Q()
    for field in fields:
        condition |= Q(**{f"{field}__icontains": query})
    return queryset.filter(condition)


def _status_filter(queryset, status):
    if status == "inactive":
        return queryset.filter(is_active=False)
    if status == "all":
        return queryset
    return queryset.filter(is_active=True)


# --- Suppliers ---------------------------------------------------------


@login_required
@permission_required("parties.view_supplier", raise_exception=True)
def supplier_list(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "active")
    suppliers = Supplier.objects.all().order_by("name")
    suppliers = _search(suppliers, query, ["code", "name", "phone", "email"])
    suppliers = _status_filter(suppliers, status)

    return render(
        request,
        "parties/suppliers/list.html",
        {"suppliers": suppliers, "query": query, "status": status},
    )


@login_required
@permission_required("parties.add_supplier", raise_exception=True)
def supplier_create(request):
    form = SupplierForm(data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Supplier added successfully.")
        return redirect("parties:supplier-list")

    return render(request, "parties/suppliers/form.html", {"form": form, "supplier": None})


@login_required
@permission_required("parties.change_supplier", raise_exception=True)
def supplier_update(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    form = SupplierForm(data=request.POST or None, instance=supplier)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Supplier updated successfully.")
        return redirect("parties:supplier-list")

    return render(request, "parties/suppliers/form.html", {"form": form, "supplier": supplier})


@login_required
@permission_required("parties.change_supplier", raise_exception=True)
@require_POST
def supplier_toggle_active(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    supplier.is_active = not supplier.is_active
    supplier.save(update_fields=["is_active", "updated_at"])
    messages.success(
        request,
        "Supplier deactivated." if not supplier.is_active else "Supplier reactivated.",
    )
    return redirect("parties:supplier-list")


# --- Customers -----------------------------------------------------------


@login_required
@permission_required("parties.view_customer", raise_exception=True)
def customer_list(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "active")
    customers = Customer.objects.all().order_by("name")
    customers = _search(customers, query, ["code", "name", "phone", "email"])
    customers = _status_filter(customers, status)

    return render(
        request,
        "parties/customers/list.html",
        {"customers": customers, "query": query, "status": status},
    )


@login_required
@permission_required("parties.add_customer", raise_exception=True)
def customer_create(request):
    form = CustomerForm(data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Customer added successfully.")
        return redirect("parties:customer-list")

    return render(request, "parties/customers/form.html", {"form": form, "customer": None})


@login_required
@permission_required("parties.change_customer", raise_exception=True)
def customer_update(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    form = CustomerForm(data=request.POST or None, instance=customer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Customer updated successfully.")
        return redirect("parties:customer-list")

    return render(request, "parties/customers/form.html", {"form": form, "customer": customer})


@login_required
@permission_required("parties.change_customer", raise_exception=True)
@require_POST
def customer_toggle_active(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    customer.is_active = not customer.is_active
    customer.save(update_fields=["is_active", "updated_at"])
    messages.success(
        request,
        "Customer deactivated." if not customer.is_active else "Customer reactivated.",
    )
    return redirect("parties:customer-list")


# --- Prescribers -----------------------------------------------------------


@login_required
@permission_required("parties.view_prescriber", raise_exception=True)
def prescriber_list(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "active")
    prescribers = Prescriber.objects.all().order_by("name")
    prescribers = _search(prescribers, query, ["name", "phone", "professional_identifier"])
    prescribers = _status_filter(prescribers, status)

    return render(
        request,
        "parties/prescribers/list.html",
        {"prescribers": prescribers, "query": query, "status": status},
    )


@login_required
@permission_required("parties.add_prescriber", raise_exception=True)
def prescriber_create(request):
    form = PrescriberForm(data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Prescriber added successfully.")
        return redirect("parties:prescriber-list")

    return render(request, "parties/prescribers/form.html", {"form": form, "prescriber": None})


@login_required
@permission_required("parties.change_prescriber", raise_exception=True)
def prescriber_update(request, pk):
    prescriber = get_object_or_404(Prescriber, pk=pk)
    form = PrescriberForm(data=request.POST or None, instance=prescriber)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Prescriber updated successfully.")
        return redirect("parties:prescriber-list")

    return render(
        request, "parties/prescribers/form.html", {"form": form, "prescriber": prescriber}
    )


@login_required
@permission_required("parties.change_prescriber", raise_exception=True)
@require_POST
def prescriber_toggle_active(request, pk):
    prescriber = get_object_or_404(Prescriber, pk=pk)
    prescriber.is_active = not prescriber.is_active
    prescriber.save(update_fields=["is_active", "updated_at"])
    messages.success(
        request,
        "Prescriber deactivated." if not prescriber.is_active else "Prescriber reactivated.",
    )
    return redirect("parties:prescriber-list")
