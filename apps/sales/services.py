from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.catalog.unit_economics import base_quantity, selected_unit_selling_price
from apps.core.models import PharmacySettings

from .forms import DraftSaleForm, DraftSaleLineFormSet
from .models import SaleBatchAllocation, SalesInvoice, SalesInvoiceLine


MONEY_QUANTUM = Decimal("0.01")
TAX_RATE_QUANTUM = Decimal("0.0001")
ZERO_MONEY = Decimal("0.00")
ZERO_TAX_RATE = Decimal("0.0000")


@dataclass(frozen=True)
class DraftLineCalculation:
    medicine: object
    medicine_unit: object
    quantity: Decimal
    conversion_to_base: Decimal
    requested_quantity_base: Decimal
    unit_price: Decimal
    line_subtotal: Decimal
    discount_amount: Decimal
    tax_rate_percent: Decimal
    tax_amount: Decimal
    line_total: Decimal
    prescription_warning_acknowledged: bool


def _require_permissions(actor, permissions):
    if not getattr(actor, "is_authenticated", False) or not actor.has_perms(permissions):
        raise PermissionDenied


def _calculate_line(*, line_form, tax_rate_percent):
    medicine = line_form.cleaned_data["medicine"]
    medicine_unit = line_form.cleaned_data["medicine_unit"]
    quantity = line_form.cleaned_data["quantity"]
    conversion = medicine_unit.conversion_to_base
    requested_base = base_quantity(quantity, conversion)
    if requested_base <= 0:
        line_form.add_error(
            "quantity",
            "Quantity converts to zero base units at the approved precision.",
        )
        return None

    unit_price = selected_unit_selling_price(
        medicine.default_selling_price,
        conversion,
    )
    line_subtotal = (quantity * unit_price).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    discount_amount = (line_form.cleaned_data.get("discount_amount") or ZERO_MONEY).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    if discount_amount > line_subtotal:
        line_form.add_error(
            "discount_amount",
            "Discount cannot exceed the rounded line subtotal.",
        )
        return None

    taxable_amount = line_subtotal - discount_amount
    tax_amount = (
        taxable_amount * tax_rate_percent / Decimal("100")
    ).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    line_total = (taxable_amount + tax_amount).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    return DraftLineCalculation(
        medicine=medicine,
        medicine_unit=medicine_unit,
        quantity=quantity,
        conversion_to_base=conversion,
        requested_quantity_base=requested_base,
        unit_price=unit_price,
        line_subtotal=line_subtotal,
        discount_amount=discount_amount,
        tax_rate_percent=tax_rate_percent,
        tax_amount=tax_amount,
        line_total=line_total,
        prescription_warning_acknowledged=line_form.cleaned_data.get(
            "prescription_warning_acknowledged",
            False,
        ),
    )


def process_draft_sale(*, actor, data, instance=None):
    """Create or replace a draft sale using server-authoritative calculations."""
    is_create = instance is None or instance._state.adding
    permissions = (
        ("sales.add_salesinvoice", "sales.add_salesinvoiceline")
        if is_create
        else ("sales.change_salesinvoice", "sales.change_salesinvoiceline")
    )
    _require_permissions(actor, permissions)

    form = DraftSaleForm(data=data)
    line_formset = DraftSaleLineFormSet(data=data, prefix="lines")
    form_is_valid = form.is_valid()
    lines_are_valid = line_formset.is_valid()
    if not form_is_valid or not lines_are_valid:
        return form, line_formset, None

    pharmacy_settings = PharmacySettings.objects.select_related("default_tax_rate").filter(
        singleton_key=1
    ).first()
    if pharmacy_settings is None:
        form.add_error(None, "Pharmacy settings must be configured before creating a sale.")
        return form, line_formset, None
    if (
        pharmacy_settings.default_tax_rate_id
        and not pharmacy_settings.default_tax_rate.is_active
    ):
        form.add_error(None, "The configured default tax rate is inactive.")
        return form, line_formset, None

    tax_rate_percent = (
        pharmacy_settings.default_tax_rate.rate_percent.quantize(
            TAX_RATE_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        if pharmacy_settings.default_tax_rate_id
        else ZERO_TAX_RATE
    )
    calculated_lines = [
        _calculate_line(line_form=line_form, tax_rate_percent=tax_rate_percent)
        for line_form in line_formset.forms
    ]
    if any(line is None for line in calculated_lines):
        return form, line_formset, None

    subtotal = sum((line.line_subtotal for line in calculated_lines), ZERO_MONEY)
    discount_total = sum((line.discount_amount for line in calculated_lines), ZERO_MONEY)
    tax_total = sum((line.tax_amount for line in calculated_lines), ZERO_MONEY)
    grand_total = sum((line.line_total for line in calculated_lines), ZERO_MONEY)

    with transaction.atomic():
        if is_create:
            invoice = SalesInvoice(pharmacist=actor)
        else:
            invoice = SalesInvoice.objects.select_for_update().get(pk=instance.pk)
            if invoice.status != SalesInvoice.Status.DRAFT:
                form.add_error(None, "Only a draft sale can be edited.")
                return form, line_formset, None
            if SaleBatchAllocation.objects.filter(
                sales_invoice_line__sales_invoice=invoice
            ).exists():
                form.add_error(
                    None,
                    "A draft with stock allocations cannot be edited by the draft service.",
                )
                return form, line_formset, None

        invoice.invoice_number = ""
        invoice.status = SalesInvoice.Status.DRAFT
        invoice.customer = form.cleaned_data["customer"]
        invoice.prescription = form.cleaned_data["prescription"]
        invoice.currency_code = pharmacy_settings.currency_code
        invoice.subtotal = subtotal
        invoice.discount_total = discount_total
        invoice.tax_total = tax_total
        invoice.grand_total = grand_total
        invoice.paid_total = ZERO_MONEY
        invoice.balance_due = grand_total
        invoice.payment_status = SalesInvoice.PaymentStatus.UNPAID
        invoice.completed_at = None
        invoice.full_clean()
        invoice.save()

        if not is_create:
            invoice.lines.all().delete()

        for line in calculated_lines:
            invoice_line = SalesInvoiceLine(
                sales_invoice=invoice,
                medicine=line.medicine,
                medicine_description_snapshot=line.medicine.name,
                medicine_unit=line.medicine_unit,
                unit_name_snapshot=line.medicine_unit.name,
                quantity=line.quantity,
                conversion_to_base_snapshot=line.conversion_to_base,
                requested_quantity_base=line.requested_quantity_base,
                unit_price=line.unit_price,
                discount_amount=line.discount_amount,
                tax_rate_percent=line.tax_rate_percent,
                tax_amount=line.tax_amount,
                line_total=line.line_total,
                prescription_required_snapshot=line.medicine.prescription_required,
                prescription_warning_acknowledged=(
                    line.prescription_warning_acknowledged
                ),
            )
            invoice_line.full_clean()
            invoice_line.save()

    return form, line_formset, invoice
