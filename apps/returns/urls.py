from django.urls import path

from . import views

app_name = "returns"

urlpatterns = [
    path("", views.returns_home, name="home"),
    path("customers/", views.customer_return_list, name="customer-return-list"),
    path("customers/new/", views.customer_return_create, name="customer-return-create"),
    path("customers/<uuid:pk>/", views.customer_return_detail, name="customer-return-detail"),
    path("customers/<uuid:pk>/post/", views.customer_return_post, name="customer-return-post"),
    path("customers/<uuid:pk>/refunds/", views.customer_refund_create, name="customer-refund-create"),
    path("suppliers/", views.supplier_return_list, name="supplier-return-list"),
    path("suppliers/new/", views.supplier_return_create, name="supplier-return-create"),
    path("suppliers/<uuid:pk>/", views.supplier_return_detail, name="supplier-return-detail"),
    path("suppliers/<uuid:pk>/post/", views.supplier_return_post, name="supplier-return-post"),
]
