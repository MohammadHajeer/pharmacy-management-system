from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [path("", views.payment_home, name="payment-list")]

for kind in ("customer", "supplier"):
    urlpatterns += [
        path(f"{kind}/", views.PaymentList.as_view(kind=kind), name=f"{kind}-payment-list"),
        path(f"{kind}/new/", views.InvoiceChoose.as_view(kind=kind), name=f"{kind}-payment-create"),
        path(f"{kind}/invoices/<uuid:pk>/", views.InvoiceDetail.as_view(kind=kind), name=f"{kind}-invoice-detail"),
        path(f"{kind}/invoices/<uuid:pk>/record/", views.PaymentRecord.as_view(kind=kind), name=f"{kind}-payment-record"),
        path(f"{kind}/<uuid:pk>/", views.PaymentDetail.as_view(kind=kind), name=f"{kind}-payment-detail"),
        path(f"{kind}/<uuid:pk>/reverse/", views.PaymentReverse.as_view(kind=kind), name=f"{kind}-payment-reverse"),
    ]
