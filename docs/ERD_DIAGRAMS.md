# Pharmacy Management System - Readable ERD Diagrams

**Status:** Visual companion to the approved Phase 1 schema baseline  
**Authoritative source:** [`docs/ERD.md`](ERD.md)  
**Scope:** Relationships and cardinalities only; exact fields, constraints, indexes, precision, and deletion policies remain defined by the authoritative ERD.

## Why this is split into several diagrams

A single diagram for every Phase 1 entity creates crossing connectors and makes repeated entities such as `Medicine`, `MedicineBatch`, `SalesInvoice`, and `User` difficult to trace. These views intentionally repeat shared anchor entities so each relationship stays local and readable. A repeated box represents the same table, not a duplicate table.

## Reading the connectors

| Symbol | Meaning |
| --- | --- |
| `||` | exactly one |
| `o|` | zero or one |
| `|{` | one or many |
| `o{` | zero or many |
| solid relationship | database foreign key or Django-owned many-to-many relation |
| dashed relationship | logical traceability through `source_type`, `source_id`, and `source_line_id`; not a database foreign key |

Every relationship label names the foreign-key field or the business role of that field.

For invoice, prescription, and return line collections, `|{` describes the approved posted/completed business invariant. A draft parent record may temporarily have no lines before it is posted or completed.

---

# 1. End-to-End Business Flow

This is the navigation view. It shows transaction flow, not database cardinality.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#f8fafc","primaryTextColor":"#0f172a","primaryBorderColor":"#64748b","lineColor":"#475569","tertiaryColor":"#ffffff"},"themeCSS":".edgeLabel .label { fill: #0f172a !important; } .edgeLabel rect.background { fill: #ffffff !important; stroke: #cbd5e1 !important; }"}}%%
flowchart TB
    SUPPLIER[Supplier]
    PURCHASE[Purchase invoice and lines]
    BATCH[Medicine batch]
    SALE[POS sale and FEFO allocation]
    SALES_INVOICE[Sales invoice]
    PAYMENT[Customer payment and balance]
    RETURN[Customer return and refund]
    REPORT[Reports]
    PRESCRIPTION[Prescription]

    SUPPLIER -->|posts and receives| PURCHASE
    PURCHASE -->|creates or increases| BATCH
    BATCH -->|allocated by FEFO| SALE
    PRESCRIPTION -->|optionally supports| SALE
    SALE -->|completes as| SALES_INVOICE
    SALES_INVOICE -->|settled by| PAYMENT
    SALES_INVOICE -->|may produce| RETURN
    PAYMENT -->|feeds| REPORT
    RETURN -->|feeds| REPORT
    BATCH -->|stock position feeds| REPORT
```

---

# 2. Authentication and Core Settings

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#f8fafc","primaryTextColor":"#0f172a","primaryBorderColor":"#64748b","lineColor":"#475569","tertiaryColor":"#ffffff"},"themeCSS":".edgeLabel .label { fill: #0f172a !important; } .edgeLabel rect.background { fill: #ffffff !important; stroke: #cbd5e1 !important; }"}}%%
erDiagram
    AUTH_USER {
        bigint id PK
    }
    AUTH_GROUP {
        bigint id PK
        string name UK
    }
    TAX_RATE {
        uuid id PK
        string code UK
    }
    PHARMACY_SETTINGS {
        uuid id PK
        uuid default_tax_rate_id FK
    }
    AUTH_USER }o--o{ AUTH_GROUP : "groups"
    TAX_RATE o|--o| PHARMACY_SETTINGS : "default_tax_rate"
```

`PaymentMethod` is shown in the payment/refund views where its actual foreign keys are used. `User` is repeated in transaction views to make actor relationships explicit.

---

# 3. Medicine Catalog

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#f8fafc","primaryTextColor":"#0f172a","primaryBorderColor":"#64748b","lineColor":"#475569","tertiaryColor":"#ffffff"},"themeCSS":".edgeLabel .label { fill: #0f172a !important; } .edgeLabel rect.background { fill: #ffffff !important; stroke: #cbd5e1 !important; }"}}%%
erDiagram
    CATEGORY {
        uuid id PK
        string name
    }
    MANUFACTURER {
        uuid id PK
        string name
    }
    MEDICINE {
        uuid id PK
        uuid category_id FK
        uuid manufacturer_id FK
    }
    MEDICINE_UNIT {
        uuid id PK
        uuid medicine_id FK
        decimal conversion_to_base
        boolean is_base_unit
    }
    MEDICINE_BARCODE {
        uuid id PK
        uuid medicine_unit_id FK
        string barcode UK
    }
    MEDICINE_BATCH {
        uuid id PK
        uuid medicine_id FK
        date expiry_date
        decimal quantity_available_base
    }

    CATEGORY ||--o{ MEDICINE : "category"
    MANUFACTURER ||--o{ MEDICINE : "manufacturer"
    MEDICINE ||--o{ MEDICINE_UNIT : "medicine"
    MEDICINE_UNIT ||--o{ MEDICINE_BARCODE : "medicine_unit"
    MEDICINE ||--o{ MEDICINE_BATCH : "medicine"
```

---

# 4. Purchasing and Batch Receipt

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#f8fafc","primaryTextColor":"#0f172a","primaryBorderColor":"#64748b","lineColor":"#475569","tertiaryColor":"#ffffff"},"themeCSS":".edgeLabel .label { fill: #0f172a !important; } .edgeLabel rect.background { fill: #ffffff !important; stroke: #cbd5e1 !important; }"}}%%
erDiagram
    AUTH_USER {
        bigint id PK
    }
    SUPPLIER {
        uuid id PK
        string code UK
    }
    PURCHASE_INVOICE {
        uuid id PK
        uuid supplier_id FK
        bigint created_by_id FK
        bigint posted_by_id FK
        string status
    }
    PURCHASE_INVOICE_LINE {
        uuid id PK
        uuid purchase_invoice_id FK
        uuid medicine_id FK
        uuid medicine_unit_id FK
        uuid medicine_batch_id FK
    }
    MEDICINE {
        uuid id PK
    }
    MEDICINE_UNIT {
        uuid id PK
        uuid medicine_id FK
    }
    MEDICINE_BATCH {
        uuid id PK
        uuid medicine_id FK
    }

    SUPPLIER ||--o{ PURCHASE_INVOICE : "supplier"
    AUTH_USER ||--o{ PURCHASE_INVOICE : "created_by"
    AUTH_USER o|--o{ PURCHASE_INVOICE : "posted_by"
    PURCHASE_INVOICE ||--|{ PURCHASE_INVOICE_LINE : "purchase_invoice"
    MEDICINE ||--o{ PURCHASE_INVOICE_LINE : "medicine"
    MEDICINE_UNIT ||--o{ PURCHASE_INVOICE_LINE : "medicine_unit"
    MEDICINE_BATCH o|--o{ PURCHASE_INVOICE_LINE : "medicine_batch after posting"
```

Posting a purchase line resolves its optional `medicine_batch` and creates one positive purchase-receipt stock movement. The movement link is shown separately in section 13 because it is logical source traceability rather than a foreign key.

---

# 5. Prescription Record

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#f8fafc","primaryTextColor":"#0f172a","primaryBorderColor":"#64748b","lineColor":"#475569","tertiaryColor":"#ffffff"},"themeCSS":".edgeLabel .label { fill: #0f172a !important; } .edgeLabel rect.background { fill: #ffffff !important; stroke: #cbd5e1 !important; }"}}%%
erDiagram
    CUSTOMER {
        uuid id PK
    }
    PRESCRIBER {
        uuid id PK
    }
    AUTH_USER {
        bigint id PK
    }
    PRESCRIPTION {
        uuid id PK
        uuid customer_id FK
        uuid prescriber_id FK
        bigint created_by_id FK
    }
    PRESCRIPTION_ITEM {
        uuid id PK
        uuid prescription_id FK
        uuid medicine_id FK
    }
    MEDICINE {
        uuid id PK
    }

    CUSTOMER o|--o{ PRESCRIPTION : "customer"
    PRESCRIBER o|--o{ PRESCRIPTION : "prescriber"
    AUTH_USER ||--o{ PRESCRIPTION : "created_by"
    PRESCRIPTION ||--|{ PRESCRIPTION_ITEM : "prescription"
    MEDICINE ||--o{ PRESCRIPTION_ITEM : "medicine"
```

---

# 6. Sales Header and Lines

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#f8fafc","primaryTextColor":"#0f172a","primaryBorderColor":"#64748b","lineColor":"#475569","tertiaryColor":"#ffffff"},"themeCSS":".edgeLabel .label { fill: #0f172a !important; } .edgeLabel rect.background { fill: #ffffff !important; stroke: #cbd5e1 !important; }"}}%%
erDiagram
    CUSTOMER {
        uuid id PK
    }
    PRESCRIPTION {
        uuid id PK
    }
    AUTH_USER {
        bigint id PK
    }
    SALES_INVOICE {
        uuid id PK
        uuid customer_id FK
        uuid prescription_id FK
        bigint pharmacist_id FK
    }
    SALES_INVOICE_LINE {
        uuid id PK
        uuid sales_invoice_id FK
        uuid medicine_id FK
        uuid medicine_unit_id FK
    }
    MEDICINE {
        uuid id PK
    }
    MEDICINE_UNIT {
        uuid id PK
    }

    CUSTOMER o|--o{ SALES_INVOICE : "customer; null means walk-in"
    PRESCRIPTION o|--o{ SALES_INVOICE : "prescription"
    AUTH_USER ||--o{ SALES_INVOICE : "pharmacist"
    SALES_INVOICE ||--|{ SALES_INVOICE_LINE : "sales_invoice"
    MEDICINE ||--o{ SALES_INVOICE_LINE : "medicine"
    MEDICINE_UNIT ||--o{ SALES_INVOICE_LINE : "medicine_unit"
```

---

# 7. FEFO Batch Allocation

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#f8fafc","primaryTextColor":"#0f172a","primaryBorderColor":"#64748b","lineColor":"#475569","tertiaryColor":"#ffffff"},"themeCSS":".edgeLabel .label { fill: #0f172a !important; } .edgeLabel rect.background { fill: #ffffff !important; stroke: #cbd5e1 !important; }"}}%%
erDiagram
    SALES_INVOICE_LINE {
        uuid id PK
    }
    SALE_BATCH_ALLOCATION {
        uuid id PK
        uuid sales_invoice_line_id FK
        uuid batch_id FK
        decimal allocated_quantity_base
    }
    MEDICINE_BATCH {
        uuid id PK
        date expiry_date
    }

    SALES_INVOICE_LINE ||--|{ SALE_BATCH_ALLOCATION : "sales_invoice_line"
    MEDICINE_BATCH ||--o{ SALE_BATCH_ALLOCATION : "batch"
```

One completed sales line may allocate across several batches. The `(sales_invoice_line, batch)` pair is unique, so the same batch cannot appear twice for one line.

---

# 8. Customer Payment and Invoice Balance

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#f8fafc","primaryTextColor":"#0f172a","primaryBorderColor":"#64748b","lineColor":"#475569","tertiaryColor":"#ffffff"},"themeCSS":".edgeLabel .label { fill: #0f172a !important; } .edgeLabel rect.background { fill: #ffffff !important; stroke: #cbd5e1 !important; }"}}%%
erDiagram
    AUTH_USER {
        bigint id PK
    }
    CUSTOMER {
        uuid id PK
    }
    PAYMENT_METHOD {
        uuid id PK
    }
    SALES_INVOICE {
        uuid id PK
        uuid customer_id FK
        decimal grand_total
        decimal paid_total
        decimal balance_due
    }
    CUSTOMER_PAYMENT {
        uuid id PK
        uuid sales_invoice_id FK
        uuid customer_id FK
        uuid payment_method_id FK
        bigint processed_by_id FK
        bigint reversed_by_id FK
        decimal amount
        string status
    }

    SALES_INVOICE ||--o{ CUSTOMER_PAYMENT : "sales_invoice"
    CUSTOMER o|--o{ SALES_INVOICE : "customer"
    CUSTOMER o|--o{ CUSTOMER_PAYMENT : "customer"
    PAYMENT_METHOD ||--o{ CUSTOMER_PAYMENT : "payment_method"
    AUTH_USER ||--o{ CUSTOMER_PAYMENT : "processed_by"
    AUTH_USER o|--o{ CUSTOMER_PAYMENT : "reversed_by"
```

The invoice balance is derived from posted, non-reversed customer payments. Payments remain separate transaction rows; they do not replace or rewrite the invoice.

---

# 9. Customer Return and Lines

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#f8fafc","primaryTextColor":"#0f172a","primaryBorderColor":"#64748b","lineColor":"#475569","tertiaryColor":"#ffffff"},"themeCSS":".edgeLabel .label { fill: #0f172a !important; } .edgeLabel rect.background { fill: #ffffff !important; stroke: #cbd5e1 !important; }"}}%%
erDiagram
    AUTH_USER {
        bigint id PK
    }
    CUSTOMER {
        uuid id PK
    }
    SALES_INVOICE {
        uuid id PK
        uuid customer_id FK
    }
    SALES_INVOICE_LINE {
        uuid id PK
        uuid sales_invoice_id FK
    }
    MEDICINE_BATCH {
        uuid id PK
    }
    CUSTOMER_RETURN {
        uuid id PK
        uuid sales_invoice_id FK
        uuid customer_id FK
        bigint processed_by_id FK
    }
    CUSTOMER_RETURN_LINE {
        uuid id PK
        uuid customer_return_id FK
        uuid sales_invoice_line_id FK
        uuid batch_id FK
    }
    SALES_INVOICE ||--o{ CUSTOMER_RETURN : "sales_invoice"
    CUSTOMER o|--o{ CUSTOMER_RETURN : "customer"
    AUTH_USER ||--o{ CUSTOMER_RETURN : "processed_by"
    CUSTOMER_RETURN ||--|{ CUSTOMER_RETURN_LINE : "customer_return"
    SALES_INVOICE_LINE ||--o{ CUSTOMER_RETURN_LINE : "sales_invoice_line"
    MEDICINE_BATCH ||--o{ CUSTOMER_RETURN_LINE : "batch"
```

The return line identifies the original sales line and exact allocated batch. A resellable restock creates a positive stock movement.

---

# 10. Customer Refund

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#f8fafc","primaryTextColor":"#0f172a","primaryBorderColor":"#64748b","lineColor":"#475569","tertiaryColor":"#ffffff"},"themeCSS":".edgeLabel .label { fill: #0f172a !important; } .edgeLabel rect.background { fill: #ffffff !important; stroke: #cbd5e1 !important; }"}}%%
erDiagram
    AUTH_USER {
        bigint id PK
    }
    PAYMENT_METHOD {
        uuid id PK
    }
    SALES_INVOICE {
        uuid id PK
    }
    CUSTOMER_RETURN {
        uuid id PK
    }
    CUSTOMER_REFUND {
        uuid id PK
        uuid customer_return_id FK
        uuid sales_invoice_id FK
        uuid payment_method_id FK
        bigint processed_by_id FK
    }

    CUSTOMER_RETURN ||--o{ CUSTOMER_REFUND : "customer_return"
    SALES_INVOICE ||--o{ CUSTOMER_REFUND : "sales_invoice"
    PAYMENT_METHOD ||--o{ CUSTOMER_REFUND : "payment_method"
    AUTH_USER ||--o{ CUSTOMER_REFUND : "processed_by"
```

The refund is a separate posted financial transaction. It does not rewrite the original sale total.

---

# 11. Supplier Payment and Invoice Balance

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#f8fafc","primaryTextColor":"#0f172a","primaryBorderColor":"#64748b","lineColor":"#475569","tertiaryColor":"#ffffff"},"themeCSS":".edgeLabel .label { fill: #0f172a !important; } .edgeLabel rect.background { fill: #ffffff !important; stroke: #cbd5e1 !important; }"}}%%
erDiagram
    AUTH_USER {
        bigint id PK
    }
    SUPPLIER {
        uuid id PK
    }
    PAYMENT_METHOD {
        uuid id PK
    }
    PURCHASE_INVOICE {
        uuid id PK
        uuid supplier_id FK
        decimal grand_total
        decimal paid_total
        decimal remaining_balance
    }
    SUPPLIER_PAYMENT {
        uuid id PK
        uuid purchase_invoice_id FK
        uuid supplier_id FK
        uuid payment_method_id FK
        bigint processed_by_id FK
        bigint reversed_by_id FK
        decimal amount
        string status
    }

    PURCHASE_INVOICE ||--o{ SUPPLIER_PAYMENT : "purchase_invoice"
    SUPPLIER ||--o{ PURCHASE_INVOICE : "supplier"
    SUPPLIER ||--o{ SUPPLIER_PAYMENT : "supplier"
    PAYMENT_METHOD ||--o{ SUPPLIER_PAYMENT : "payment_method"
    AUTH_USER ||--o{ SUPPLIER_PAYMENT : "processed_by"
    AUTH_USER o|--o{ SUPPLIER_PAYMENT : "reversed_by"
```

The purchase-invoice balance is derived from posted, non-reversed supplier payments. Supplier returns affect the supplier statement separately and are shown in section 12.

---

# 12. Supplier Return

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#f8fafc","primaryTextColor":"#0f172a","primaryBorderColor":"#64748b","lineColor":"#475569","tertiaryColor":"#ffffff"},"themeCSS":".edgeLabel .label { fill: #0f172a !important; } .edgeLabel rect.background { fill: #ffffff !important; stroke: #cbd5e1 !important; }"}}%%
erDiagram
    AUTH_USER {
        bigint id PK
    }
    SUPPLIER {
        uuid id PK
    }
    PURCHASE_INVOICE {
        uuid id PK
    }
    MEDICINE {
        uuid id PK
    }
    MEDICINE_BATCH {
        uuid id PK
        uuid medicine_id FK
    }
    SUPPLIER_RETURN {
        uuid id PK
        uuid supplier_id FK
        uuid purchase_invoice_id FK
        bigint processed_by_id FK
    }
    SUPPLIER_RETURN_LINE {
        uuid id PK
        uuid supplier_return_id FK
        uuid medicine_id FK
        uuid batch_id FK
    }

    SUPPLIER ||--o{ SUPPLIER_RETURN : "supplier"
    PURCHASE_INVOICE o|--o{ SUPPLIER_RETURN : "purchase_invoice"
    AUTH_USER ||--o{ SUPPLIER_RETURN : "processed_by"
    SUPPLIER_RETURN ||--|{ SUPPLIER_RETURN_LINE : "supplier_return"
    MEDICINE ||--o{ SUPPLIER_RETURN_LINE : "medicine"
    MEDICINE_BATCH ||--o{ SUPPLIER_RETURN_LINE : "batch"
```

Posting decreases the exact selected batch and creates one negative supplier-return stock movement for each return line.

---

# 13. Authoritative Stock Movement and Source Traceability

This view deliberately distinguishes real foreign keys from the generic source reference. There is no database foreign key from a source line/allocation to `StockMovement`.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#f8fafc","primaryTextColor":"#0f172a","primaryBorderColor":"#64748b","lineColor":"#475569","tertiaryColor":"#ffffff"},"themeCSS":".edgeLabel .label { fill: #0f172a !important; } .edgeLabel rect.background { fill: #ffffff !important; stroke: #cbd5e1 !important; }"}}%%
flowchart TB
    MEDICINE[Medicine]
    BATCH[MedicineBatch]
    USER[User]
    MOVEMENT[StockMovement]

    PURCHASE_LINE[PurchaseInvoiceLine]
    SALE_ALLOCATION[SaleBatchAllocation]
    CUSTOMER_RETURN_LINE[CustomerReturnLine]
    SUPPLIER_RETURN_LINE[SupplierReturnLine]

    MEDICINE -->|medicine FK| MOVEMENT
    BATCH -->|batch FK| MOVEMENT
    USER -->|performed_by FK| MOVEMENT

    PURCHASE_LINE -. "PURCHASE_RECEIPT: source_line_id" .-> MOVEMENT
    SALE_ALLOCATION -. "SALE: source_line_id" .-> MOVEMENT
    CUSTOMER_RETURN_LINE -. "CUSTOMER_RETURN_RESTOCK: source_line_id" .-> MOVEMENT
    SUPPLIER_RETURN_LINE -. "SUPPLIER_RETURN: source_line_id" .-> MOVEMENT
```

The logical source mapping is:

| Movement/source type | `source_id` identifies | `source_line_id` identifies | Direction |
| --- | --- | --- | --- |
| `PURCHASE_RECEIPT` | `PurchaseInvoice` | `PurchaseInvoiceLine` | positive |
| `SALE` | `SalesInvoice` | `SaleBatchAllocation` | negative |
| `CUSTOMER_RETURN_RESTOCK` | `CustomerReturn` | `CustomerReturnLine` | positive |
| `SUPPLIER_RETURN` | `SupplierReturn` | `SupplierReturnLine` | negative |

`apps.inventory` is the only app allowed to change `MedicineBatch.quantity_available_base`. The batch change and its stock movement are created in the same database transaction.

---

# 14. Complete Foreign-Key Relationship Index

This index is the text fallback for every connector. “Optional” means the foreign-key column may be `NULL`.

| Owning entity | Foreign-key field | Referenced entity | Optional |
| --- | --- | --- | --- |
| `PharmacySettings` | `default_tax_rate` | `TaxRate` | Yes |
| `Medicine` | `category` | `Category` | No |
| `Medicine` | `manufacturer` | `Manufacturer` | No |
| `MedicineUnit` | `medicine` | `Medicine` | No |
| `MedicineBarcode` | `medicine_unit` | `MedicineUnit` | No |
| `MedicineBatch` | `medicine` | `Medicine` | No |
| `StockMovement` | `medicine` | `Medicine` | No |
| `StockMovement` | `batch` | `MedicineBatch` | No |
| `StockMovement` | `performed_by` | `User` | No |
| `PurchaseInvoice` | `supplier` | `Supplier` | No |
| `PurchaseInvoice` | `created_by` | `User` | No |
| `PurchaseInvoice` | `posted_by` | `User` | Yes |
| `PurchaseInvoiceLine` | `purchase_invoice` | `PurchaseInvoice` | No |
| `PurchaseInvoiceLine` | `medicine` | `Medicine` | No |
| `PurchaseInvoiceLine` | `medicine_unit` | `MedicineUnit` | No |
| `PurchaseInvoiceLine` | `medicine_batch` | `MedicineBatch` | Yes, until posting |
| `Prescription` | `customer` | `Customer` | Yes |
| `Prescription` | `prescriber` | `Prescriber` | Yes |
| `Prescription` | `created_by` | `User` | No |
| `PrescriptionItem` | `prescription` | `Prescription` | No |
| `PrescriptionItem` | `medicine` | `Medicine` | No |
| `SalesInvoice` | `customer` | `Customer` | Yes; null is walk-in |
| `SalesInvoice` | `prescription` | `Prescription` | Yes |
| `SalesInvoice` | `pharmacist` | `User` | No |
| `SalesInvoiceLine` | `sales_invoice` | `SalesInvoice` | No |
| `SalesInvoiceLine` | `medicine` | `Medicine` | No |
| `SalesInvoiceLine` | `medicine_unit` | `MedicineUnit` | No |
| `SaleBatchAllocation` | `sales_invoice_line` | `SalesInvoiceLine` | No |
| `SaleBatchAllocation` | `batch` | `MedicineBatch` | No |
| `CustomerPayment` | `sales_invoice` | `SalesInvoice` | No |
| `CustomerPayment` | `customer` | `Customer` | Yes |
| `CustomerPayment` | `payment_method` | `PaymentMethod` | No |
| `CustomerPayment` | `processed_by` | `User` | No |
| `CustomerPayment` | `reversed_by` | `User` | Yes |
| `SupplierPayment` | `purchase_invoice` | `PurchaseInvoice` | No |
| `SupplierPayment` | `supplier` | `Supplier` | No |
| `SupplierPayment` | `payment_method` | `PaymentMethod` | No |
| `SupplierPayment` | `processed_by` | `User` | No |
| `SupplierPayment` | `reversed_by` | `User` | Yes |
| `CustomerReturn` | `sales_invoice` | `SalesInvoice` | No |
| `CustomerReturn` | `customer` | `Customer` | Yes |
| `CustomerReturn` | `processed_by` | `User` | No |
| `CustomerReturnLine` | `customer_return` | `CustomerReturn` | No |
| `CustomerReturnLine` | `sales_invoice_line` | `SalesInvoiceLine` | No |
| `CustomerReturnLine` | `batch` | `MedicineBatch` | No |
| `CustomerRefund` | `customer_return` | `CustomerReturn` | No |
| `CustomerRefund` | `sales_invoice` | `SalesInvoice` | No |
| `CustomerRefund` | `payment_method` | `PaymentMethod` | No |
| `CustomerRefund` | `processed_by` | `User` | No |
| `SupplierReturn` | `supplier` | `Supplier` | No |
| `SupplierReturn` | `purchase_invoice` | `PurchaseInvoice` | Yes |
| `SupplierReturn` | `processed_by` | `User` | No |
| `SupplierReturnLine` | `supplier_return` | `SupplierReturn` | No |
| `SupplierReturnLine` | `medicine` | `Medicine` | No |
| `SupplierReturnLine` | `batch` | `MedicineBatch` | No |

The Django-managed `User`-to-`Group` membership is many-to-many and remains part of Django's built-in authentication schema.
