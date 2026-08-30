from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import (
    CategoryForm,
    ManufacturerForm,
    MedicineBarcodeForm,
    MedicineForm,
    MedicineUnitForm,
)
from .models import Category, Manufacturer, Medicine, MedicineBarcode, MedicineUnit


def _status_filter(queryset, status):
    if status == "inactive":
        return queryset.filter(is_active=False)
    if status == "all":
        return queryset
    return queryset.filter(is_active=True)


# --- Medicines -------------------------------------------------------------


@login_required
@permission_required("catalog.view_medicine", raise_exception=True)
def medicine_list(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "active")

    medicines = Medicine.objects.select_related("category", "manufacturer").order_by("name")
    if query:
        medicines = medicines.filter(
            Q(name__icontains=query)
            | Q(generic_name__icontains=query)
            | Q(barcodes__barcode__iexact=query)
        ).distinct()
        medicines = _status_filter(medicines, status)

    return render(
        request,
        "catalog/medicines/list.html",
        {
            "medicines": medicines,
            "query": query,
            "status": status,
            "breadcrumbs": [{"label": "Catalog"}, {"label": "Medicines"}],
        },
    )


@login_required
@permission_required("catalog.view_medicine", raise_exception=True)
def medicine_detail(request, pk):
    medicine = get_object_or_404(
        Medicine.objects.select_related("category", "manufacturer"), pk=pk
    )
    units = medicine.units.all().order_by("-is_base_unit", "name")
    barcodes = MedicineBarcode.objects.filter(medicine_unit__medicine=medicine).select_related(
        "medicine_unit"
    )

    return render(
        request,
        "catalog/medicines/detail.html",
        {"medicine": medicine, "units": units, "barcodes": barcodes},
    )


def _medicine_select_options():
    category_options = [
        {"value": str(category.pk), "label": category.name}
        for category in Category.objects.filter(is_active=True).order_by("name")
    ]
    manufacturer_options = [
        {"value": str(manufacturer.pk), "label": manufacturer.name}
        for manufacturer in Manufacturer.objects.filter(is_active=True).order_by("name")
    ]
    return category_options, manufacturer_options


@login_required
@permission_required("catalog.add_medicine", raise_exception=True)
def medicine_create(request):
    form = MedicineForm(data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        medicine = form.save()
        messages.success(request, "Medicine added successfully.")
        return redirect("catalog:medicine-detail", pk=medicine.pk)

    category_options, manufacturer_options = _medicine_select_options()
    return render(
        request,
        "catalog/medicines/form.html",
        {
            "form": form,
            "medicine": None,
            "category_options": category_options,
            "manufacturer_options": manufacturer_options,
        },
    )


@login_required
@permission_required("catalog.change_medicine", raise_exception=True)
def medicine_update(request, pk):
    medicine = get_object_or_404(Medicine, pk=pk)
    form = MedicineForm(data=request.POST or None, instance=medicine)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Medicine updated successfully.")
        return redirect("catalog:medicine-detail", pk=medicine.pk)

    category_options, manufacturer_options = _medicine_select_options()
    return render(
        request,
        "catalog/medicines/form.html",
        {
            "form": form,
            "medicine": medicine,
            "category_options": category_options,
            "manufacturer_options": manufacturer_options,
        },
    )


@login_required
@permission_required("catalog.change_medicine", raise_exception=True)
@require_POST
def medicine_toggle_active(request, pk):
    medicine = get_object_or_404(Medicine, pk=pk)
    medicine.is_active = not medicine.is_active
    medicine.save(update_fields=["is_active", "updated_at"])
    messages.success(
        request,
        "Medicine deactivated." if not medicine.is_active else "Medicine reactivated.",
    )
    return redirect("catalog:medicine-detail", pk=medicine.pk)


# --- Medicine units ----------------------------------------------------------


@login_required
@permission_required("catalog.add_medicineunit", raise_exception=True)
def medicine_unit_create(request, medicine_pk):
    medicine = get_object_or_404(Medicine, pk=medicine_pk)
    form = MedicineUnitForm(data=request.POST or None, medicine=medicine)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Unit added successfully.")
        return redirect("catalog:medicine-detail", pk=medicine.pk)

    return render(
        request,
        "catalog/medicines/unit_form.html",
        {"form": form, "medicine": medicine, "unit": None},
    )


@login_required
@permission_required("catalog.change_medicineunit", raise_exception=True)
def medicine_unit_update(request, medicine_pk, pk):
    medicine = get_object_or_404(Medicine, pk=medicine_pk)
    unit = get_object_or_404(MedicineUnit, pk=pk, medicine=medicine)
    form = MedicineUnitForm(data=request.POST or None, instance=unit, medicine=medicine)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Unit updated successfully.")
        return redirect("catalog:medicine-detail", pk=medicine.pk)

    return render(
        request,
        "catalog/medicines/unit_form.html",
        {"form": form, "medicine": medicine, "unit": unit},
    )


@login_required
@permission_required("catalog.change_medicineunit", raise_exception=True)
@require_POST
def medicine_unit_toggle_active(request, medicine_pk, pk):
    medicine = get_object_or_404(Medicine, pk=medicine_pk)
    unit = get_object_or_404(MedicineUnit, pk=pk, medicine=medicine)
    unit.is_active = not unit.is_active
    unit.save(update_fields=["is_active", "updated_at"])
    messages.success(
        request,
        "Unit deactivated." if not unit.is_active else "Unit reactivated.",
    )
    return redirect("catalog:medicine-detail", pk=medicine.pk)


# --- Medicine barcodes -------------------------------------------------------


@login_required
@permission_required("catalog.add_medicinebarcode", raise_exception=True)
def medicine_barcode_create(request, medicine_pk):
    medicine = get_object_or_404(Medicine, pk=medicine_pk)
    form = MedicineBarcodeForm(data=request.POST or None, medicine=medicine)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Barcode added successfully.")
        return redirect("catalog:medicine-detail", pk=medicine.pk)

    unit_options = [
        {"value": str(unit.pk), "label": unit.name}
        for unit in MedicineUnit.objects.filter(medicine=medicine, is_active=True).order_by("name")
    ]
    return render(
        request,
        "catalog/medicines/barcode_form.html",
        {"form": form, "medicine": medicine, "unit_options": unit_options},
    )


@login_required
@permission_required("catalog.change_medicinebarcode", raise_exception=True)
@require_POST
def medicine_barcode_toggle_active(request, medicine_pk, pk):
    medicine = get_object_or_404(Medicine, pk=medicine_pk)
    barcode = get_object_or_404(MedicineBarcode, pk=pk, medicine_unit__medicine=medicine)
    barcode.is_active = not barcode.is_active
    barcode.save(update_fields=["is_active", "updated_at"])
    messages.success(
        request,
        "Barcode deactivated." if not barcode.is_active else "Barcode reactivated.",
    )
    return redirect("catalog:medicine-detail", pk=medicine.pk)


# --- Categories --------------------------------------------------------------


@login_required
@permission_required("catalog.view_category", raise_exception=True)
def category_list(request):
    status = request.GET.get("status", "active")
    categories = _status_filter(Category.objects.all().order_by("name"), status)
    return render(request, "catalog/categories/list.html", {"categories": categories, "status": status})


@login_required
@permission_required("catalog.add_category", raise_exception=True)
def category_create(request):
    form = CategoryForm(data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Category added successfully.")
        return redirect("catalog:category-list")
    return render(request, "catalog/categories/form.html", {"form": form, "category": None})


@login_required
@permission_required("catalog.change_category", raise_exception=True)
def category_update(request, pk):
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(data=request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Category updated successfully.")
        return redirect("catalog:category-list")
    return render(request, "catalog/categories/form.html", {"form": form, "category": category})


@login_required
@permission_required("catalog.change_category", raise_exception=True)
@require_POST
def category_toggle_active(request, pk):
    category = get_object_or_404(Category, pk=pk)
    category.is_active = not category.is_active
    category.save(update_fields=["is_active", "updated_at"])
    messages.success(
        request,
        "Category deactivated." if not category.is_active else "Category reactivated.",
    )
    return redirect("catalog:category-list")


# --- Manufacturers -------------------------------------------------------------


@login_required
@permission_required("catalog.view_manufacturer", raise_exception=True)
def manufacturer_list(request):
    status = request.GET.get("status", "active")
    manufacturers = _status_filter(Manufacturer.objects.all().order_by("name"), status)
    return render(
        request,
        "catalog/manufacturers/list.html",
        {"manufacturers": manufacturers, "status": status},
    )


@login_required
@permission_required("catalog.add_manufacturer", raise_exception=True)
def manufacturer_create(request):
    form = ManufacturerForm(data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Manufacturer added successfully.")
        return redirect("catalog:manufacturer-list")
    return render(
        request, "catalog/manufacturers/form.html", {"form": form, "manufacturer": None}
    )


@login_required
@permission_required("catalog.change_manufacturer", raise_exception=True)
def manufacturer_update(request, pk):
    manufacturer = get_object_or_404(Manufacturer, pk=pk)
    form = ManufacturerForm(data=request.POST or None, instance=manufacturer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Manufacturer updated successfully.")
        return redirect("catalog:manufacturer-list")
    return render(
        request, "catalog/manufacturers/form.html", {"form": form, "manufacturer": manufacturer}
    )


@login_required
@permission_required("catalog.change_manufacturer", raise_exception=True)
@require_POST
def manufacturer_toggle_active(request, pk):
    manufacturer = get_object_or_404(Manufacturer, pk=pk)
    manufacturer.is_active = not manufacturer.is_active
    manufacturer.save(update_fields=["is_active", "updated_at"])
    messages.success(
        request,
        "Manufacturer deactivated." if not manufacturer.is_active else "Manufacturer reactivated.",
    )
    return redirect("catalog:manufacturer-list")