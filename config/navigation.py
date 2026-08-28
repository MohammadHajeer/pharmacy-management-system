"""Project-level dashboard navigation.

Feature apps can add their URL name and optional Django permission here when
they are introduced. Missing URL names are handled as disabled links.
"""

DASHBOARD_NAVIGATION = (
    {
        "label": "Dashboard",
        "icon": "dashboard",
        "url_name": "dashboard:home",
        "namespace": "dashboard",
        "permission": None,
        "groups": None,  # everyone
    },
    {
        "label": "Medicines",
        "icon": "medicines",
        "url_name": None,
        "namespace": "medicines",
        "permission": None,
        "groups": ("Owner / Admin", "Pharmacist", "Inventory Manager"),
    },
    {
        "label": "Inventory",
        "icon": "inventory",
        "url_name": None,
        "namespace": "inventory",
        "permission": None,
        "groups": ("Owner / Admin", "Pharmacist", "Inventory Manager"),
    },
    {
        "label": "Suppliers",
        "icon": "suppliers",
        "url_name": None,
        "namespace": "suppliers",
        "permission": None,
        "groups": ("Owner / Admin", "Inventory Manager"),
    },
    {
        "label": "Purchases",
        "icon": "purchases",
        "url_name": None,
        "namespace": "purchases",
        "permission": None,
        "groups": ("Owner / Admin", "Inventory Manager"),
    },
    {
        "label": "Customers",
        "icon": "customers",
        "url_name": None,
        "namespace": "customers",
        "permission": None,
        "groups": ("Owner / Admin", "Pharmacist"),
    },
    {
        "label": "Sales",
        "icon": "sales",
        "url_name": None,
        "namespace": "sales",
        "permission": None,
        "groups": ("Owner / Admin", "Pharmacist"),
    },
    {
        "label": "Prescriptions",
        "icon": "prescriptions",
        "url_name": None,
        "namespace": "prescriptions",
        "permission": None,
        "groups": ("Owner / Admin", "Pharmacist"),
    },
    {
        "label": "Payments",
        "icon": "payments",
        "url_name": None,
        "namespace": "payments",
        "permission": None,
        "groups": ("Owner / Admin", "Accountant"),
    },
    {
        "label": "Reports",
        "icon": "reports",
        "url_name": None,
        "namespace": "reports",
        "permission": None,
        "groups": ("Owner / Admin", "Accountant"),
    },
)
