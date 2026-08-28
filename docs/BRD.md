# Pharmacy Management System — Business Requirements Document

**Document status:** Phase 1 scope baseline

**Delivery window:** 9 calendar days

**Product type:** Single-pharmacy, full-stack Django modular monolith

**Requirements sources:** `REPO-IMPLEMENTATION-CONTEXT.md`, `PHASE-1.md`, and `TECH-SPEC.md`

Source precedence is:

1. Repository implementation context
2. Phase 1 document
3. Technical specification

The repository implementation context governs whenever a proposed design conflicts with the working foundation. The explicit conflict resolutions requested for this BRD are binding and are recorded in Sections 3, 4, and 7.

## 1. Project overview

The Pharmacy Management System is a single-pharmacy system for managing the connected operational and financial workflow of a pharmacy. It covers medicine catalog data, suppliers, customers, prescriptions, purchasing, medicine receipt, batch-aware inventory, Point of Sale (POS), sales and purchase invoices, payments and balances, returns and refunds, discounts and taxes, cashier/pharmacist shifts, audit history, reporting, exports, backup, and configurable pharmacy settings.

The system must connect these capabilities as real workflows rather than present them as unrelated CRUD pages. In particular:

- receiving a purchase must create or update medicine batches, create stock-movement history, increase inventory, and support the related purchase invoice and supplier balance;
- completing a sale must allocate eligible batches, reduce inventory through stock movements, create a professional sales invoice/receipt, record payment or balance information, and preserve pricing, tax, discount, unit-conversion, and acquisition-cost snapshots;
- customer and supplier payments must remain separate from invoices so unpaid, partially paid, and paid states can be represented accurately;
- customer and supplier returns must remain traceable to their original transactions and affect the correct batch and financial balance where applicable;
- sensitive operations must be authorized, auditable, and protected from duplicate posting.

### Existing foundation that governs the BRD

The project already exists and must be extended rather than replaced. Phase 1 must use:

- Django 6.1 as the full-stack framework;
- Django Templates;
- Django Forms and ModelForms;
- Django ORM;
- PostgreSQL hosted on Neon;
- Django's built-in User model;
- username/password authentication;
- Django sessions;
- Django Groups and Permissions;
- the exact groups `Owner / Admin`, `Pharmacist`, `Inventory Manager`, and `Accountant`;
- Tailwind CSS v4;
- vanilla JavaScript, including same-origin interactive POS behavior;
- `uv` for Python dependency management;
- npm for frontend tooling;
- feature apps under `apps/`;
- shared layouts and components under the root `templates/` directory.

The existing login/logout flow, authentication pages, project layout, settings conventions, shared UI foundation, and navigation mechanism must be preserved. The Pharmacist performs cashier/POS duties; there is no separate Cashier group and no `Cashier-Pharmacist` group.

### Product architecture

The system is a server-rendered modular monolith. Simple CRUD behavior may remain in Django models, forms, and views. Multi-record transactional workflows must use explicit service functions and `transaction.atomic()` so their related writes either all succeed or all fail. The browser is not authoritative for stock, pricing, discounts, taxes, totals, permissions, or transaction state.

## 2. Objectives

### 2.1 Primary business objectives

1. Provide one connected operational system from supplier purchasing through batch receipt, inventory control, POS sale, invoicing, payment, return/refund, and reporting.
2. Protect patient safety by preventing sale of expired batches, providing prescription and expiry warnings, using FEFO-assisted batch selection, and preserving batch-level traceability.
3. Keep medicine availability practical by allowing a controlled, auditable sale when non-expired medicine is physically present but recorded stock is insufficient.
4. Maintain reliable inventory through append-style stock movements, batch-specific quantities and acquisition costs, physical stock counts, adjustments, write-offs, and reconciliation.
5. Produce professional, historically accurate sales and purchase invoices, receipts, payment records, return/refund documents, and print-ready output.
6. Represent customer and supplier receivables/payables through separate invoices and payments, including partial and multiple payments.
7. Enforce role-based access on the server while preserving the existing Django authentication foundation and role-aware navigation.
8. Preserve accountability through practical append-only audit records, alerts, transaction history, and non-destructive handling of posted records.
9. Deliver useful operational and financial reports and exports based on authoritative transaction data.
10. Deliver the mandatory Phase 1 scope within nine days using simple, established Django patterns, early integration, and minimal unnecessary abstraction.

### 2.2 Success conditions

Phase 1 is complete only when every in-scope capability is implemented as a connected, working workflow rather than a mock or disconnected screen. At minimum, success requires:

- authorized staff can perform the workflows assigned to their group;
- anonymous and unauthorized access is denied server-side;
- purchases and returns update the correct batches through stock movements;
- sales use eligible non-expired batches and support multi-batch allocation;
- controlled discrepancies produce the required audit record and role-targeted alert;
- invoices, payments, balances, shifts, refunds, and statements reconcile according to their authoritative records;
- historical price, tax, discount, unit, and acquisition-cost snapshots remain stable;
- required reports and exports are produced from real stored transactions;
- backup and restore procedures are documented and tested;
- critical posting operations do not create duplicates when the same submission is retried.

## 3. Scope

### 3.1 Phase 1 in-scope capabilities

All of the following are mandatory in Phase 1:

- existing authentication and role-aware navigation;
- server-side group and model-permission enforcement;
- medicine catalog, categories, manufacturers, units, conversions, barcodes, pricing, prescription flags, thresholds, and active/inactive state;
- suppliers, customers, walk-in customers, and prescribers;
- medicine batches, expiry/expiration tracking, acquisition cost, stock quantities, stock movements, counts, adjustments, write-offs, and alerts;
- lightweight purchase orders, partial/full receiving, purchase invoices, supplier balances/payments, and supplier returns;
- pharmacist-facing POS, keyboard/HID barcode scanning, held/resumed sales, FEFO, actual-batch deviation, discounts, taxes, customer selection, prescription association, payment, and completion;
- controlled stock-discrepancy sale with acknowledgment, audit, and Owner/Admin plus Inventory Manager alerts;
- prescription records and lightweight non-blocking prescription-required warnings;
- sales invoices/receipts and purchase invoices with professional, print-friendly output and PDF where reasonably achievable;
- unpaid, partially paid, and fully paid invoice states; separate customer/supplier payments; multiple payments; balances; payment history; and statements;
- pharmacist/cashier opening and closing shift reconciliation;
- customer returns, supplier returns, refunds, safe batch restocking, and financial traceability;
- server-side discount and tax calculations with historical snapshots;
- batch-cost-based COGS, gross profit, and inventory valuation;
- practical append-only audit logging for all listed sensitive operations;
- bounded idempotency for critical posting workflows;
- dashboard, reports, CSV/XLSX exports, and PDF where applicable;
- pharmacy settings, payment methods, document information, tax configuration, and stock/expiry defaults;
- documented PostgreSQL backup strategy and a tested restore procedure.

### 3.2 Reactivation of previously deferred items

The later instruction that all original mandatory pharmacy requirements belong to Phase 1 supersedes earlier deferrals. The resulting decisions are:

| Previously deferred item | Phase 1 decision | Required boundary |
|---|---|---|
| Purchase orders | **Reactivated and mandatory** | Lightweight order, item, status, partial/full receiving, and remaining-quantity workflow. No enterprise multi-level approval chain. |
| Cashier-shift reconciliation | **Reactivated and mandatory** | Opening cash, expected cash, actual cash, discrepancy, close, and preserved history for the Pharmacist acting as cashier. No separate Cashier role. |
| Idempotency | **Reactivated and mandatory in bounded form** | Retrying or double-submitting a critical posting action must not create a duplicate sale, receipt, payment, return/refund, stock reconciliation, or other posted transaction. No separate enterprise idempotency platform is required. |
| Advanced audit | **Reactivated as complete practical audit coverage** | Append-only application audit records must cover every sensitive operation listed in this BRD. Cryptographic ledgers, event sourcing, and enterprise tamper-evidence infrastructure remain out of scope. |
| Complex stock-discrepancy workflows | **Reactivated only as the explicit lightweight discrepancy capability** | The sale override, required evidence, audit entry, role alerts, open/resolved state, and later reconciliation are mandatory. A case-management or enterprise investigation subsystem is not. |

These bounded forms are the Phase 1 requirements. They are not optional backlog items, and they must not be expanded into the excluded enterprise variants during the nine-day delivery.

### 3.3 Backlog and out-of-scope capabilities

The following are not part of Phase 1 unless a later explicit team decision changes the scope:

- replacing username login with email login;
- a custom User model merely for authentication;
- a custom Role model;
- a separate Cashier group;
- JWT or DRF authentication;
- DRF-centric or API-first replacement of the full-stack Django application;
- React, Vue, Angular, or another separate SPA;
- Redis;
- microservices;
- multi-branch pharmacy support;
- shelf, bin, or physical storage-location tracking;
- full double-entry accounting or a general ledger;
- enterprise multi-level purchase-order approval;
- enterprise stock-discrepancy investigation/case management;
- enterprise cryptographic audit infrastructure or event sourcing;
- a separate enterprise idempotency platform;
- clinical decision-making or AI medical advice/recommendations;
- e-commerce;
- delivery management;
- loyalty systems;
- payroll or HR;
- insurance integrations;
- strict visual-design prescriptions such as fixed colors, typography, exact layouts, or exact component counts.

### 3.4 Concrete app and reserved-navigation mapping

Model ownership and navigation namespaces are deliberately separated where one navigation page aggregates records owned by more than one app. A model has one authoritative owning app; another app may consume it through an agreed service/query interface but must not duplicate it.

| Existing/reserved navigation | URL namespace | Owning Django app | Boundary and authoritative ownership |
|---|---|---|---|
| Dashboard | `dashboard` | `apps.dashboard` | Existing authenticated dashboard shell and role-aware widgets. No duplicate dashboard app per role. |
| Sales | `sales` | `apps.sales` | POS, held/completed sales, sales invoices and lines, FEFO sale allocations, and sale completion service. |
| Medicines | `medicines` | `apps.catalog` | Medicines, categories, manufacturers, medicine units/conversions, barcodes, selling prices, and catalog status. |
| Inventory | `inventory` | `apps.inventory` | Batches, stock movements, stock counts, write-offs, adjustments, inventory alerts, discrepancy records, and the single authoritative inventory service. |
| Suppliers | `suppliers` | `apps.parties` | Supplier master data. Supplier financial statements are queried through `apps.finance`. |
| Customers | `customers` | `apps.parties` | Customer master data and walk-in-customer rules. Customer financial statements are queried through `apps.finance`. Prescriber master data also lives here. |
| Prescriptions | `prescriptions` | `apps.prescriptions` | Prescription records, items, optional attachments, and POS-linkable prescription data. |
| Purchases | `purchases` | `apps.purchasing` | Purchase orders/items, receipts, purchase invoices/items, receiving service, and purchasing status transitions. |
| Invoices | `invoices` | `apps.finance` as an aggregate navigation/query facade | Unified invoice search/status/payment view. Sales invoice records remain owned by `apps.sales`; purchase invoice records remain owned by `apps.purchasing`. The facade must not create duplicate invoice models. |
| Payments | `payments` | `apps.finance` | Customer/supplier payments, balances, statements, payment methods, pharmacist shifts, and financial reconciliation. |
| Returns & Refunds | `returns` | `apps.returns` | Customer returns, supplier returns, refund records, and orchestration across original transaction, finance, and the inventory service. This optional boundary is adopted because both return directions share the reserved navigation and cross-domain traceability requirements. |
| Reports | `reports` | `apps.reports` | Query/service-based reports and CSV/XLSX/PDF exports; no unnecessary report transaction models. |
| Settings | `settings` | `apps.core` | Pharmacy settings, practical audit records, idempotency records/keys, and shared document-numbering concerns. This cross-cutting app must remain small and must not replace `config.settings`. |
| Login/logout | `accounts` | `apps.accounts` | Existing built-in Django authentication integration and group/permission provisioning. |

`config.navigation` remains the single navigation definition. Adding a route must preserve namespace-based active state, role visibility, unresolved-link handling during development, and server-side authorization.

## 4. Stakeholders and roles

### 4.1 Project stakeholders

| Stakeholder | Interest/responsibility |
|---|---|
| Pharmacy owner/administrator | Complete operational visibility, staff access, configuration, audit, financial and inventory oversight. |
| Pharmacist | POS/cashier operation, customer interaction, prescription handling, sales documents, permitted payments/returns, own shift, and controlled physical-stock override. |
| Inventory Manager | Catalog, suppliers, purchasing operations, batches, stock control, counts, write-offs, alerts, supplier returns, and discrepancy reconciliation. |
| Accountant | Invoice/payment visibility, receivables/payables, statements, refunds, tax/discount reporting, financial reconciliation, and finance reports. |
| Pharmacy customer/patient | Receives safe medicine handling, an accurate invoice/receipt, payment/return/refund traceability, and prescription-related warnings handled by staff. The customer is not a system-login role. |
| Development team | Malik, Mhmd Hajeer, Hala, and Yasser deliver and validate the system within nine days. |

### 4.2 Authorization approach selected for Owner/Admin

**Selected approach: full Django group permissions.**

The `Owner / Admin` group must be assigned every current project model permission and every explicit non-model business permission. New business permissions added during Phase 1 must also be assigned to this group through the project's deterministic role/permission setup. A member of `Owner / Admin` does not need `is_superuser=True` to receive full business-system access.

Django superuser status is therefore not the business rule used to implement Owner/Admin access. This avoids leaving “full access” dependent on an unrelated per-user flag and keeps the exact four-group RBAC model authoritative.

### 4.3 Group permission matrix

Every listed permission must be enforced by the relevant view/action on the server. Navigation visibility is a convenience only.

| Capability | Owner / Admin | Pharmacist | Inventory Manager | Accountant |
|---|---:|---:|---:|---:|
| Full user/group/permission administration | Full | No | No | No |
| Pharmacy settings and sensitive configuration | Full | No | No | No |
| View role-aware dashboard | Yes | Yes | Yes | Yes |
| Manage medicine catalog, units, conversions, barcodes | Full | Availability lookup only | Create/view/change/deactivate | View as needed |
| View batches and availability | Full | View for POS | Full | View for valuation/reporting |
| Manual stock adjustments, counts, write-offs | Full | No unrestricted access | Full | View history only |
| Create/manage suppliers | Full | No | Full | View as needed |
| Create/select customers | Full | Basic create/select | View as needed | View for statements |
| Purchase orders and receiving | Full | No | Full operational access | Financial visibility |
| Purchase invoices | Full | No | Operational create/post | Financial visibility and permitted reconciliation |
| POS, held sales, and sale completion | Full | Full operational access | No | Financial visibility |
| Allowed sale discounts | Full | Permitted discounts | No | Report/audit visibility |
| Prescription records and warnings | Full | Full operational access | No | No unless required for invoice visibility |
| Controlled stock-discrepancy sale | Full | Create during sale | Reconcile and resolve | Financial visibility where relevant |
| Receive discrepancy alerts | Yes | Sees own warning/created record | Yes | No required alert |
| Customer payments | Full | Through permitted POS/customer workflow | No | Full permitted financial access |
| Supplier payments | Full | No | No posting unless separately granted | Full permitted financial access |
| Own pharmacist shift | Full visibility | Open/close own shift | No | View/reconcile as permitted |
| Customer returns/refunds | Full | Permitted operational workflow | Inventory effect visibility | Permitted financial reconciliation |
| Supplier returns | Full | No | Full operational workflow | Financial credit visibility/reconciliation |
| Reports and exports | Full | Operational/performance reports as permitted | Inventory/purchasing reports | Finance/tax/payment reports |
| Audit history | Full | Own/relevant operational records as permitted | Relevant inventory/purchasing records | Relevant financial records |
| Backup/restore administration | Full | No | No | No unless explicitly delegated by Owner/Admin |

The implementation may use Django's generated model permissions plus explicit custom permissions for non-CRUD actions such as posting, receiving, completing, refunding, reconciling, exporting, and viewing sensitive reports. It must preserve Django's default superuser behavior without relying on superuser status for the Owner/Admin business role.

## 5. Functional requirements grouped by domain

All requirements in this section are mandatory unless the text explicitly says “where reasonably achievable” or “where applicable,” matching the source documents.

### 5.1 Medicine catalog and parties

#### Medicine catalog

- **BRD-CAT-001:** The system shall manage medicines with a UUID business identifier, brand/name, optional generic name, category, manufacturer, optional strength, optional dosage form, prescription-required flag, low-stock threshold, default selling price, and active/inactive state.
- **BRD-CAT-002:** The system shall preserve price changes where required for auditability and shall snapshot the price used by a posted transaction.
- **BRD-CAT-003:** A medicine with transaction history shall be deactivated rather than hard-deleted.
- **BRD-CAT-004:** The system shall manage active/inactive categories and manufacturers.
- **BRD-CAT-005:** Each medicine shall support one or more units with unit name, conversion factor to the base unit, base-unit flag, purchase-allowed flag, sale-allowed flag, and active state.
- **BRD-CAT-006:** Each medicine shall have exactly one base unit; its conversion factor shall equal 1; every conversion factor shall be greater than zero.
- **BRD-CAT-007:** Posted transactions shall preserve the unit and conversion factor applied at posting time.
- **BRD-CAT-008:** A medicine unit may have active barcodes. Every barcode shall be unique and shall resolve to exactly one medicine/unit combination.

#### Suppliers, customers, and prescribers

- **BRD-PTY-001:** A supplier shall support a unique code, name, contact person, phone, email, address, notes, and active state.
- **BRD-PTY-002:** A customer shall support a unique code, name, phone, email, address, notes, and active state.
- **BRD-PTY-003:** A sale shall support a saved customer or a walk-in customer without requiring a Customer row.
- **BRD-PTY-004:** A prescriber shall support a name, optional phone, optional professional/reference identifier, notes, and active state.
- **BRD-PTY-005:** Master records with transaction history shall be deactivated rather than hard-deleted.

### 5.2 Inventory and batches

#### Batch records and availability

- **BRD-INV-001:** Inventory shall be batch-aware. One medicine may have multiple batches with different batch numbers, expiry dates, acquisition costs, and available quantities.
- **BRD-INV-002:** A medicine batch shall record its medicine, batch number, required expiry date, acquisition cost per base unit, quantity available in base units, and received timestamp/reference.
- **BRD-INV-003:** Batch acquisition cost shall be non-negative and is mandatory for received stock.
- **BRD-INV-004:** Expired batches shall never be eligible for sale, including during a stock-discrepancy override.
- **BRD-INV-005:** Normal inventory workflows shall not create negative stock. The controlled physical-stock discrepancy sale is the only approved exception.
- **BRD-INV-006:** Shelf, bin, and physical-location tracking shall not be implemented.

#### Authoritative stock movements

- **BRD-INV-007:** Every stock-changing workflow shall create append-style stock-movement history and shall not update an editable stock quantity without the corresponding movement.
- **BRD-INV-008:** A stock movement shall identify the medicine, batch where known, signed base-unit quantity, movement type, source transaction type/reference, actor, timestamp, and reason where applicable.
- **BRD-INV-009:** Movement types shall distinguish purchase receipt, sale, customer-return restock, supplier return, expiry write-off, damage write-off, loss write-off, manual adjustment, and stock-count adjustment.
- **BRD-INV-010:** Completed stock history shall not be hard-deleted or silently rewritten.

#### FEFO and physical batch handling

- **BRD-INV-011:** FEFO eligibility shall include only batches for the medicine that are non-expired on the pharmacy's local date and have recorded usable stock greater than zero.
- **BRD-INV-012:** Eligible batches shall be ordered by earliest expiry date, then earliest receipt/creation order for deterministic allocation.
- **BRD-INV-013:** If the first batch cannot satisfy the requested base quantity, allocation shall continue across later eligible batches. One sales line may therefore have multiple batch allocations.
- **BRD-INV-014:** The POS shall display the recommended batch and allow the Pharmacist to record a different actual valid batch.
- **BRD-INV-015:** Selecting a newer valid batch while an older valid batch remains shall produce a lightweight warning, allow continuation without manager approval, and record recommended batch, actual batch, actor, timestamp, and optional reason/note for audit.

#### Counts, adjustments, write-offs, and alerts

- **BRD-INV-016:** A stock count shall record its date/status, actor, and lines containing medicine, batch, system quantity, counted quantity, and variance.
- **BRD-INV-017:** Reconciling a non-zero count variance shall create an inventory movement and preserve the count history.
- **BRD-INV-018:** Expired, damaged, and lost stock write-offs shall require an exact batch and reason, create a movement, and preserve batch/history records.
- **BRD-INV-019:** Manual stock adjustment shall require authorization, reason, actor, timestamp, exact affected stock, and a movement record.
- **BRD-INV-020:** The system shall expose queryable/visible low-stock, out-of-stock, near-expiry, expired-stock, and stock-discrepancy alerts to the relevant roles.

#### Single inventory-service ownership rule

- **BRD-INV-021:** `apps.inventory` shall own the authoritative services that allocate, increase, decrease, restore, adjust, write off, count, and reconcile stock.
- **BRD-INV-022:** Purchasing, sales, returns, finance, reports, and other apps shall call those inventory services and shall not implement independent stock arithmetic or directly mutate batch quantities.

### 5.3 Purchasing

#### Purchase orders

- **BRD-PUR-001:** The system shall support lightweight purchase orders with a unique number/reference, supplier, date, status, notes, and items.
- **BRD-PUR-002:** A purchase-order item shall record the medicine, purchase unit, ordered quantity, expected unit cost, discount, tax, and received quantity/remaining quantity.
- **BRD-PUR-003:** Purchase-order status shall support the business meaning of draft, submitted, partially received, received, closed, and cancelled while keeping transitions simple.
- **BRD-PUR-004:** Multi-level enterprise approval is not required.

#### Partial/full receiving

- **BRD-PUR-005:** The system shall receive a purchase order partially or fully through a receipt/goods-receipt record linked to the order and supplier, received-by user, received date, posted state, and receipt lines.
- **BRD-PUR-006:** Each receipt line shall identify its purchase-order item, medicine, unit, received quantity, batch number, expiry date, and actual purchase/acquisition cost.
- **BRD-PUR-007:** Posting a receipt shall atomically validate the remaining order quantity, batch data, expiry, and acquisition cost; create or update the appropriate batch; increase base-unit availability through the inventory service; create the stock movement; update received quantity; and update purchase-order status.
- **BRD-PUR-008:** A held/draft receipt shall not increase stock until it is posted.

#### Purchase invoices and supplier returns

- **BRD-PUR-009:** A purchase invoice shall record a unique internal invoice number, supplier, optional supplier invoice reference, invoice date, optional due date, items, subtotal, total discount, total tax, grand total, paid total, remaining balance, payment status, and posted/completed state.
- **BRD-PUR-010:** A purchase-invoice item shall snapshot medicine, unit, quantity, unit cost, discount, tax, line total, and batch/receipt reference where appropriate.
- **BRD-PUR-011:** Posted purchase invoices shall not be silently edited or hard-deleted; cancellation/reversal behavior shall preserve history.
- **BRD-PUR-012:** Supplier returns shall reference the supplier and purchase where appropriate, exact medicine batch, returned quantity, reason, and value; posting shall reduce the exact batch through the inventory service, create a movement, reflect supplier credit/balance where applicable, and preserve traceability.

### 5.4 POS and sales

#### Barcode and sale preparation

- **BRD-SAL-001:** The POS shall support medicine search and common keyboard/HID barcode scanners that type into a barcode input and may submit with Enter.
- **BRD-SAL-002:** A known unique barcode shall identify its medicine/unit. An unknown barcode shall not create a medicine automatically, and manual medicine search shall remain available.
- **BRD-SAL-003:** The Pharmacist shall be able to select a unit, enter quantity, see available stock and relevant expiry warnings, add multiple medicines, apply permitted discounts, calculate tax, select/create a saved customer when permitted, use walk-in customer context, and associate a prescription.
- **BRD-SAL-004:** The POS shall support hold/suspend and resume. Holding a sale shall not permanently allocate or deduct inventory.
- **BRD-SAL-005:** The browser may display previews, but the server shall recalculate and authorize units, quantities, FEFO allocation, prices, discounts, taxes, totals, payment, and completion.

#### Sale completion

- **BRD-SAL-006:** Completing a sale shall be an atomic, idempotent posting workflow.
- **BRD-SAL-007:** Completion shall verify user permission and sale state; validate lines, units, quantities, and prescription warnings; convert quantities to base units; calculate authoritative FEFO allocation; reject expired batches; process valid actual-batch deviation; and detect recorded-stock shortfall.
- **BRD-SAL-008:** Completion shall calculate authoritative prices, permitted discounts, and taxes; create final invoice lines with historical snapshots; create actual batch allocations and acquisition-cost snapshots; create stock movements; update batch quantities through the inventory service; create discrepancy records/alerts where applicable; create initial payment records; calculate remaining balance; generate a unique invoice number; mark the sale completed; and expose the printable invoice/receipt.
- **BRD-SAL-009:** Repeating the same completion submission shall return/reuse the already-posted business result or reject the duplicate without creating another invoice, payment, allocation, movement, or discrepancy.

#### Sales invoice and line snapshots

- **BRD-SAL-010:** A sales invoice shall record a unique invoice number, optional customer, Pharmacist, date/time, status, items, subtotal, total discount, total tax, grand total, paid total, and balance due.
- **BRD-SAL-011:** A sales line shall snapshot medicine description, unit, quantity, conversion factor, selling price, discount, tax rate/amount, line total, and prescription-required acknowledgment where needed.
- **BRD-SAL-012:** Each batch allocation shall identify the sales line, actual batch, allocated base quantity, acquisition-cost snapshot, and FEFO recommendation/override metadata.
- **BRD-SAL-013:** Completed sales and invoices shall not be silently edited or hard-deleted. Voids/reversals shall remain traceable.

#### Minimal controlled stock-discrepancy override

- **BRD-SAL-014 (trigger):** The discrepancy workflow is available only when the system's recorded usable stock is insufficient for the requested sale but the Pharmacist confirms that the required medicine is physically present and non-expired.
- **BRD-SAL-015 (warning):** The POS shall clearly warn that recorded stock is insufficient, show the recorded available quantity, and state that the override will be audited and flagged for reconciliation.
- **BRD-SAL-016 (acknowledgment):** The Pharmacist shall explicitly acknowledge the override and select a reason: `physical stock present / system mismatch`, `batch quantity mismatch`, or `other`. `Other` requires a note.
- **BRD-SAL-017 (evidence):** The discrepancy shall record the linked sales invoice and line, medicine, requested quantity, recorded available quantity, actual/observed batch if known, observed batch number/expiry where useful, actor, timestamp, reason code, optional note, and open/resolved status with resolution details.
- **BRD-SAL-018 (completion):** After valid acknowledgment, the non-expired sale may complete through the normal atomic posting workflow. The discrepancy is linked to the sale and its stock movement/allocation; expired medicine remains absolutely blocked.
- **BRD-SAL-019 (audit/alert):** Creation shall append an audit record and create an actionable alert visible to every applicable `Owner / Admin` user and the `Inventory Manager` group.
- **BRD-SAL-020 (later reconciliation):** An authorized Inventory Manager or Owner/Admin may resolve the discrepancy through a stock adjustment, stock count, or documented no-change resolution. Reconciliation shall preserve the original sale and discrepancy history.
- **BRD-SAL-021 (scope boundary):** Phase 1 shall not add investigation assignments, escalations, SLA timers, threaded case comments, approval chains, or a separate enterprise discrepancy subsystem.

### 5.5 Prescriptions

- **BRD-PRE-001:** The system shall support prescription records with optional customer, prescriber/doctor information, prescription date, notes, optional attachment/image where reasonably achievable, and status where appropriate.
- **BRD-PRE-002:** Prescription items shall record medicine, prescribed quantity where applicable, dosage/instructions, and notes.
- **BRD-PRE-003:** A medicine marked prescription-required shall produce a lightweight POS warning and require Pharmacist acknowledgment; the flag alone shall not hard-block the sale.
- **BRD-PRE-004:** Prescription behavior shall not perform clinical decision-making or provide medical advice.
- **BRD-PRE-005:** Prescription warnings shall never override the independent rule that expired batches cannot be sold.

### 5.6 Finance, payments, balances, shifts, discounts, and taxes

#### Customer and supplier payments

- **BRD-FIN-001:** Payments shall be separate records from invoices. An invoice shall represent unpaid, partially paid, or fully paid state based on active payment history.
- **BRD-FIN-002:** A customer payment shall identify the sales invoice, optional saved customer context, payment method, amount, reference, timestamp, and actor.
- **BRD-FIN-003:** A supplier payment shall identify the purchase invoice, supplier, payment method, amount, external/reference value where relevant, timestamp, and actor.
- **BRD-FIN-004:** Payment methods shall include cash, card, bank transfer, and other configured methods.
- **BRD-FIN-005:** Payments shall be positive, may be partial, and may be multiple. Active payments shall not exceed the payable balance unless the transaction explicitly represents an approved credit/refund.
- **BRD-FIN-006:** Posting or reversing a payment shall recalculate paid total, remaining balance, and payment state without rewriting payment history.
- **BRD-FIN-007:** A walk-in sale shall normally be fully settled because it has no saved customer account. Partial/unpaid balances are supported for saved customers.
- **BRD-FIN-008:** Customer statements shall show invoices, payments, returns/refunds/credits, and current balance. Supplier statements shall show purchase invoices, supplier returns/credits, payments, and current balance.
- **BRD-FIN-009:** Payment posting shall be idempotent so a retry cannot create a duplicate payment or alter the balance twice.

#### Pharmacist/cashier shifts

- **BRD-FIN-010:** The Pharmacist acting as cashier shall open a shift with opening time and opening cash and close it with closing time, expected cash, actual cash, discrepancy, and closing note.
- **BRD-FIN-011:** One user shall not have more than one simultaneous open shift.
- **BRD-FIN-012:** Expected cash shall account for cash sale receipts and cash refunds, plus explicit approved cash-in/out only if that optional movement is implemented.
- **BRD-FIN-013:** Closing shall calculate and display expected versus actual cash and preserve any discrepancy and shift history.
- **BRD-FIN-014:** Shift handling shall remain lightweight and shall not add a separate Cashier role or enterprise cash-management subsystem.

#### Discounts, taxes, cost, and profit

- **BRD-FIN-015:** Applicable sales and purchase workflows shall calculate discounts and taxes on the server using Decimal arithmetic, never floating-point arithmetic.
- **BRD-FIN-016:** A line total shall be derived from quantity multiplied by unit price/cost, minus permitted discount, plus tax applied to the configured taxable amount. Document totals shall be derived from authoritative line values and configured document-level adjustments.
- **BRD-FIN-017:** Posted documents shall preserve price/cost, discount, tax, unit, and conversion snapshots so later configuration changes do not change historical output.
- **BRD-FIN-018:** Each sales allocation shall preserve batch acquisition cost. COGS equals allocated base quantity multiplied by its acquisition-cost snapshot; gross profit equals sales revenue excluding tax minus COGS.
- **BRD-FIN-019:** If a controlled discrepancy sale lacks authoritative acquisition cost, reporting shall flag unresolved cost rather than assume zero until reconciliation.
- **BRD-FIN-020:** Phase 1 shall not implement full double-entry accounting or a general ledger.

### 5.7 Returns and refunds

#### Customer return/refund

- **BRD-RET-001:** A customer return shall reference an original completed sale and identify the original item, returned quantity, reason, condition/safety, refund amount, and related actor/time.
- **BRD-RET-002:** Return quantity shall be greater than zero, and cumulative returned quantity shall not exceed the original sold quantity.
- **BRD-RET-003:** The original batch allocation shall be identified where possible. A safe/resellable item shall be restored through the inventory service to the correct original batch.
- **BRD-RET-004:** Expired, damaged, unsafe, or otherwise non-resellable returned medicine shall not enter sellable inventory.
- **BRD-RET-005:** A refund shall remain linked to the return and original invoice, preserve amount and payment method, and shall not exceed the eligible refundable value.
- **BRD-RET-006:** Return/refund posting shall be atomic and idempotent and shall preserve the original posted transaction.

#### Supplier return

- **BRD-RET-007:** A supplier return shall record supplier, purchase reference where appropriate, medicine, exact batch, returned quantity, reason, and value.
- **BRD-RET-008:** Posting shall reduce the exact batch through the inventory service, create a stock movement, reflect the supplier credit/balance where applicable, and preserve traceability.
- **BRD-RET-009:** Supplier-return posting shall be atomic and idempotent.

### 5.8 Invoices, receipts, and document output

- **BRD-DOC-001:** Invoice and receipt quality is a top-priority acceptance area.
- **BRD-DOC-002:** The system shall generate unique internal numbers for posted sales invoices, sales receipts, purchase invoices, payment receipts/history, returns, and refunds as applicable.
- **BRD-DOC-003:** A sales invoice/receipt shall show pharmacy identity/contact, invoice number, date/time, Pharmacist, selected customer where present, medicine description, unit, quantity, unit price, discount, tax, line total, subtotal, total discounts, total tax, grand total, payment breakdown, paid amount, remaining balance, status, and return/refund references where applicable.
- **BRD-DOC-004:** A purchase invoice shall show pharmacy identity, supplier identity, internal invoice number, supplier reference where present, date, medicine/unit, quantity, cost, discount, tax, totals, and payment/balance state.
- **BRD-DOC-005:** Historical output shall be generated from stored transaction snapshots rather than current catalog/settings values.
- **BRD-DOC-006:** Documents shall have clean, professional, consistent, print-friendly HTML. PDF shall be provided where reasonably achievable with the current project.
- **BRD-DOC-007:** Retrying a numbering/posting request shall not consume a second business number or create a duplicate posted document.
- **BRD-DOC-008:** Visual styling remains under Mhmd Hajeer's UI/UX ownership; completeness, clarity, printability, safety warnings, accessibility, and permission behavior are mandatory.

### 5.9 Dashboard, reports, and exports

- **BRD-RPT-001:** The system shall use one dashboard architecture with role-aware widgets/content rather than separate dashboard applications per role.
- **BRD-RPT-002:** Reports shall cover sales, purchases, gross profit/COGS, current inventory, inventory valuation, low stock, out of stock, near-expiry medicine, expired stock, customer receivables, supplier payables, customer payments, supplier payments, discounts, taxes, best-selling medicines, Pharmacist/cashier performance, and shift discrepancy.
- **BRD-RPT-003:** Reports shall use authoritative transactional queries/services and shall not create unnecessary report transaction models.
- **BRD-RPT-004:** Batch-specific acquisition-cost snapshots shall feed COGS, gross-profit, and valuation results.
- **BRD-RPT-005:** Important reports shall support CSV and XLSX export and PDF where applicable.
- **BRD-RPT-006:** Report visibility and export permission shall follow the role matrix and protect sensitive financial information.

### 5.10 System settings and backup

- **BRD-SET-001:** Authorized Owner/Admin users shall configure pharmacy identity/contact/address, currency, taxes, payment methods, invoice/receipt information, expiry-warning threshold, and low-stock defaults.
- **BRD-SET-002:** Settings changes shall be audited and shall not retrospectively change posted document snapshots.
- **BRD-SET-003:** Secrets and credentials shall remain outside Git and shall not be exposed in settings screens or audit metadata.
- **BRD-SET-004:** The project shall document a PostgreSQL/Neon backup strategy and complete a tested restore procedure before final delivery.
- **BRD-SET-005:** Backup/restore implementation shall remain realistic for the nine-day project.

### 5.11 RBAC, security, audit, idempotency, and concurrency

#### Authentication and authorization

- **BRD-SEC-001:** The system shall preserve the existing Django 6.1 built-in User, username/password login, session authentication, login/logout pages, and POST/CSRF-protected logout flow.
- **BRD-SEC-002:** The system shall use only the exact business groups `Owner / Admin`, `Pharmacist`, `Inventory Manager`, and `Accountant`.
- **BRD-SEC-003:** Every protected view and business action shall enforce authentication and required Django permissions server-side. Hiding a navigation link shall not authorize or secure an action.
- **BRD-SEC-004:** The `Owner / Admin` group shall receive all model and explicit business permissions through deterministic permission provisioning. The business role shall not depend on `is_superuser`.
- **BRD-SEC-005:** Authentication, authorization, user/permission changes, and shared authentication UI changes shall preserve the existing foundation and be coordinated with Mhmd Hajeer.

#### Application security and data integrity

- **BRD-SEC-006:** The application shall preserve Django CSRF protection and template escaping, validate uploaded prescription files safely, keep secrets in environment/configuration rather than Git, and use the ORM or parameterized SQL.
- **BRD-SEC-007:** The server shall calculate and validate authoritative stock and financial values and shall not trust browser calculations or stale previews.
- **BRD-SEC-008:** Posted financial, inventory, payment, return/refund, shift, and audit history shall not be hard-deleted or silently rewritten.
- **BRD-SEC-009:** Critical multi-record workflows shall use `transaction.atomic()`.

#### Practical append-only audit

- **BRD-AUD-001:** Audit records shall be append-only from the application UI and shall record actor, action code, affected entity/reference, timestamp, and reason/context or before/after metadata where useful.
- **BRD-AUD-002:** Audit coverage shall include user/permission changes, price changes, stock adjustments/write-offs, purchase receiving, purchase-invoice posting, sale completion, invoice void/cancellation, discount, FEFO deviation, controlled discrepancy override and resolution, payment/reversal, refund, customer/supplier return, shift close/discrepancy, and settings changes.
- **BRD-AUD-003:** Audit history shall have no hard-delete UI.
- **BRD-AUD-004:** Phase 1 shall not implement cryptographic chaining, event sourcing, or a separate enterprise audit platform.

#### Bounded idempotency

- **BRD-IDM-001:** Critical posting actions shall accept or derive a stable submission identity sufficient to recognize a retry of the same business operation.
- **BRD-IDM-002:** The protected actions are sale completion, purchase receipt posting, purchase-invoice posting, customer/supplier payment posting, customer return/refund posting, supplier-return posting, stock count/adjustment reconciliation, and other document posting that changes stock or financial state.
- **BRD-IDM-003:** A recognized retry shall not create duplicate business records, numbering, payments, allocations, stock movements, audit entries, or alerts. It shall return/reuse the original result or report that the operation was already posted.
- **BRD-IDM-004:** Idempotency data shall be scoped to the operation/user or business context, shall not weaken permission checks, and shall be stored and checked inside the same transaction as the protected posting.
- **BRD-IDM-005:** Phase 1 shall not add a distributed idempotency service or unrelated infrastructure.

#### Concurrency

- **BRD-CON-001:** Stock-changing sale, receipt, return, and reconciliation workflows shall re-read authoritative stock inside the transaction and lock affected batch rows when needed.
- **BRD-CON-002:** If stock changes after a browser preview and before posting, the server shall recompute FEFO and either surface a conflict or offer the controlled discrepancy path when its physical-stock conditions are satisfied.
- **BRD-CON-003:** Concurrency controls shall focus on affected stock and transaction rows and shall not introduce complex locking everywhere.

## 6. Non-functional requirements

### 6.1 Security and privacy

- The application shall use the existing Django session/CSRF/authentication foundation and enforce least-privilege group/model/business permissions.
- Secrets, Neon credentials, passwords, keys, production data, and secret-bearing logs shall not be committed to Git or exposed in generated documents.
- Uploaded prescription files shall be validated for permitted type/size and served only to authorized users.
- Django template escaping and ORM/parameterized queries shall be preserved.
- Security-relevant user, permission, settings, stock, financial, and posting operations shall be audited.

### 6.2 Auditability and traceability

- Posted records shall preserve historical snapshots and relationships to their source transactions.
- Stock shall be traceable from each batch change to its source record, actor, time, and reason.
- Payments, returns, refunds, discrepancies, shifts, and reversals shall remain traceable to the affected invoice or transaction.
- Audit and posted transaction history shall be append-style and unavailable for hard deletion through the normal UI.
- Unknown acquisition cost in a discrepancy shall remain visibly unresolved rather than distort COGS/profit.

### 6.3 Transaction integrity and concurrency

- Critical workflows shall be atomic and idempotent.
- A failed multi-record workflow shall leave no partial invoice, payment, allocation, stock movement, alert, or balance update.
- Concurrent stock-changing operations shall validate current authoritative rows at posting time and use targeted locking where required.
- Financial and quantity arithmetic shall use Decimal-compatible database fields and server-side calculations.

### 6.4 Performance and operability

- POS barcode lookup, medicine search, FEFO allocation, and sale completion shall remain practical for an active pharmacy workflow.
- Reports shall primarily use query/service calculations over transactional data rather than unnecessary report models.
- The implementation shall avoid unnecessary frameworks, services, and abstractions that would increase delivery or operational risk.
- No numeric response-time, throughput, or availability target is specified by the source documents; Phase 1 shall not invent one.

### 6.5 Usability and accessibility

- Workflow screens shall expose the information required to complete the action, understand warnings, submit mandatory evidence, print documents, and understand status/balance.
- Required warnings—expired stock, FEFO deviation, prescription-required medicine, and controlled stock discrepancy—shall be clear and distinguish blocking from non-blocking behavior.
- Barcode input shall work with common keyboard/HID scanners while manual medicine search remains available.
- Existing accessible shared component behavior and server-side validation feedback shall be preserved.
- Visual colors, layout, typography, spacing, and exact component composition remain under Mhmd Hajeer's ownership and are not frozen by this BRD.

### 6.6 Reliability, backup, and recovery

- Posted operations shall be protected from duplicate submission and partial failure.
- The project shall document the Neon/PostgreSQL backup procedure and execute a restore test before final delivery.
- Backup credentials and artifacts containing production data shall be protected and kept outside Git.

### 6.7 Maintainability and validation

- The application shall remain a modular monolith using existing Django, Tailwind, vanilla JavaScript, `uv`, and npm conventions.
- Each business model and workflow shall have one owning app; cross-app consumers shall use agreed services/queries rather than duplicate rules.
- Tests shall cover allowed/denied/anonymous authorization; catalog units/barcodes/conversions; purchase-order partial/full receiving; stock movements/counts/write-offs/alerts; barcode POS, FEFO, multi-batch allocation, expired-batch blocking, deviations, held sales, walk-in and partial-payment sales; controlled discrepancy audit/alerts/reconciliation; customer/supplier payments and balances; returns/refund limits and correct restocking; invoice totals/snapshots; COGS/profit; reports and exports; idempotent retries; and relevant concurrency conflicts.
- Dependencies shall be added only when necessary and through the existing dependency managers.

## 7. Assumptions and constraints

### 7.1 Delivery and team constraints

- The total project window is nine days, and every Phase 1 requirement in this BRD is mandatory.
- The team consists of Malik, Mhmd Hajeer, Hala, and Yasser.
- Mhmd Hajeer owns authentication-related changes, UI/UX, visual design, and shared layout/design integration. Other contributors shall make only the smallest necessary coordinated change in those areas.
- Malik and Mhmd Hajeer use Codex. Task plans for Hala and Yasser must explicitly list the repository documents and task-specific files they must attach to their AI assistant; team handoffs shall not rely on hidden AI memory.
- Work shall be split into small mergeable tasks, integrated early, and shall avoid risky late-stage architectural rewrites.
- Any Phase 2 or Phase 3 work attempted during the same nine days must deliver real user value without endangering Phase 1 completion.

### 7.2 Product and architecture constraints

- The system supports one pharmacy; multi-branch behavior is not modeled.
- Django 6.1 and the current full-stack repository foundation are fixed for Phase 1.
- The built-in Django User model, username/password login, sessions, and current login/logout flow are fixed.
- The four exact Django Groups are fixed. The Pharmacist performs cashier duties.
- `Owner / Admin` full access is implemented through full group permissions, not by requiring Django superuser status.
- PostgreSQL is hosted on Neon. Credentials and environment configuration remain outside Git.
- The application remains server-rendered and same-origin; it shall not become DRF-only or a separate SPA.
- Tailwind CSS v4, vanilla JavaScript, `uv`, npm, the `apps/` layout, root shared templates, and existing shared components/navigation are preserved.
- UI/UX visual choices are not frozen, but correctness, safety, authorization, accessibility, required warnings, barcode behavior, and document completeness are fixed.

### 7.3 Data and workflow constraints

- New business records use UUID primary keys where compatible with the existing schema.
- Money uses Decimal fields; unit prices/costs use four decimal places where required, posted totals/payments use two decimal places, and quantities support three decimal places, consistent with the technical specification.
- Time values use timezone-aware Django datetimes. FEFO expiry uses the configured pharmacy local date.
- Master data with history is deactivated rather than hard-deleted. Posted transactions, stock movements, payments, shifts, returns/refunds, discrepancies, and audit history remain traceable.
- Payments remain separate from invoices.
- Batch-specific acquisition cost is mandatory and feeds COGS, profit, and valuation.
- Expired batches can never be sold or restored to sellable stock.
- Prescription-required status creates a lightweight warning rather than an automatic sale block.
- A physical-stock discrepancy may override recorded shortage only through the minimal workflow in BRD-SAL-014 through BRD-SAL-021.
- Purchase orders and shift reconciliation are required but lightweight.
- Idempotency and audit coverage are required in their bounded Phase 1 forms; enterprise platforms are not.

### 7.4 One-inventory-service ownership constraint

`apps.inventory` is the sole owner of stock mutation and batch-allocation rules. At minimum, its service boundary shall cover receipt, FEFO allocation, sale consumption, safe customer-return restoration, supplier return, write-off, manual adjustment, stock-count reconciliation, discrepancy reconciliation, and authoritative movement creation.

No sales, purchasing, returns, finance, reports, or UI code may independently change a batch quantity or create an alternative stock ledger. Cross-domain workflows must call the inventory service inside their transaction boundary and preserve the source transaction reference.

### 7.5 Source and implementation constraints

- This BRD does not authorize implementation by itself. Model fields, migrations, and code changes shall follow the repository's own AI/development instructions and an approved ERD/task plan.
- Before implementation, agents must inspect the actual repository, existing models/migrations, settings, permissions, templates, shared components, and relevant tests.
- The repository wins over a conflicting proposed architecture. A newer task-specific decision may supersede this BRD only when it explicitly records a later team decision.
- No requirement may be silently removed, mocked, deferred, or expanded beyond the boundaries recorded here.
