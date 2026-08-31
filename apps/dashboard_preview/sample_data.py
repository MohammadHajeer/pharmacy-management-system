"""Illustrative records retained only for the isolated visual comparison page."""

SAMPLE_KPIS = (
    {
        "label": "Today's Sales",
        "value": "$2,450.00",
        "context": "18 completed transactions",
        "tone": "neutral",
        "permission": "sales.view_salesinvoice",
    },
    {
        "label": "Receivables",
        "value": "$1,280.00",
        "context": "Outstanding customer balances",
        "tone": "neutral",
        "permission": "finance.view_customerpayment",
    },
    {
        "label": "Low Stock",
        "value": "12",
        "context": "Medicines below reorder level",
        "tone": "warning",
        "permission": "inventory.view_medicinebatch",
    },
    {
        "label": "Expiring Soon",
        "value": "7",
        "context": "Batches within the next 30 days",
        "tone": "warning",
        "permission": "inventory.view_medicinebatch",
    },
)

SAMPLE_RECENT_ACTIVITY = (
    {
        "reference": "SL-1048",
        "activity": "Sale completed",
        "party": "Walk-in customer",
        "when": "10:42 AM",
        "amount": "$124.50",
        "status": "Completed",
        "status_variant": "success",
        "icon": "sales",
        "permission": "sales.view_salesinvoice",
    },
    {
        "reference": "PI-0312",
        "activity": "Purchase received",
        "party": "MediSupply Co.",
        "when": "9:18 AM",
        "amount": "$780.00",
        "status": "Posted",
        "status_variant": "secondary",
        "icon": "purchases",
        "permission": "purchasing.view_purchaseinvoice",
    },
    {
        "reference": "CP-0206",
        "activity": "Customer payment",
        "party": "Nour Haddad",
        "when": "Yesterday",
        "amount": "$200.00",
        "status": "Received",
        "status_variant": "success",
        "icon": "payments",
        "permission": "finance.view_customerpayment",
    },
    {
        "reference": "SP-0094",
        "activity": "Supplier payment",
        "party": "MediSupply Co.",
        "when": "Yesterday",
        "amount": "$450.00",
        "status": "Paid",
        "status_variant": "success",
        "icon": "payments",
        "permission": "finance.view_supplierpayment",
    },
)

SAMPLE_ATTENTION_ITEMS = (
    {
        "title": "Amoxicillin 500 mg",
        "detail": "8 boxes remaining",
        "status": "Low stock",
        "status_variant": "warning",
        "group": "Stock",
        "permission": "inventory.view_medicinebatch",
    },
    {
        "title": "Batch B-1842",
        "detail": "Expires in 12 days",
        "status": "Expiry urgent",
        "status_variant": "warning",
        "group": "Expiry",
        "permission": "inventory.view_medicinebatch",
    },
    {
        "title": "Batch IN-048",
        "detail": "Expired 2 days ago",
        "status": "Expired",
        "status_variant": "destructive",
        "group": "Expiry",
        "permission": "inventory.view_medicinebatch",
    },
    {
        "title": "Invoice SL-1021",
        "detail": "$320.00 balance outstanding",
        "status": "Partially paid",
        "status_variant": "warning",
        "group": "Finance",
        "permission": "sales.view_salesinvoice",
    },
    {
        "title": "Invoice PI-0298",
        "detail": "$540.00 due to supplier",
        "status": "Unpaid",
        "status_variant": "destructive",
        "group": "Finance",
        "permission": "purchasing.view_purchaseinvoice",
    },
)


def _visible_items(user, items):
    return [item for item in items if user.has_perm(item["permission"])]


