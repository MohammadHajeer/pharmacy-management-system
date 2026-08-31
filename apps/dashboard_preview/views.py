from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from . import sample_data


@never_cache
@login_required
def dashboard_preview_view(request):
    """Keep the isolated visual comparison independent of the live dashboard."""
    return render(
        request,
        "dashboard_preview/index.html",
        {
            "page_context": "Dashboard preview",
            "dashboard_data_notice": (
                "Illustrative values for visual comparison only. "
                "Open Dashboard for live operational data."
            ),
            "kpis": sample_data._visible_items(
                request.user,
                sample_data.SAMPLE_KPIS,
            ),
            "recent_activity": sample_data._visible_items(
                request.user,
                sample_data.SAMPLE_RECENT_ACTIVITY,
            ),
            "attention_items": sample_data._visible_items(
                request.user,
                sample_data.SAMPLE_ATTENTION_ITEMS,
            ),
        },
    )
