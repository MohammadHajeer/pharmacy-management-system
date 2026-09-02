"""Read-only report queries built from the owning apps' authoritative records."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from django.db.models import (
    Case,
    CharField,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.core.models import PharmacySettings
from apps.finance.models import CustomerPayment, PaymentStatus, SupplierPayment
from apps.inventory.models import MedicineBatch
from apps.purchasing.models import PurchaseInvoice
from apps.returns.models import (
    CustomerRefund,
    CustomerReturn,
    ReturnStatus,
    SupplierReturn,
)
from apps.sales.models import SalesInvoice


MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)
QUANTITY_FIELD = DecimalField(max_digits=14, decimal_places=3)
ZERO_MONEY = Value(Decimal("0.00"), output_field=MONEY_FIELD)


@dataclass
class ReportResult:
    rows: object
    summary: dict
    filters: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)

    @property
    def invalid(self):
        return bool(self.errors)


def _text(params, name):
    return str(params.get(name, "")).strip()


def _date_filters(params):
    values = {"date_from": _text(params, "date_from"), "date_to": _text(params, "date_to")}
    parsed = {}
    errors = {}
    for name, value in values.items():
        if not value:
            parsed[name] = None
            continue
        try:
            parsed[name] = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            parsed[name] = None
            errors[name] = "Enter a valid date in YYYY-MM-DD format."
    if (
        not errors
        and parsed["date_from"]
        and parsed["date_to"]
        and parsed["date_from"] > parsed["date_to"]
    ):
        errors["date_to"] = "Date to must be on or after date from."
    return values, parsed, errors


def _uuid_filter(value, *, name, errors, allow=()):
    if not value or value in allow:
        return value
    try:
        return UUID(value)
    except (TypeError, ValueError):
        errors[name] = "Select a valid option."
        return None


def _active_payment_subquery(model, invoice_field):
    return (
        model.objects.filter(
            **{invoice_field: OuterRef("pk")},
            status=PaymentStatus.POSTED,
        )
        .values(invoice_field)
        .annotate(total=Sum("amount"))
        .values("total")
    )


def _with_effective_customer_balance(queryset):
    paid = _active_payment_subquery(CustomerPayment, "sales_invoice_id")
    return queryset.annotate(
        effective_paid=Coalesce(Subquery(paid, output_field=MONEY_FIELD), ZERO_MONEY)
    ).annotate(
        effective_balance=ExpressionWrapper(
            F("grand_total") - F("effective_paid"), output_field=MONEY_FIELD
        )
    ).annotate(
        effective_payment_status=Case(
            When(effective_balance__lte=0, then=Value(SalesInvoice.PaymentStatus.PAID)),
            When(effective_paid__gt=0, then=Value(SalesInvoice.PaymentStatus.PARTIAL)),
            default=Value(SalesInvoice.PaymentStatus.UNPAID),
            output_field=CharField(),
        )
    )


def _with_effective_supplier_balance(queryset):
    paid = _active_payment_subquery(SupplierPayment, "purchase_invoice_id")
    return queryset.annotate(
        effective_paid=Coalesce(Subquery(paid, output_field=MONEY_FIELD), ZERO_MONEY)
    ).annotate(
        effective_balance=ExpressionWrapper(
            F("grand_total") - F("effective_paid"), output_field=MONEY_FIELD
        )
    ).annotate(
        effective_payment_status=Case(
            When(effective_balance__lte=0, then=Value(PurchaseInvoice.PaymentStatus.PAID)),
            When(effective_paid__gt=0, then=Value(PurchaseInvoice.PaymentStatus.PARTIAL)),
            default=Value(PurchaseInvoice.PaymentStatus.UNPAID),
            output_field=CharField(),
        )
    )


def _money_summary(queryset, value_field, *, balance_field=None):
    aggregates = {
        "count": Count("pk"),
        "total": Coalesce(Sum(value_field), ZERO_MONEY),
    }
    if balance_field:
        aggregates["outstanding"] = Coalesce(
            Sum(balance_field, filter=Q(**{f"{balance_field}__gt": 0})), ZERO_MONEY
        )
    return queryset.aggregate(**aggregates)


def completed_sales_report(params):
    date_values, dates, errors = _date_filters(params)
    filters = {
        **date_values,
        "q": _text(params, "q"),
        "customer": _text(params, "customer"),
        "payment_status": _text(params, "payment_status"),
    }
    customer = _uuid_filter(
        filters["customer"], name="customer", errors=errors, allow=("walk-in",)
    )
    if filters["payment_status"] and filters["payment_status"] not in SalesInvoice.PaymentStatus.values:
        errors["payment_status"] = "Select a valid payment status."

    rows = _with_effective_customer_balance(
        SalesInvoice.objects.filter(status=SalesInvoice.Status.COMPLETED)
        .select_related("customer", "pharmacist")
    )
    if dates["date_from"]:
        rows = rows.filter(completed_at__date__gte=dates["date_from"])
    if dates["date_to"]:
        rows = rows.filter(completed_at__date__lte=dates["date_to"])
    if customer == "walk-in":
        rows = rows.filter(customer__isnull=True)
    elif customer:
        rows = rows.filter(customer_id=customer)
    if filters["payment_status"] in SalesInvoice.PaymentStatus.values:
        rows = rows.filter(effective_payment_status=filters["payment_status"])
    if filters["q"]:
        rows = rows.filter(
            Q(invoice_number__icontains=filters["q"])
            | Q(customer_name_snapshot__icontains=filters["q"])
            | Q(customer__name__icontains=filters["q"])
        )
    if errors:
        rows = rows.none()
    rows = rows.order_by("-completed_at", "-id")
    return ReportResult(rows, _money_summary(rows, "grand_total"), filters, errors)


def posted_purchases_report(params):
    date_values, dates, errors = _date_filters(params)
    filters = {
        **date_values,
        "q": _text(params, "q"),
        "supplier": _text(params, "supplier"),
        "payment_status": _text(params, "payment_status"),
    }
    supplier = _uuid_filter(filters["supplier"], name="supplier", errors=errors)
    if filters["payment_status"] and filters["payment_status"] not in PurchaseInvoice.PaymentStatus.values:
        errors["payment_status"] = "Select a valid payment status."

    rows = _with_effective_supplier_balance(
        PurchaseInvoice.objects.filter(status=PurchaseInvoice.Status.POSTED)
        .select_related("supplier", "posted_by")
    )
    if dates["date_from"]:
        rows = rows.filter(invoice_date__gte=dates["date_from"])
    if dates["date_to"]:
        rows = rows.filter(invoice_date__lte=dates["date_to"])
    if supplier:
        rows = rows.filter(supplier_id=supplier)
    if filters["payment_status"] in PurchaseInvoice.PaymentStatus.values:
        rows = rows.filter(effective_payment_status=filters["payment_status"])
    if filters["q"]:
        rows = rows.filter(
            Q(invoice_number__icontains=filters["q"])
            | Q(supplier_invoice_reference__icontains=filters["q"])
            | Q(supplier_name_snapshot__icontains=filters["q"])
            | Q(supplier__name__icontains=filters["q"])
        )
    if errors:
        rows = rows.none()
    rows = rows.order_by("-invoice_date", "-posted_at", "-id")
    return ReportResult(
        rows,
        _money_summary(rows, "grand_total", balance_field="effective_balance"),
        filters,
        errors,
    )


def _stock_queryset(today):
    settings_row = PharmacySettings.objects.filter(singleton_key=1).first()
    default_threshold = (
        settings_row.default_low_stock_threshold
        if settings_row
        else Decimal("0.000")
    )
    eligible = (
        MedicineBatch.objects.filter(
            medicine_id=OuterRef("medicine_id"),
            medicine__is_active=True,
            is_active=True,
            expiry_date__gte=today,
        )
        .order_by()
        .values("medicine_id")
        .annotate(total=Sum("quantity_available_base"))
        .values("total")
    )
    rows = MedicineBatch.objects.select_related("medicine").annotate(
        sellable_quantity=Coalesce(
            Subquery(eligible, output_field=QUANTITY_FIELD),
            Value(Decimal("0.000"), output_field=QUANTITY_FIELD),
        ),
        stock_threshold=Coalesce(
            "medicine__low_stock_threshold_base",
            Value(default_threshold, output_field=QUANTITY_FIELD),
        ),
    )
    return rows.annotate(
        stock_state=Case(
            When(quantity_available_base=0, then=Value("out")),
            When(expiry_date__lt=today, then=Value("expired")),
            When(Q(is_active=False) | Q(medicine__is_active=False), then=Value("inactive")),
            When(
                sellable_quantity__gt=0,
                sellable_quantity__lte=F("stock_threshold"),
                then=Value("low"),
            ),
            default=Value("healthy"),
            output_field=CharField(),
        )
    )


def stock_report(params, *, today=None):
    today = today or timezone.localdate()
    filters = {"q": _text(params, "q"), "state": _text(params, "state")}
    errors = {}
    states = {"healthy", "low", "out", "expired", "inactive"}
    if filters["state"] and filters["state"] not in states:
        errors["state"] = "Select a valid stock state."
    rows = _stock_queryset(today)
    if filters["q"]:
        rows = rows.filter(
            Q(medicine__name__icontains=filters["q"])
            | Q(medicine__generic_name__icontains=filters["q"])
            | Q(batch_number__icontains=filters["q"])
        )
    if filters["state"] in states:
        rows = rows.filter(stock_state=filters["state"])
    if errors:
        rows = rows.none()
    rows = rows.order_by("medicine__name", "expiry_date", "batch_number", "id")
    summary = rows.aggregate(
        count=Count("pk"),
        quantity=Coalesce(Sum("quantity_available_base"), Value(Decimal("0.000"), output_field=QUANTITY_FIELD)),
        low=Count("pk", filter=Q(stock_state="low")),
        out=Count("pk", filter=Q(stock_state="out")),
    )
    return ReportResult(rows, summary, filters, errors)


def expiry_report(params, *, today=None):
    today = today or timezone.localdate()
    filters = {"q": _text(params, "q"), "bucket": _text(params, "bucket")}
    errors = {}
    buckets = {"expired", "within_30", "days_31_90", "later"}
    if filters["bucket"] and filters["bucket"] not in buckets:
        errors["bucket"] = "Select a valid expiry bucket."
    day_30 = today + timedelta(days=30)
    day_90 = today + timedelta(days=90)
    rows = MedicineBatch.objects.filter(quantity_available_base__gt=0).select_related("medicine").annotate(
        expiry_bucket=Case(
            When(expiry_date__lt=today, then=Value("expired")),
            When(expiry_date__lte=day_30, then=Value("within_30")),
            When(expiry_date__lte=day_90, then=Value("days_31_90")),
            default=Value("later"),
            output_field=CharField(),
        )
    )
    if filters["q"]:
        rows = rows.filter(
            Q(medicine__name__icontains=filters["q"])
            | Q(medicine__generic_name__icontains=filters["q"])
            | Q(batch_number__icontains=filters["q"])
        )
    if filters["bucket"] in buckets:
        rows = rows.filter(expiry_bucket=filters["bucket"])
    if errors:
        rows = rows.none()
    rows = rows.order_by("expiry_date", "medicine__name", "batch_number", "id")
    summary = rows.aggregate(
        count=Count("pk"),
        quantity=Coalesce(Sum("quantity_available_base"), Value(Decimal("0.000"), output_field=QUANTITY_FIELD)),
        expired=Count("pk", filter=Q(expiry_bucket="expired")),
        near=Count("pk", filter=Q(expiry_bucket="within_30")),
    )
    return ReportResult(rows, summary, filters, errors)


def customer_receivables_report(params):
    date_values, dates, errors = _date_filters(params)
    balance = _text(params, "balance") or "outstanding"
    filters = {
        **date_values,
        "q": _text(params, "q"),
        "customer": _text(params, "customer"),
        "balance": balance,
    }
    customer = _uuid_filter(filters["customer"], name="customer", errors=errors)
    if balance not in {"outstanding", "all"}:
        errors["balance"] = "Select a valid balance state."
    rows = _with_effective_customer_balance(
        SalesInvoice.objects.filter(
            status=SalesInvoice.Status.COMPLETED,
            customer__isnull=False,
        ).select_related("customer")
    )
    if dates["date_from"]:
        rows = rows.filter(completed_at__date__gte=dates["date_from"])
    if dates["date_to"]:
        rows = rows.filter(completed_at__date__lte=dates["date_to"])
    if customer:
        rows = rows.filter(customer_id=customer)
    if filters["q"]:
        rows = rows.filter(
            Q(invoice_number__icontains=filters["q"])
            | Q(customer_name_snapshot__icontains=filters["q"])
            | Q(customer__name__icontains=filters["q"])
        )
    if balance == "outstanding":
        rows = rows.filter(effective_balance__gt=0)
    if errors:
        rows = rows.none()
    rows = rows.order_by("-completed_at", "-id")
    return ReportResult(
        rows,
        _money_summary(rows, "grand_total", balance_field="effective_balance"),
        filters,
        errors,
    )


def supplier_payables_report(params):
    date_values, dates, errors = _date_filters(params)
    balance = _text(params, "balance") or "outstanding"
    filters = {
        **date_values,
        "q": _text(params, "q"),
        "supplier": _text(params, "supplier"),
        "balance": balance,
    }
    supplier = _uuid_filter(filters["supplier"], name="supplier", errors=errors)
    if balance not in {"outstanding", "all"}:
        errors["balance"] = "Select a valid balance state."
    rows = _with_effective_supplier_balance(
        PurchaseInvoice.objects.filter(status=PurchaseInvoice.Status.POSTED).select_related("supplier")
    )
    if dates["date_from"]:
        rows = rows.filter(invoice_date__gte=dates["date_from"])
    if dates["date_to"]:
        rows = rows.filter(invoice_date__lte=dates["date_to"])
    if supplier:
        rows = rows.filter(supplier_id=supplier)
    if filters["q"]:
        rows = rows.filter(
            Q(invoice_number__icontains=filters["q"])
            | Q(supplier_invoice_reference__icontains=filters["q"])
            | Q(supplier_name_snapshot__icontains=filters["q"])
            | Q(supplier__name__icontains=filters["q"])
        )
    if balance == "outstanding":
        rows = rows.filter(effective_balance__gt=0)
    if errors:
        rows = rows.none()
    rows = rows.order_by("invoice_date", "invoice_number", "id")
    return ReportResult(
        rows,
        _money_summary(rows, "grand_total", balance_field="effective_balance"),
        filters,
        errors,
    )


def payment_activity_report(params):
    date_values, dates, errors = _date_filters(params)
    filters = {
        **date_values,
        "q": _text(params, "q"),
        "type": _text(params, "type"),
        "method": _text(params, "method"),
        "status": _text(params, "status"),
    }
    if filters["type"] and filters["type"] not in {"customer", "supplier"}:
        errors["type"] = "Select a valid payment type."
    if filters["status"] and filters["status"] not in PaymentStatus.values:
        errors["status"] = "Select a valid payment status."
    method = _uuid_filter(filters["method"], name="method", errors=errors)

    customer = CustomerPayment.objects.select_related(
        "customer", "sales_invoice", "payment_method", "processed_by", "reversed_by"
    )
    supplier = SupplierPayment.objects.select_related(
        "supplier", "purchase_invoice", "payment_method", "processed_by", "reversed_by"
    )
    if filters["type"] == "customer":
        supplier = supplier.none()
    elif filters["type"] == "supplier":
        customer = customer.none()
    for value, lookup in ((dates["date_from"], "paid_at__date__gte"), (dates["date_to"], "paid_at__date__lte")):
        if value:
            customer = customer.filter(**{lookup: value})
            supplier = supplier.filter(**{lookup: value})
    if method:
        customer = customer.filter(payment_method_id=method)
        supplier = supplier.filter(payment_method_id=method)
    if filters["status"] in PaymentStatus.values:
        customer = customer.filter(status=filters["status"])
        supplier = supplier.filter(status=filters["status"])
    if filters["q"]:
        q = filters["q"]
        customer = customer.filter(
            Q(reference__icontains=q)
            | Q(sales_invoice__invoice_number__icontains=q)
            | Q(customer__name__icontains=q)
        )
        supplier = supplier.filter(
            Q(reference__icontains=q)
            | Q(purchase_invoice__invoice_number__icontains=q)
            | Q(supplier__name__icontains=q)
        )
    if errors:
        customer = customer.none()
        supplier = supplier.none()
    customer_rows = [
        {
            "kind": "customer",
            "payment": payment,
            "invoice": payment.sales_invoice,
            "party": payment.customer,
            "event_at": payment.paid_at,
        }
        for payment in customer
    ]
    supplier_rows = [
        {
            "kind": "supplier",
            "payment": payment,
            "invoice": payment.purchase_invoice,
            "party": payment.supplier,
            "event_at": payment.paid_at,
        }
        for payment in supplier
    ]
    rows = sorted(
        customer_rows + supplier_rows,
        key=lambda row: (row["event_at"], str(row["payment"].pk)),
        reverse=True,
    )
    customer_active = sum(
        (
            row["payment"].amount
            for row in rows
            if row["kind"] == "customer" and row["payment"].status == PaymentStatus.POSTED
        ),
        Decimal("0.00"),
    )
    supplier_active = sum(
        (
            row["payment"].amount
            for row in rows
            if row["kind"] == "supplier" and row["payment"].status == PaymentStatus.POSTED
        ),
        Decimal("0.00"),
    )
    return ReportResult(
        rows,
        {
            "count": len(rows),
            "customer_active": customer_active,
            "supplier_active": supplier_active,
            "reversed": sum(row["payment"].status == PaymentStatus.REVERSED for row in rows),
        },
        filters,
        errors,
    )


def returns_report(params, *, include_customer=True, include_supplier=True):
    date_values, dates, errors = _date_filters(params)
    filters = {
        **date_values,
        "q": _text(params, "q"),
        "type": _text(params, "type"),
        "status": _text(params, "status"),
    }
    allowed_types = set()
    if include_customer:
        allowed_types.update(("customer_return", "customer_refund"))
    if include_supplier:
        allowed_types.add("supplier_return")
    if filters["type"] and filters["type"] not in allowed_types:
        errors["type"] = "Select a return type available to your account."
    allowed_statuses = set(ReturnStatus.values) | {"REFUNDED"}
    if filters["status"] and filters["status"] not in allowed_statuses:
        errors["status"] = "Select a valid status."

    customer_returns = CustomerReturn.objects.none()
    refunds = CustomerRefund.objects.none()
    supplier_returns = SupplierReturn.objects.none()
    if include_customer and filters["type"] in {"", "customer_return"}:
        customer_returns = CustomerReturn.objects.select_related("sales_invoice", "customer", "processed_by")
    if include_customer and filters["type"] in {"", "customer_refund"}:
        refunds = CustomerRefund.objects.select_related(
            "customer_return", "sales_invoice", "customer_return__customer", "payment_method", "processed_by"
        )
    if include_supplier and filters["type"] in {"", "supplier_return"}:
        supplier_returns = SupplierReturn.objects.select_related("supplier", "purchase_invoice", "processed_by")

    if filters["status"]:
        if filters["status"] == "REFUNDED":
            customer_returns = customer_returns.none()
            supplier_returns = supplier_returns.none()
        else:
            customer_returns = customer_returns.filter(status=filters["status"])
            supplier_returns = supplier_returns.filter(status=filters["status"])
            refunds = refunds.none()
    if filters["q"]:
        q = filters["q"]
        customer_returns = customer_returns.filter(
            Q(return_number__icontains=q)
            | Q(sales_invoice__invoice_number__icontains=q)
            | Q(customer__name__icontains=q)
        )
        refunds = refunds.filter(
            Q(refund_number__icontains=q)
            | Q(sales_invoice__invoice_number__icontains=q)
            | Q(customer_return__customer__name__icontains=q)
        )
        supplier_returns = supplier_returns.filter(
            Q(return_number__icontains=q)
            | Q(purchase_invoice__invoice_number__icontains=q)
            | Q(supplier__name__icontains=q)
        )
    if errors:
        customer_returns = customer_returns.none()
        refunds = refunds.none()
        supplier_returns = supplier_returns.none()

    rows = []
    for item in customer_returns:
        event_at = item.posted_at or item.created_at
        rows.append({"kind": "customer_return", "record": item, "event_at": event_at, "status": item.status, "amount": item.return_total})
    for item in refunds:
        rows.append({"kind": "customer_refund", "record": item, "event_at": item.refunded_at, "status": "REFUNDED", "amount": item.amount})
    for item in supplier_returns:
        event_at = item.posted_at or item.created_at
        rows.append({"kind": "supplier_return", "record": item, "event_at": event_at, "status": item.status, "amount": item.return_total})
    if dates["date_from"]:
        rows = [row for row in rows if timezone.localtime(row["event_at"]).date() >= dates["date_from"]]
    if dates["date_to"]:
        rows = [row for row in rows if timezone.localtime(row["event_at"]).date() <= dates["date_to"]]
    rows.sort(key=lambda row: (row["event_at"], str(row["record"].pk)), reverse=True)
    return ReportResult(
        rows,
        {
            "count": len(rows),
            "customer_returns": sum(row["kind"] == "customer_return" for row in rows),
            "refunds": sum(row["kind"] == "customer_refund" for row in rows),
            "supplier_returns": sum(row["kind"] == "supplier_return" for row in rows),
        },
        filters,
        errors,
    )
