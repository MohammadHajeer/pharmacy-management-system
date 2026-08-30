from django.urls import path

from . import views

app_name = "purchasing"

urlpatterns = [
    path("invoices/", views.purchase_invoice_list, name="purchase-invoice-list"),
    path("invoices/new/", views.purchase_invoice_create, name="purchase-invoice-create"),
    path(
        "invoices/<uuid:pk>/",
        views.purchase_invoice_detail,
        name="purchase-invoice-detail",
    ),
    path(
        "invoices/<uuid:pk>/post/",
        views.purchase_invoice_post,
        name="purchase-invoice-post",
    ),
]
