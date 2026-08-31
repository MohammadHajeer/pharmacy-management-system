from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("medicines/", views.medicine_list, name="medicine-list"),
    path("medicines/new/", views.medicine_create, name="medicine-create"),
    path("medicines/<uuid:pk>/", views.medicine_detail, name="medicine-detail"),
    path("medicines/<uuid:pk>/edit/", views.medicine_update, name="medicine-update"),
    path(
        "medicines/<uuid:pk>/toggle-active/",
        views.medicine_toggle_active,
        name="medicine-toggle-active",
    ),
    path(
        "medicines/<uuid:medicine_pk>/units/new/",
        views.medicine_unit_create,
        name="medicine-unit-create",
    ),
    path(
        "medicines/<uuid:medicine_pk>/units/<uuid:pk>/edit/",
        views.medicine_unit_update,
        name="medicine-unit-update",
    ),
    path(
        "medicines/<uuid:medicine_pk>/units/<uuid:pk>/toggle-active/",
        views.medicine_unit_toggle_active,
        name="medicine-unit-toggle-active",
    ),
    path(
        "medicines/<uuid:medicine_pk>/barcodes/new/",
        views.medicine_barcode_create,
        name="medicine-barcode-create",
    ),
    path(
        "medicines/<uuid:medicine_pk>/barcodes/<uuid:pk>/toggle-active/",
        views.medicine_barcode_toggle_active,
        name="medicine-barcode-toggle-active",
    ),
    path("categories/", views.category_list, name="category-list"),
    path("categories/new/", views.category_create, name="category-create"),
    path("categories/<uuid:pk>/edit/", views.category_update, name="category-update"),
    path(
        "categories/<uuid:pk>/toggle-active/",
        views.category_toggle_active,
        name="category-toggle-active",
    ),
    path("manufacturers/", views.manufacturer_list, name="manufacturer-list"),
    path("manufacturers/new/", views.manufacturer_create, name="manufacturer-create"),
    path(
        "manufacturers/<uuid:pk>/edit/", views.manufacturer_update, name="manufacturer-update"
    ),
    path(
        "manufacturers/<uuid:pk>/toggle-active/",
        views.manufacturer_toggle_active,
        name="manufacturer-toggle-active",
    ),
]
