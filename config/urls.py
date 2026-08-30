"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    return redirect("accounts:login")


urlpatterns = [
    path("", home, name="home"),
    path("admin/", admin.site.urls),
    path("__reload__/", include("django_browser_reload.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("settings/", include("apps.core.urls")),
    path("catalog/", include("apps.catalog.urls")),
    path("parties/", include("apps.parties.urls")),
    path("purchasing/", include("apps.purchasing.urls")),
    path("prescriptions/", include("apps.prescriptions.urls")),
    path("sales/", include("apps.sales.urls")),
    path("dashboard-preview/", include("apps.dashboard_preview.urls")),
]
