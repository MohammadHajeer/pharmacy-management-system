from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.shortcuts import render


@never_cache
@login_required
def dashboard_view(request):
    return render(
        request,
        "dashboard/index.html",
        {
            "page_context": "Dashboard",
        },
    )
