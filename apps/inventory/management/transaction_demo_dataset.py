"""Stable identities and sizes for the PHARMANEX transactional demo wave.

The records are fictional UI/testing fixtures.  Keep the namespace and identity
keys stable: the management command uses them to detect a complete prior run
without adopting, deleting, or rewriting unrelated rows.
"""

from uuid import UUID, uuid5


NAMESPACE = UUID("6493fd2f-b29d-4c77-8c35-eab4532662bc")
MARKER = "PHARMANEX-DEMO-V2"

CUSTOMER_COUNT = 50
PRESCRIBER_COUNT = 20
PRESCRIPTION_COUNT = 30
PRESCRIPTION_ITEMS_PER_RECORD = 2
COMPLETED_SALE_COUNT = 84
DRAFT_SALE_COUNT = 4
WALK_IN_SALE_COUNT = 36
PAID_SAVED_SALE_COUNT = 20
PARTIAL_SAVED_SALE_COUNT = 14
UNPAID_SAVED_SALE_COUNT = 14
PRESCRIPTION_LINKED_SALE_COUNT = 20
REVERSED_CUSTOMER_PAYMENT_COUNT = 3
PAID_PURCHASE_COUNT = 8
PARTIAL_PURCHASE_COUNT = 6
REVERSED_SUPPLIER_PAYMENT_COUNT = 2
MULTI_BATCH_SALE_COUNT = 3


def transaction_identity(kind, key):
    return uuid5(NAMESPACE, f"{kind}:{key}")
