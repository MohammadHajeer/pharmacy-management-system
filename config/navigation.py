"""Project-level dashboard navigation.

Feature apps can add their URL name and optional Django permission here when
they are introduced. Missing URL names are handled as disabled links.
"""

DASHBOARD_NAVIGATION = (
    {
        "label": "Dashboard",
        "icon": "dashboard",
        "url_name": "home",
        "namespace": None,
        "permission": None,
    },
    {
        "label": "Medicines",
        "icon": "medicines",
        "url_name": None,
        "namespace": "medicines",
        "permission": None,
    },
    {
        "label": "Inventory",
        "icon": "inventory",
        "url_name": None,
        "namespace": "inventory",
        "permission": None,
    },
    {
        "label": "Suppliers",
        "icon": "suppliers",
        "url_name": None,
        "namespace": "suppliers",
        "permission": None,
    },
    {
        "label": "Purchases",
        "icon": "purchases",
        "url_name": None,
        "namespace": "purchases",
        "permission": None,
    },
    {
        "label": "Customers",
        "icon": "customers",
        "url_name": None,
        "namespace": "customers",
        "permission": None,
    },
    {
        "label": "Sales",
        "icon": "sales",
        "url_name": None,
        "namespace": "sales",
        "permission": None,
    },
    {
        "label": "Prescriptions",
        "icon": "prescriptions",
        "url_name": None,
        "namespace": "prescriptions",
        "permission": None,
    },
    {
        "label": "Payments",
        "icon": "payments",
        "url_name": None,
        "namespace": "payments",
        "permission": None,
    },
    {
        "label": "Reports",
        "icon": "reports",
        "url_name": None,
        "namespace": "reports",
        "permission": None,
    },
)
