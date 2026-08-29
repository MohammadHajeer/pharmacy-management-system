"""Project-level dashboard navigation.

Feature apps add their URL name and Django permission here when introduced.
Missing URL names are handled as disabled links.

Groups organize permissions; navigation checks permissions only.
"""


DASHBOARD_NAVIGATION = (
    {
        "section": "Main",
        "label": "Dashboard",
        "icon": "dashboard",
        "url_name": "dashboard:home",
        "namespace": "dashboard",
        "permission": None,
    },
    {
        "section": "Main",
        "label": "Sales",
        "icon": "sales",
        "url_name": None,
        "namespace": "sales",
        "permission": "sales.view_salesinvoice",
    },
    {
        "section": "Management",
        "label": "Medicines",
        "icon": "medicines",
        "url_name": "catalog:medicine-list",
        "namespace": "catalog",
        "permission": "catalog.view_medicine",
    },
    {
        "section": "Management",
        "label": "Inventory",
        "icon": "inventory",
        "url_name": None,
        "namespace": "inventory",
        "permission": "inventory.view_medicinebatch",
    },
    {
        "section": "Management",
        "label": "Suppliers",
        "icon": "suppliers",
        "url_name": None,
        "namespace": "parties",
        "permission": "parties.view_supplier",
    },
    {
        "section": "Management",
        "label": "Customers",
        "icon": "customers",
        "url_name": None,
        "namespace": "parties",
        "permission": "parties.view_customer",
    },
    {
        "section": "Management",
        "label": "Prescriptions",
        "icon": "prescriptions",
        "url_name": None,
        "namespace": "prescriptions",
        "permission": "prescriptions.view_prescription",
    },
    {
        "section": "Transactions",
        "label": "Purchases",
        "icon": "purchases",
        "url_name": None,
        "namespace": "purchasing",
        "permission": "purchasing.view_purchaseinvoice",
    },
    {
        "section": "Transactions",
        "label": "Invoices",
        "icon": "invoices",
        "url_name": None,
        "namespace": "sales",
        "permission": "sales.view_salesinvoice",
    },
    {
        "section": "Transactions",
        "label": "Payments",
        "icon": "payments",
        "url_name": None,
        "namespace": "finance",
        "permission": "finance.view_customerpayment",
    },
    {
        "section": "Transactions",
        "label": "Returns & Refunds",
        "icon": "returns",
        "url_name": None,
        "namespace": "returns",
        "permission": "returns.view_customerreturn",
    },
    {
        "section": "Reports",
        "label": "Reports",
        "icon": "reports",
        "url_name": None,
        "namespace": "reports",
        "permission": "finance.view_financial_reports",
    },
    {
        "section": "System",
        "label": "Settings",
        "icon": "settings",
        "url_name": None,
        "namespace": "core",
        "permission": "core.change_pharmacysettings",
    },
    {
        "section": "System",
        "label": "Logout",
        "icon": "logout",
        "url_name": "accounts:logout",
        "namespace": None,
        "permission": None,
        "method": "post",
    },
)
