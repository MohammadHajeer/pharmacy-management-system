from django.urls import path

from . import views


app_name = "reports"

urlpatterns = [
    path("", views.reports_hub, name="hub"),
    path("sales/", views.sales_report, name="sales"),
    path("purchases/", views.purchases_report, name="purchases"),
    path("stock/", views.stock_report, name="stock"),
    path("expiry/", views.expiry_report, name="expiry"),
    path("receivables/", views.receivables_report, name="receivables"),
    path("payables/", views.payables_report, name="payables"),
    path("payments/", views.payments_report, name="payments"),
    path("returns/", views.returns_report, name="returns"),
]
