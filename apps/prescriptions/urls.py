from django.urls import path

from . import views

app_name = "prescriptions"

urlpatterns = [
    path("", views.prescription_list, name="list"),
    path("new/", views.prescription_create, name="create"),
    path("<uuid:pk>/", views.prescription_detail, name="detail"),
]
