from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from apps.dashboard import views as dashboard_views


@never_cache
@login_required
def dashboard_preview_view(request):
    """Render the isolated visual preview with the canonical dashboard mock data."""
    return render(
        request,
        "dashboard_preview/index.html",
        {
            "page_context": "Dashboard preview",
            "dashboard_data_notice": (
                "Illustrative values for the Phase 1 layout; live dashboard "
                "queries are not connected yet."
            ),
            "kpis": dashboard_views._visible_items(
                request.user,
                dashboard_views.SAMPLE_KPIS,
            ),
            "recent_activity": dashboard_views._visible_items(
                request.user,
                dashboard_views.SAMPLE_RECENT_ACTIVITY,
            ),
            "attention_items": dashboard_views._visible_items(
                request.user,
                dashboard_views.SAMPLE_ATTENTION_ITEMS,
            ),
        },
    )
