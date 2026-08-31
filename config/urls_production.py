"""Production URL configuration.

It preserves the application's existing URL patterns while excluding the
development-only browser-reload endpoint and adding a lightweight health check.
"""

from django.http import JsonResponse
from django.urls import path

from .urls import urlpatterns as application_urlpatterns


def health_check(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("health/", health_check, name="health-check"),
    *[
        pattern
        for pattern in application_urlpatterns
        if str(pattern.pattern) != "__reload__/"
    ],
]
