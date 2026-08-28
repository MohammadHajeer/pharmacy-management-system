from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("medicines/", views.medicine_list, name="medicine-list"),
]