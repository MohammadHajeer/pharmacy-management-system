from django.urls import NoReverseMatch, reverse

from .navigation import DASHBOARD_NAVIGATION


def dashboard_navigation(request):
    """Return visible, URL-safe dashboard navigation for every template."""
    resolver_match = request.resolver_match
    current_namespace = resolver_match.namespace if resolver_match else None
    current_url_name = resolver_match.url_name if resolver_match else None
    items = []

    user_groups = (
        set(request.user.groups.values_list("name", flat=True))
        if request.user.is_authenticated
        else set()
    )

    for configured_item in DASHBOARD_NAVIGATION:
        permission = configured_item["permission"]
        if permission and not request.user.has_perm(permission):
            continue

        allowed_groups = configured_item.get("groups")

        if (
            allowed_groups
            and not request.user.is_superuser
            and not user_groups.intersection(allowed_groups)
        ):
            continue

        item = configured_item.copy()
        item["url"] = None

        if item["url_name"]:
            try:
                item["url"] = reverse(item["url_name"])
            except NoReverseMatch:
                # A feature can be configured before its URLconf is installed.
                pass

        item["is_active"] = bool(
            (item["namespace"] and item["namespace"] == current_namespace)
            or (
                not item["namespace"]
                and item["url_name"]
                and item["url_name"] == current_url_name
            )
        )
        items.append(item)

    return {"dashboard_navigation": items}
