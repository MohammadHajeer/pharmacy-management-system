from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.batch_list, name="batch-list"),
    path("movements/", views.movement_list, name="movement-list"),
    path("batches/<uuid:pk>/", views.batch_detail, name="batch-detail"),
]
