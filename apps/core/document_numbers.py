from enum import StrEnum
from uuid import UUID


class DocumentKind(StrEnum):
    SALES_INVOICE = "sales_invoice"
    PURCHASE_INVOICE = "purchase_invoice"
    CUSTOMER_RETURN = "customer_return"
    SUPPLIER_RETURN = "supplier_return"
    CUSTOMER_REFUND = "customer_refund"


_PREFIX_BY_KIND = {
    DocumentKind.SALES_INVOICE: "SAL",
    DocumentKind.PURCHASE_INVOICE: "PUR",
    DocumentKind.CUSTOMER_RETURN: "CRT",
    DocumentKind.SUPPLIER_RETURN: "SRT",
    DocumentKind.CUSTOMER_REFUND: "CRF",
}


def generate_document_number(document_id: UUID, kind: DocumentKind) -> str:
    """Return the approved deterministic number for a project document."""
    if not isinstance(document_id, UUID):
        raise TypeError("document_id must be a UUID instance")
    if not isinstance(kind, DocumentKind):
        raise TypeError("kind must be a DocumentKind instance")

    return f"{_PREFIX_BY_KIND[kind]}-{document_id.hex.upper()}"


def sales_invoice_number_for_completion(document_id: UUID) -> str:
    """Generate a sales number when the owning service completes a draft."""
    return generate_document_number(document_id, DocumentKind.SALES_INVOICE)


def purchase_invoice_number_for_posting(document_id: UUID) -> str:
    """Generate a purchase number when the owning service posts a draft."""
    return generate_document_number(document_id, DocumentKind.PURCHASE_INVOICE)


def customer_return_number_for_creation(document_id: UUID) -> str:
    """Generate the required number for a new customer return."""
    return generate_document_number(document_id, DocumentKind.CUSTOMER_RETURN)


def supplier_return_number_for_creation(document_id: UUID) -> str:
    """Generate the required number for a new supplier return."""
    return generate_document_number(document_id, DocumentKind.SUPPLIER_RETURN)


def customer_refund_number_for_creation(document_id: UUID) -> str:
    """Generate the required number for a new customer refund."""
    return generate_document_number(document_id, DocumentKind.CUSTOMER_REFUND)
