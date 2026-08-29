from decimal import ROUND_HALF_UP, Decimal


QUANTITY_QUANTUM = Decimal("0.001")
UNIT_VALUE_QUANTUM = Decimal("0.0001")


def _require_decimal(value, name):
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal.")


def _require_positive_conversion(conversion_to_base):
    _require_decimal(conversion_to_base, "conversion_to_base")
    if conversion_to_base <= 0:
        raise ValueError("conversion_to_base must be greater than zero.")


def base_quantity(selected_quantity, conversion_to_base):
    """Convert a selected-unit quantity to the stored three-decimal base quantity."""
    _require_decimal(selected_quantity, "selected_quantity")
    _require_positive_conversion(conversion_to_base)
    return (selected_quantity * conversion_to_base).quantize(
        QUANTITY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def selected_unit_selling_price(base_unit_price, conversion_to_base):
    """Return the selected-unit price derived from the medicine's base-unit price."""
    _require_decimal(base_unit_price, "base_unit_price")
    _require_positive_conversion(conversion_to_base)
    return (base_unit_price * conversion_to_base).quantize(
        UNIT_VALUE_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def acquisition_cost_per_base_unit(selected_unit_cost, conversion_to_base):
    """Convert a selected purchase-unit cost to a four-decimal base-unit cost."""
    _require_decimal(selected_unit_cost, "selected_unit_cost")
    _require_positive_conversion(conversion_to_base)
    return (selected_unit_cost / conversion_to_base).quantize(
        UNIT_VALUE_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
