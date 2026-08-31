from django.urls import path

from . import views


app_name = "sales"

urlpatterns = [
    path("pos/", views.pos_workspace, name="pos"),
    path("pos/<uuid:pk>/", views.pos_workspace, name="pos-workspace"),
    path("invoices/", views.invoice_list, name="invoice-list"),
    path("invoices/<uuid:pk>/", views.invoice_detail, name="invoice-detail"),
    path("invoices/<uuid:pk>/print/", views.invoice_print, name="invoice-print"),
    path("pos/medicines/", views.pos_medicine_search, name="pos-medicine-search"),
    path("pos/barcodes/", views.pos_barcode_lookup, name="pos-barcode-lookup"),
    path("pos/drafts/", views.pos_draft_create, name="pos-draft-create"),
    path("pos/drafts/<uuid:pk>/", views.pos_draft_detail, name="pos-draft-detail"),
    path(
        "pos/drafts/<uuid:pk>/update/",
        views.pos_draft_update,
        name="pos-draft-update",
    ),
    path(
        "pos/drafts/<uuid:pk>/complete/",
        views.pos_sale_complete,
        name="pos-sale-complete",
    ),
]
