from django.urls import path

from . import views

app_name = "parties"

urlpatterns = [
    path("suppliers/", views.supplier_list, name="supplier-list"),
    path("suppliers/new/", views.supplier_create, name="supplier-create"),
    path("suppliers/<uuid:pk>/edit/", views.supplier_update, name="supplier-update"),
    path(
        "suppliers/<uuid:pk>/toggle-active/",
        views.supplier_toggle_active,
        name="supplier-toggle-active",
    ),
    path("customers/", views.customer_list, name="customer-list"),
    path("customers/new/", views.customer_create, name="customer-create"),
    path("customers/<uuid:pk>/edit/", views.customer_update, name="customer-update"),
    path(
        "customers/<uuid:pk>/toggle-active/",
        views.customer_toggle_active,
        name="customer-toggle-active",
    ),
    path("prescribers/", views.prescriber_list, name="prescriber-list"),
    path("prescribers/new/", views.prescriber_create, name="prescriber-create"),
    path("prescribers/<uuid:pk>/edit/", views.prescriber_update, name="prescriber-update"),
    path(
        "prescribers/<uuid:pk>/toggle-active/",
        views.prescriber_toggle_active,
        name="prescriber-toggle-active",
    ),
]
