"""Server-rendered finance workflows; all writes stay in the finance services."""

from uuid import UUID

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_GET

from apps.core.models import PaymentMethod, PharmacySettings
from apps.core.pagination import pagination_context
from apps.purchasing.models import PurchaseInvoice
from apps.sales.models import SalesInvoice

from . import services
from .forms import CustomerPaymentForm, PaymentReversalForm, SupplierPaymentForm
from .models import CustomerPayment, PaymentStatus, SupplierPayment


@login_required
@require_GET
def payment_home(request):
    for kind in ("customer", "supplier"):
        if request.user.has_perm(f"finance.view_{kind}payment"):
            return redirect(f"finance:{kind}-payment-list")
    raise PermissionDenied


class PaymentWorkspace(LoginRequiredMixin, PermissionRequiredMixin, View):
    kind = "customer"
    operation = "view"

    def get_permission_required(self):
        return (f"finance.{self.operation}_{self.kind}payment",)

    @property
    def is_customer(self):
        return self.kind == "customer"

    @property
    def invoice_field(self):
        return "sales_invoice" if self.is_customer else "purchase_invoice"

    @property
    def balance_field(self):
        return "balance_due" if self.is_customer else "remaining_balance"

    @property
    def form_class(self):
        return CustomerPaymentForm if self.is_customer else SupplierPaymentForm

    def invoices(self):
        model = SalesInvoice if self.is_customer else PurchaseInvoice
        return model.objects.select_related(self.kind)

    def payments(self):
        model = CustomerPayment if self.is_customer else SupplierPayment
        return model.objects.select_related(
            self.kind, self.invoice_field, "payment_method", "processed_by", "reversed_by"
        ).order_by("-paid_at", "-id")

    def url(self, action, **kwargs):
        return reverse(f"finance:{self.kind}-{action}", kwargs=kwargs)

    def context(self, action=None):
        title = f"{self.kind.title()} Payments"
        can_view = self.request.user.has_perm(f"finance.view_{self.kind}payment")
        root = {"label": title}
        if action and can_view:
            root["url"] = self.url("payment-list")
        settings_row = PharmacySettings.objects.filter(singleton_key=1).first()
        return {
            "kind": self.kind,
            "title": title,
            "party_label": self.kind.title(),
            "invoice_label": "Sales invoice" if self.is_customer else "Purchase invoice",
            "description": (
                "Track payments received against customer sales invoices."
                if self.is_customer else
                "Track payments made against supplier purchase invoices."
            ),
            "breadcrumbs": [{"label": "Payments"}, root] + (
                [{"label": action}] if action else []
            ),
            "currency_code": settings_row.currency_code if settings_row else "",
            "list_url": self.url("payment-list") if can_view else "",
            "choose_url": self.url("payment-create"),
            "can_post": self.request.user.has_perm(f"finance.post_{self.kind}payment"),
        }

    def invoice_context(self, invoice):
        balance = getattr(invoice, self.balance_field)
        eligible_status = "COMPLETED" if self.is_customer else "POSTED"
        # Presentation only. Services recheck status and active payments under lock.
        eligible = invoice.status == eligible_status and balance > 0
        return {
            "invoice": invoice,
            "party": getattr(invoice, self.kind),
            "balance": balance,
            "eligible": eligible,
            "record_url": self.url("payment-record", pk=invoice.pk),
            "invoice_url": self.url("invoice-detail", pk=invoice.pk),
        }

    def payment_rows(self, payments):
        return [
            {
                "payment": payment,
                "invoice": getattr(payment, self.invoice_field),
                "party": getattr(payment, self.kind),
                "detail_url": self.url("payment-detail", pk=payment.pk),
                "invoice_url": self.url(
                    "invoice-detail", pk=getattr(payment, f"{self.invoice_field}_id")
                ),
            }
            for payment in payments
        ]


class PaymentList(PaymentWorkspace):
    def get(self, request):
        payments = self.payments()
        query = request.GET.get("q", "").strip()
        status = request.GET.get("status", "")
        method = request.GET.get("method", "")
        invalid_filter = False
        if query:
            payments = payments.filter(
                Q(reference__icontains=query)
                | Q(**{f"{self.invoice_field}__invoice_number__icontains": query})
                | Q(**{f"{self.kind}__name__icontains": query})
                | Q(**{f"{self.kind}__code__icontains": query})
            )
        if status:
            if status in PaymentStatus.values:
                payments = payments.filter(status=status)
            else:
                invalid_filter = True
        methods = list(PaymentMethod.objects.order_by("name", "id"))
        if method:
            try:
                method_id = UUID(method)
            except ValueError:
                invalid_filter = True
            else:
                if any(item.pk == method_id for item in methods):
                    payments = payments.filter(payment_method_id=method_id)
                else:
                    invalid_filter = True
        if invalid_filter:
            payments = payments.none()
        page = pagination_context(request, payments, context_name="payments")
        return render(request, "finance/payment_list.html", {
            **self.context(), **page,
            "rows": self.payment_rows(page["payments"]),
            "query": query, "status": status, "method": method,
            "has_filters": bool(query or status or method),
            "invalid_filter": invalid_filter,
            "status_options": [{"value": "", "label": "All statuses"}] + [
                {"value": value, "label": label} for value, label in PaymentStatus.choices
            ],
            "method_options": [{"value": "", "label": "All methods"}] + [
                {"value": str(item.pk), "label": item.name} for item in methods
            ],
        })


class InvoiceChoose(PaymentWorkspace):
    operation = "post"

    def get(self, request):
        invoices = self.invoices().filter(**{
            "status": "COMPLETED" if self.is_customer else "POSTED",
            f"{self.balance_field}__gt": 0,
        }).order_by("-created_at", "-id")
        query = request.GET.get("q", "").strip()
        if query:
            invoices = invoices.filter(
                Q(invoice_number__icontains=query)
                | Q(**{f"{self.kind}__name__icontains": query})
                | Q(**{f"{self.kind}__code__icontains": query})
            )
        page = pagination_context(request, invoices, context_name="invoices")
        return render(request, "finance/invoice_choose.html", {
            **self.context("Select invoice"), **page, "query": query,
            "invoice_rows": [self.invoice_context(invoice) for invoice in page["invoices"]],
        })


class InvoiceDetail(PaymentWorkspace):
    def get(self, request, pk):
        invoice = get_object_or_404(self.invoices(), pk=pk)
        payments = self.payments().filter(**{self.invoice_field: invoice})
        page = pagination_context(request, payments, context_name="payments")
        return render(request, "finance/invoice_detail.html", {
            **self.context(invoice.invoice_number or "Invoice"),
            **self.invoice_context(invoice), **page,
            "rows": self.payment_rows(page["payments"]),
        })


class PaymentRecord(PaymentWorkspace):
    operation = "post"

    def get(self, request, pk):
        invoice = get_object_or_404(self.invoices(), pk=pk)
        return self.render_form(invoice, self.form_class())

    def post(self, request, pk):
        invoice = get_object_or_404(self.invoices(), pk=pk)
        service = services.post_customer_payment if self.is_customer else services.post_supplier_payment
        form, payment = service(actor=request.user, data=request.POST, **{self.invoice_field: invoice})
        if payment is not None:
            messages.success(request, "Payment posted successfully.")
            if request.user.has_perm(f"finance.view_{self.kind}payment"):
                return redirect(self.url("payment-detail", pk=payment.pk))
            return redirect(self.url("payment-create"))
        # Show the latest stored balance after a stale form or concurrent payment.
        invoice.refresh_from_db()
        return self.render_form(invoice, form)

    def render_form(self, invoice, form):
        # Widget formatting only; do not change the backend's validation contract.
        form.fields["paid_at"].widget = forms.DateTimeInput(format="%Y-%m-%dT%H:%M:%S")
        paid_at_value = form["paid_at"].value()
        if not form.is_bound:
            paid_at_value = form.fields["paid_at"].widget.format_value(paid_at_value)
        return render(self.request, "finance/payment_form.html", {
            **self.context("Record payment"), **self.invoice_context(invoice),
            "form": form, "paid_at_value": paid_at_value,
            "time_zone": timezone.get_current_timezone_name(),
            "method_options": [
                {"value": str(method.pk), "label": method.name + (
                    " — reference required" if method.requires_reference else ""
                )}
                for method in form.fields["payment_method"].queryset
            ],
        })


class PaymentDetail(PaymentWorkspace):
    def get(self, request, pk):
        payment = get_object_or_404(self.payments(), pk=pk)
        return self.render_detail(payment, PaymentReversalForm())

    def render_detail(self, payment, reversal_form, *, open_modal=None):
        invoice = get_object_or_404(self.invoices(), pk=getattr(payment, f"{self.invoice_field}_id"))
        return render(self.request, "finance/payment_detail.html", {
            **self.context("Payment record"), **self.invoice_context(invoice),
            "payment": payment,
            "reversal_form": reversal_form,
            "reverse_url": self.url("payment-reverse", pk=payment.pk),
            "open_modal": open_modal,
        })


class PaymentReverse(PaymentDetail):
    operation = "post"
    http_method_names = ["post", "options"]

    def post(self, request, pk):
        payment = get_object_or_404(self.payments(), pk=pk)
        service = services.reverse_customer_payment if self.is_customer else services.reverse_supplier_payment
        form, reversed_payment = service(actor=request.user, payment=payment, data=request.POST)
        if reversed_payment is not None:
            messages.success(request, "Payment reversed. The original record is retained.")
            if request.user.has_perm(f"finance.view_{self.kind}payment"):
                return redirect(self.url("payment-detail", pk=payment.pk))
            return redirect(self.url("payment-create"))
        payment.refresh_from_db()
        return self.render_detail(payment, form, open_modal="reverse-payment")
