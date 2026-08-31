from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from .queries import dashboard_context


@never_cache
@login_required
def dashboard_view(request):
    return render(request, "dashboard/index.html", {
        "page_context": "Dashboard",
        "breadcrumbs": [{"label": "Dashboard"}],
        **dashboard_context(request.user),
    })
