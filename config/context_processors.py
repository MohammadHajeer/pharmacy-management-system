from collections import Counter

from django.urls import NoReverseMatch, reverse

from .navigation import DASHBOARD_NAVIGATION


def dashboard_navigation(request):
    """Return visible, URL-safe dashboard navigation for every template."""
    resolver_match = request.resolver_match
    current_namespace = resolver_match.namespace if resolver_match else None
    current_url_name = resolver_match.url_name if resolver_match else None
    current_view_name = resolver_match.view_name if resolver_match else None
    namespace_counts = Counter(item["namespace"] for item in DASHBOARD_NAVIGATION)

    items = []

    for configured_item in DASHBOARD_NAVIGATION:
        permission = configured_item["permission"]

        if permission and not request.user.has_perm(permission):
            continue

        item = configured_item.copy()
        item["url"] = None

        if item["url_name"]:
            try:
                item["url"] = reverse(item["url_name"])
            except NoReverseMatch:
                pass

        if "active_url_names" in item:
            matches = (
                item["namespace"] == current_namespace
                and current_url_name in item["active_url_names"]
            )
        else:
            matches = item["url_name"] == current_view_name or (
                bool(item["namespace"])
                and namespace_counts[item["namespace"]] == 1
                and item["namespace"] == current_namespace
            )
        item["is_active"] = bool(item["url"] and matches)

        items.append(item)

    return {"dashboard_navigation": items}
