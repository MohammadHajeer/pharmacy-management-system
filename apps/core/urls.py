from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.settings_overview, name="settings"),
    path("tax-rates/new/", views.tax_rate_create, name="tax-rate-create"),
    path("tax-rates/<uuid:pk>/edit/", views.tax_rate_edit, name="tax-rate-edit"),
    path(
        "payment-methods/new/",
        views.payment_method_create,
        name="payment-method-create",
    ),
    path(
        "payment-methods/<uuid:pk>/edit/",
        views.payment_method_edit,
        name="payment-method-edit",
    ),
]
