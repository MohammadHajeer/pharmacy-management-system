from django.urls import path

from . import views

app_name = "dashboard_preview"

urlpatterns = [
    path("", views.dashboard_preview_view, name="home"),
]
