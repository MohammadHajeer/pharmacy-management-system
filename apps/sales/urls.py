from django.urls import path

from . import views


app_name = "sales"

urlpatterns = [
    path("pos/medicines/", views.pos_medicine_search, name="pos-medicine-search"),
    path("pos/barcodes/", views.pos_barcode_lookup, name="pos-barcode-lookup"),
    path("pos/drafts/", views.pos_draft_create, name="pos-draft-create"),
    path("pos/drafts/<uuid:pk>/", views.pos_draft_detail, name="pos-draft-detail"),
    path(
        "pos/drafts/<uuid:pk>/update/",
        views.pos_draft_update,
        name="pos-draft-update",
    ),
]
