"""Permission-aware presentation for the read-only reports query layer."""

from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.core.models import PaymentMethod, PharmacySettings
from apps.core.pagination import pagination_context
from apps.parties.models import Customer, Supplier
from apps.purchasing.models import PurchaseInvoice
from apps.sales.models import SalesInvoice

from . import queries


def _options(choices, all_label):
    return [{"value": "", "label": all_label}] + [
        {"value": value, "label": label} for value, label in choices
    ]


def _party_options(model, all_label, *, walk_in=False):
    options = [{"value": "", "label": all_label}]
    if walk_in:
        options.append({"value": "walk-in", "label": "Walk-in"})
    options.extend(
        {"value": str(item.pk), "label": f"{item.code} — {item.name}"}
        for item in model.objects.order_by("name", "code", "id")
    )
    return options


def _currency_code():
    settings_row = PharmacySettings.objects.filter(singleton_key=1).first()
    return settings_row.currency_code if settings_row else ""


def _field(result, name, label, *, field_type="select", options=None, placeholder=""):
    return {
        "name": name,
        "label": label,
        "type": field_type,
        "value": result.filters.get(name, ""),
        "options": options or [],
        "placeholder": placeholder,
        "error": result.errors.get(name, ""),
    }


def _date_fields(result):
    return [
        _field(result, "date_from", "Date from", field_type="date"),
        _field(result, "date_to", "Date to", field_type="date"),
    ]


def _render_report(
    request,
    result,
    *,
    title,
    kicker,
    description,
    table_template,
    empty_title,
    empty_text,
    row_label,
    filter_fields,
    summary_items,
    extra_context=None,
):
    page = pagination_context(request, result.rows, context_name="report_rows")
    return render(
        request,
        "reports/report.html",
        {
            **page,
            "breadcrumbs": [
                {"label": "Reports", "url": reverse("reports:hub")},
                {"label": title},
            ],
            "title": title,
            "kicker": kicker,
            "description": description,
            "table_template": table_template,
            "empty_title": empty_title,
            "empty_text": empty_text,
            "row_label": row_label,
            "filter_fields": filter_fields,
            "has_filters": any(result.filters.values()),
            "filter_errors": result.errors,
            "summary_items": summary_items,
            "currency_code": _currency_code(),
            "clear_url": request.path,
            **(extra_context or {}),
        },
    )


@login_required
@never_cache
@require_GET
def reports_hub(request):
    reports = []
    definitions = (
        ("Sales", "Sales Report", "Completed invoice value and payment state.", "sales.view_salesinvoice", "reports:sales"),
        ("Purchasing", "Purchase Report", "Posted supplier invoices and effective balances.", "purchasing.view_purchaseinvoice", "reports:purchases"),
        ("Inventory", "Stock Report", "Batch-level physical stock and operational state.", "inventory.view_medicinebatch", "reports:stock"),
        ("Inventory", "Expiry Report", "Remaining batches grouped by real expiry windows.", "inventory.view_medicinebatch", "reports:expiry"),
        ("Finance", "Customer Receivables", "Saved-customer balances after active payments.", "finance.view_financial_reports", "reports:receivables"),
        ("Finance", "Supplier Payables", "Posted purchase balances after active payments.", "finance.view_financial_reports", "reports:payables"),
        ("Finance", "Payment Activity", "Customer and supplier payments, including reversals.", "finance.view_financial_reports", "reports:payments"),
        ("Returns", "Returns Report", "Customer returns, refunds, and supplier returns.", None, "reports:returns"),
    )
    for section, title, description, permission, url_name in definitions:
        if url_name == "reports:returns":
            allowed = request.user.has_perm("returns.view_customerreturn") or request.user.has_perm("returns.view_supplierreturn")
        else:
            allowed = request.user.has_perm(permission)
        if allowed:
            reports.append(
                {
                    "section": section,
                    "title": title,
                    "description": description,
                    "url": reverse(url_name),
                }
            )
    if not reports:
        raise PermissionDenied
    sections = []
    for section_name in ("Sales", "Purchasing", "Inventory", "Finance", "Returns"):
        items = [item for item in reports if item["section"] == section_name]
        if items:
            sections.append({"name": section_name, "reports": items})
    return render(
        request,
        "reports/hub.html",
        {"breadcrumbs": [{"label": "Reports"}], "report_sections": sections},
    )


@login_required
@permission_required("sales.view_salesinvoice", raise_exception=True)
@never_cache
@require_GET
def sales_report(request):
    result = queries.completed_sales_report(request.GET)
    fields = [
        _field(result, "q", "Search", field_type="search", placeholder="Invoice number or customer…"),
        *_date_fields(result),
        _field(result, "customer", "Customer", options=_party_options(Customer, "All customers", walk_in=True)),
        _field(result, "payment_status", "Payment", options=_options(SalesInvoice.PaymentStatus.choices, "All payment states")),
    ]
    return _render_report(
        request,
        result,
        title="Sales Report",
        kicker="Completed sales ledger",
        description="Inspect completed sales only. Draft and void invoices are excluded.",
        table_template="reports/tables/sales.html",
        empty_title="No completed sales match these filters",
        empty_text="Adjust the date, customer, payment, or search filters.",
        row_label="completed sales",
        filter_fields=fields,
        summary_items=[
            {"label": "Completed sales", "value": result.summary["count"]},
            {"label": "Sales value", "value": result.summary["total"], "money": True},
        ],
    )


@login_required
@permission_required("purchasing.view_purchaseinvoice", raise_exception=True)
@never_cache
@require_GET
def purchases_report(request):
    result = queries.posted_purchases_report(request.GET)
    can_view_financials = request.user.has_perm("finance.view_financial_reports")
    fields = [
        _field(result, "q", "Search", field_type="search", placeholder="Invoice, reference, or supplier…"),
        *_date_fields(result),
        _field(result, "supplier", "Supplier", options=_party_options(Supplier, "All suppliers")),
        _field(result, "payment_status", "Payment", options=_options(PurchaseInvoice.PaymentStatus.choices, "All payment states")),
    ]
    return _render_report(
        request,
        result,
        title="Purchase Report",
        kicker="Posted purchasing ledger",
        description="Inspect posted purchase invoices only. Draft and void documents are excluded.",
        table_template="reports/tables/purchases.html",
        empty_title="No posted purchases match these filters",
        empty_text="Adjust the date, supplier, payment, or search filters.",
        row_label="posted purchases",
        filter_fields=fields,
        summary_items=[
            {"label": "Posted invoices", "value": result.summary["count"]},
            {"label": "Purchase value", "value": result.summary["total"], "money": True},
        ] + ([
            {"label": "Outstanding payable", "value": result.summary["outstanding"], "money": True},
        ] if can_view_financials else []),
        extra_context={"show_financial_columns": can_view_financials},
    )


@login_required
@permission_required("inventory.view_medicinebatch", raise_exception=True)
@never_cache
@require_GET
def stock_report(request):
    result = queries.stock_report(request.GET)
    fields = [
        _field(result, "q", "Medicine or batch", field_type="search", placeholder="Medicine, generic name, or batch…"),
        _field(result, "state", "Stock state", options=_options((
            ("healthy", "Healthy"), ("low", "Low stock"), ("out", "Out of stock"),
            ("expired", "Expired"), ("inactive", "Inactive"),
        ), "All stock states")),
    ]
    return _render_report(
        request,
        result,
        title="Stock Report",
        kicker="Physical batch inventory",
        description="MedicineBatch is the physical stock source of truth; this workspace is read-only.",
        table_template="reports/tables/stock.html",
        empty_title="No medicine batches match these filters",
        empty_text="Adjust the medicine, batch, or stock-state filter.",
        row_label="batch layers",
        filter_fields=fields,
        summary_items=[
            {"label": "Batch layers", "value": result.summary["count"]},
            {"label": "Available base quantity", "value": result.summary["quantity"], "quantity": True},
            {"label": "Low-stock layers", "value": result.summary["low"]},
            {"label": "Empty layers", "value": result.summary["out"]},
        ],
    )


@login_required
@permission_required("inventory.view_medicinebatch", raise_exception=True)
@never_cache
@require_GET
def expiry_report(request):
    result = queries.expiry_report(request.GET)
    fields = [
        _field(result, "q", "Medicine or batch", field_type="search", placeholder="Medicine, generic name, or batch…"),
        _field(result, "bucket", "Expiry window", options=_options((
            ("expired", "Expired"), ("within_30", "Within 30 days"),
            ("days_31_90", "31–90 days"), ("later", "Later than 90 days"),
        ), "All expiry windows")),
    ]
    return _render_report(
        request,
        result,
        title="Expiry Report",
        kicker="Expiry exposure ledger",
        description="Remaining physical batches ordered by nearest expiry using today's date.",
        table_template="reports/tables/expiry.html",
        empty_title="No stocked batches match these filters",
        empty_text="There are no remaining batch quantities in the selected expiry window.",
        row_label="stocked batches",
        filter_fields=fields,
        summary_items=[
            {"label": "Stocked batches", "value": result.summary["count"]},
            {"label": "Available base quantity", "value": result.summary["quantity"], "quantity": True},
            {"label": "Expired layers", "value": result.summary["expired"]},
            {"label": "Within 30 days", "value": result.summary["near"]},
        ],
    )


def _balance_fields(result, party_name, party_options):
    return [
        _field(result, "q", "Search", field_type="search", placeholder=f"Invoice or {party_name.lower()}…"),
        *_date_fields(result),
        _field(result, party_name.lower(), party_name, options=party_options),
        _field(result, "balance", "Balance", options=_options((("outstanding", "Outstanding only"), ("all", "All invoices")), "Outstanding only")),
    ]


@login_required
@permission_required("finance.view_financial_reports", raise_exception=True)
@never_cache
@require_GET
def receivables_report(request):
    result = queries.customer_receivables_report(request.GET)
    return _render_report(
        request,
        result,
        title="Customer Receivables",
        kicker="Effective customer balances",
        description="Completed saved-customer invoices less active posted customer payments.",
        table_template="reports/tables/receivables.html",
        empty_title="No outstanding customer receivables" if result.filters["balance"] == "outstanding" else "No customer invoices match these filters",
        empty_text="Reversed payments are excluded from effective paid values.",
        row_label="customer invoices",
        filter_fields=_balance_fields(result, "Customer", _party_options(Customer, "All customers")),
        summary_items=[
            {"label": "Invoices", "value": result.summary["count"]},
            {"label": "Invoice value", "value": result.summary["total"], "money": True},
            {"label": "Outstanding receivable", "value": result.summary["outstanding"], "money": True},
        ],
    )


@login_required
@permission_required("finance.view_financial_reports", raise_exception=True)
@never_cache
@require_GET
def payables_report(request):
    result = queries.supplier_payables_report(request.GET)
    return _render_report(
        request,
        result,
        title="Supplier Payables",
        kicker="Effective supplier balances",
        description="Posted purchase invoices less active posted supplier payments.",
        table_template="reports/tables/payables.html",
        empty_title="No outstanding supplier payables" if result.filters["balance"] == "outstanding" else "No purchase invoices match these filters",
        empty_text="Reversed payments are excluded from effective paid values.",
        row_label="supplier invoices",
        filter_fields=_balance_fields(result, "Supplier", _party_options(Supplier, "All suppliers")),
        summary_items=[
            {"label": "Invoices", "value": result.summary["count"]},
            {"label": "Invoice value", "value": result.summary["total"], "money": True},
            {"label": "Outstanding payable", "value": result.summary["outstanding"], "money": True},
        ],
    )


@login_required
@permission_required("finance.view_financial_reports", raise_exception=True)
@never_cache
@require_GET
def payments_report(request):
    result = queries.payment_activity_report(request.GET)
    methods = _options(
        ((str(item.pk), item.name) for item in PaymentMethod.objects.order_by("name", "id")),
        "All methods",
    )
    fields = [
        _field(result, "q", "Search", field_type="search", placeholder="Invoice, party, or reference…"),
        *_date_fields(result),
        _field(result, "type", "Payment type", options=_options((("customer", "Customer payments"), ("supplier", "Supplier payments")), "All payment types")),
        _field(result, "method", "Method", options=methods),
        _field(result, "status", "Status", options=_options((('POSTED', 'Posted'), ('REVERSED', 'Reversed')), "All statuses")),
    ]
    return _render_report(
        request,
        result,
        title="Payment Activity",
        kicker="Payment transaction history",
        description="Actual customer and supplier payments with reversals clearly retained in history.",
        table_template="reports/tables/payments.html",
        empty_title="No payment activity matches these filters",
        empty_text="Adjust the payment type, method, status, date, or search filters.",
        row_label="payments",
        filter_fields=fields,
        summary_items=[
            {"label": "Payment records", "value": result.summary["count"]},
            {"label": "Active customer received", "value": result.summary["customer_active"], "money": True},
            {"label": "Active supplier paid", "value": result.summary["supplier_active"], "money": True},
            {"label": "Reversed records", "value": result.summary["reversed"]},
        ],
    )


@login_required
@never_cache
@require_GET
def returns_report(request):
    include_customer = request.user.has_perm("returns.view_customerreturn")
    include_supplier = request.user.has_perm("returns.view_supplierreturn")
    if not (include_customer or include_supplier):
        raise PermissionDenied
    result = queries.returns_report(
        request.GET,
        include_customer=include_customer,
        include_supplier=include_supplier,
    )
    type_choices = []
    if include_customer:
        type_choices.extend((("customer_return", "Customer returns"), ("customer_refund", "Customer refunds")))
    if include_supplier:
        type_choices.append(("supplier_return", "Supplier returns"))
    fields = [
        _field(result, "q", "Search", field_type="search", placeholder="Return, invoice, or party…"),
        *_date_fields(result),
        _field(result, "type", "Record type", options=_options(type_choices, "All available types")),
        _field(result, "status", "Status", options=_options((("DRAFT", "Draft"), ("POSTED", "Posted"), ("VOID", "Void"), ("REFUNDED", "Refund posted")), "All statuses")),
    ]
    return _render_report(
        request,
        result,
        title="Returns Report",
        kicker="Authoritative returns history",
        description="Customer returns, posted refunds, and supplier returns available to your account.",
        table_template="reports/tables/returns.html",
        empty_title="No return records match these filters",
        empty_text="No customer returns, refunds, or supplier returns are recorded for this selection.",
        row_label="return records",
        filter_fields=fields,
        summary_items=[
            {"label": "Records", "value": result.summary["count"]},
            {"label": "Customer returns", "value": result.summary["customer_returns"]},
            {"label": "Customer refunds", "value": result.summary["refunds"]},
            {"label": "Supplier returns", "value": result.summary["supplier_returns"]},
        ],
    )
