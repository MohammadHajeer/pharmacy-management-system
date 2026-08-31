from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.catalog.unit_economics import base_quantity, selected_unit_selling_price
from apps.core.document_numbers import sales_invoice_number_for_completion
from apps.core.models import PharmacySettings
from apps.finance.services import post_customer_payment
from apps.inventory.models import StockMovement
from apps.inventory.services import deduct_stock_fefo

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


@dataclass(frozen=True)
class SaleCompletionResult:
    invoice: SalesInvoice
    initial_payment: object | None


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


def _completion_line_amounts(line):
    line_subtotal = (line.quantity * line.unit_price).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    if line.discount_amount > line_subtotal:
        raise ValidationError(
            f"The stored discount for {line.medicine_description_snapshot} exceeds "
            "its rounded subtotal."
        )
    taxable_amount = line_subtotal - line.discount_amount
    tax_amount = (
        taxable_amount * line.tax_rate_percent / Decimal("100")
    ).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    line_total = (taxable_amount + tax_amount).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    return line_subtotal, tax_amount, line_total


def _validate_completion_state(invoice, lines):
    if invoice.status != SalesInvoice.Status.DRAFT:
        raise ValidationError("Only a draft sale can be completed.")
    if not lines:
        raise ValidationError("A completed sale requires at least one line.")
    if SaleBatchAllocation.objects.filter(
        sales_invoice_line__sales_invoice=invoice
    ).exists():
        raise ValidationError("A draft sale cannot already have stock allocations.")
    if (
        invoice.payments.exists()
        or invoice.paid_total != ZERO_MONEY
        or invoice.payment_status != SalesInvoice.PaymentStatus.UNPAID
    ):
        raise ValidationError("A draft sale cannot already have customer payments.")

    expected_subtotal = ZERO_MONEY
    expected_discount_total = ZERO_MONEY
    expected_tax_total = ZERO_MONEY
    expected_grand_total = ZERO_MONEY

    for line in lines:
        line.full_clean()
        if not line.medicine.is_active:
            raise ValidationError(
                f"{line.medicine_description_snapshot} is no longer active."
            )
        if not line.medicine_unit.is_active or not line.medicine_unit.sale_allowed:
            raise ValidationError(
                f"{line.unit_name_snapshot} is no longer an active sale unit."
            )
        expected_base_quantity = base_quantity(
            line.quantity,
            line.conversion_to_base_snapshot,
        )
        if line.requested_quantity_base != expected_base_quantity:
            raise ValidationError(
                "A sale line's requested base quantity no longer matches its "
                "quantity and conversion snapshot."
            )
        if (
            line.prescription_required_snapshot
            and not line.prescription_warning_acknowledged
        ):
            raise ValidationError(
                f"The prescription warning for {line.medicine_description_snapshot} "
                "must be acknowledged before completion."
            )

        line_subtotal, expected_tax_amount, expected_line_total = (
            _completion_line_amounts(line)
        )
        if line.tax_amount != expected_tax_amount or line.line_total != expected_line_total:
            raise ValidationError(
                "A sale line's stored tax or total no longer matches its inputs."
            )
        expected_subtotal += line_subtotal
        expected_discount_total += line.discount_amount
        expected_tax_total += expected_tax_amount
        expected_grand_total += expected_line_total

    expected_totals = (
        expected_subtotal,
        expected_discount_total,
        expected_tax_total,
        expected_grand_total,
    )
    stored_totals = (
        invoice.subtotal,
        invoice.discount_total,
        invoice.tax_total,
        invoice.grand_total,
    )
    if stored_totals != expected_totals:
        raise ValidationError("The sale totals no longer match its stored lines.")
    if invoice.balance_due != invoice.grand_total - invoice.paid_total:
        raise ValidationError("The sale balance is inconsistent.")


def _raise_payment_form_errors(form):
    messages = [str(error) for errors in form.errors.values() for error in errors]
    raise ValidationError(
        {"initial_payment": messages or ["The initial payment was rejected."]}
    )


def complete_sale(*, actor, sales_invoice_id, initial_payment_data=None):
    """Complete a draft sale atomically through Inventory and Finance.

    The invoice is locked first. Lines are processed in deterministic medicine/id
    order, while ``apps.inventory`` owns FEFO batch locks, quantity changes, and
    matching SALE movements. Optional payment writes remain owned by
    ``apps.finance``. Any validation or downstream failure rolls the whole unit
    of work back.
    """
    _require_permissions(actor, ("sales.complete_sale",))

    with transaction.atomic():
        # Lock only the invoice row. Joining nullable customer/prescription
        # relations here would make PostgreSQL reject FOR UPDATE on the
        # nullable side of an outer join.
        invoice = SalesInvoice.objects.select_for_update().get(pk=sales_invoice_id)
        _require_permissions(actor, ("sales.complete_sale",))

        lines = list(
            invoice.lines.select_related("medicine", "medicine_unit").order_by(
                "medicine_id",
                "id",
            )
        )
        _validate_completion_state(invoice, lines)

        if (
            invoice.customer_id is None
            and invoice.grand_total > ZERO_MONEY
            and initial_payment_data is None
        ):
            raise ValidationError(
                "A walk-in sale requires full payment during completion."
            )

        pharmacy_settings = PharmacySettings.objects.filter(singleton_key=1).first()
        if pharmacy_settings is None:
            raise ValidationError(
                "Pharmacy settings must be configured before completing a sale."
            )

        invoice.invoice_number = sales_invoice_number_for_completion(invoice.id)
        occurred_at = timezone.now()

        for line in lines:
            def create_allocation(allocation):
                sale_allocation = SaleBatchAllocation(
                    sales_invoice_line=line,
                    batch=allocation.batch,
                    allocated_quantity_base=allocation.quantity_base,
                    acquisition_cost_snapshot=allocation.unit_cost_snapshot,
                )
                sale_allocation.full_clean()
                sale_allocation.save()
                return sale_allocation.id

            deduct_stock_fefo(
                actor=actor,
                medicine=line.medicine,
                quantity_base=line.requested_quantity_base,
                source_type=StockMovement.MovementType.SALE,
                source_id=invoice.id,
                source_line_id_factory=create_allocation,
                reference_number=invoice.invoice_number,
                occurred_at=occurred_at,
            )

        invoice.pharmacy_name_snapshot = pharmacy_settings.pharmacy_name
        invoice.customer_name_snapshot = invoice.customer.name if invoice.customer else ""
        invoice.customer_phone_snapshot = invoice.customer.phone if invoice.customer else ""
        invoice.completed_at = occurred_at
        invoice.status = SalesInvoice.Status.COMPLETED

        # The database requires a completed walk-in sale to be settled. These
        # provisional values only make the not-yet-visible row valid while the
        # finance service posts the required payment in this same transaction.
        if invoice.customer_id is None:
            invoice.paid_total = invoice.grand_total
            invoice.balance_due = ZERO_MONEY
            invoice.payment_status = SalesInvoice.PaymentStatus.PAID

        invoice.full_clean()
        invoice.save()

        initial_payment = None
        if initial_payment_data is not None:
            payment_form, initial_payment = post_customer_payment(
                actor=actor,
                sales_invoice=invoice,
                data=initial_payment_data,
            )
            if initial_payment is None:
                _raise_payment_form_errors(payment_form)
            invoice.refresh_from_db()

        if invoice.customer_id is None and invoice.balance_due != ZERO_MONEY:
            raise ValidationError(
                "A walk-in sale must be fully settled during completion."
            )

        invoice.full_clean()

    return SaleCompletionResult(
        invoice=invoice,
        initial_payment=initial_payment,
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
