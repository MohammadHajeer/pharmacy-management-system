# Sales / POS UI handoff

## Service contracts preserved

- Existing JSON medicine lookup searches active sale medicines by name, generic name or strength. The UI requests at most 12 results. Exact active barcodes resolve a `MedicineBarcode` belonging to a `MedicineUnit`, selecting that exact unit.
- The draft service creates or replaces the entire line set; removal submits the remaining contiguous formset. It requires at least one line. Drafts do not reserve or mutate stock.
- Catalog helpers remain responsible for unit conversion and selected-unit price. The Sales service computes rounded line discounts, default tax and totals, and persists snapshots. No JavaScript financial or stock arithmetic was added.
- Customer `NULL` means walk-in, without a synthetic Customer row. An existing prescription may be linked; each prescription-required line must separately acknowledge its warning before completion.
- Completion locks the invoice, validates its current state, then delegates batch locks, FEFO deductions and matching movements to Inventory. Initial payments delegate to Finance in the same atomic transaction. Failures roll back together.
- Walk-ins require full settlement (except zero-total sales). Saved customers may complete unpaid or partially paid. Finance owns reference requirements, positive amounts, overpayment validation and payment-only balances.
- The invoice number is assigned by the existing completion service (`SAL-` plus uppercase UUID hex). The stored pharmacist is the draft creator; the UI does not invent a separate “completed by” audit field.

## Approved integration fixes

`pos_sale_complete` now catches **only** the known Inventory `InsufficientStockError` alongside the pre-existing Django `ValidationError` handling. Stock shortages return HTTP 400 with `errors.__all__` containing the service message. Unexpected exceptions still propagate. The UI displays messages with text nodes, preserves draft/payment input and does not retry automatically.

SQLite's aggregate Decimal representation may be `Decimal('10')`, while PostgreSQL preserves a `10.000` exponent. Both values are semantically equal. The medicine JSON serializer now uses `.3f` formatting for `available_stock_base`; no Decimal calculations, scale, model, inventory query or service test was changed.

## Screens and routes

| Route name | Purpose |
| --- | --- |
| `sales:pos` | New checkout workspace; GET and CSRF-protected draft POST |
| `sales:pos-workspace` | View/edit an existing draft; completed/void records redirect to invoice detail |
| `sales:invoice-list` | Paginated transaction registry |
| `sales:invoice-detail` | Read-only transaction document and optional authorized allocation trace |
| `sales:invoice-print` | Printable HTML invoice; `?format=receipt` selects the narrow receipt layout |

Existing lookup, draft JSON and completion routes remain available. The main UI uses native Django draft forms and the existing JSON lookup/completion endpoints; no API framework or new dependency was introduced.

The desktop POS places products on the left and the summary/payment workspace on the right. Smaller screens stack the same controls. Save & review refreshes authoritative totals. Any unsaved edit disables completion and labels totals as last-saved. Scanner Enter is explicitly handled; Alt+/ focuses medicine search. Lookup failures are announced, and stale search responses are discarded. A completion timeout or unconfirmed response requires checking the invoice/reloading before retrying, to avoid accidental double submission.

The registry searches invoice numbers and customer names and filters by document status, payment status and completion period (today / 7 / 30 days). It uses the shared 350 ms debounce, immediate select navigation, page reset and filter-preserving 25-row pagination. Ordering is descending `Coalesce(completed_at, created_at)`, then descending UUID. Sales and Invoices sidebar states match distinct route names.

Invoice/receipt lines and totals use historical snapshots. Pharmacy identity uses its stored snapshot; additional contact/header/footer text uses current `PharmacySettings`. Print CSS removes controls, keeps numeric data readable and repeats invoice table headings. PDF generation and physical printer integration are not required.

## Permissions

- New workspace, registry and lookup require `sales.view_salesinvoice`.
- Existing workspace, invoice detail and print additionally require `sales.view_salesinvoiceline`.
- Creating/editing drafts retains both invoice and line add/change permissions respectively, enforced by the view and service.
- Completion retains `sales.complete_sale`; initial payment retains `finance.post_customerpayment`.
- Allocation traces require `sales.view_salebatchallocation`; acquisition costs are not exposed.
- Record payment appears only on completed saved-customer invoices with a positive balance and `finance.post_customerpayment`, linking to `finance:customer-payment-record`. Payment history separately requires `finance.view_customerpayment`.

## Verification

Use an explicitly isolated database, never the default `.env` target:

```powershell
$env:DATABASE_URL = 'sqlite:///:memory:'
uv run manage.py check
uv run manage.py test apps.sales apps.inventory apps.finance apps.prescriptions apps.dashboard --noinput
npm run build:css
node --test apps/sales/tests_js/*.test.cjs apps/dashboard/tests_js/*.test.cjs
git diff --check
```

For repeatable browser review, `uv run python scripts/preview-sales.py` starts port 8017 with an in-memory SQLite test database and synthetic existing test fixtures. It prints a random, process-local login. It explicitly overrides database settings and never runs `seed_demo_data`. Stop the server to discard all preview data. Template edits are visible after reload; Python edits require a restart.

Automated coverage includes known stock errors/rollback, unexpected exceptions, successful completion, draft create/update/remove, input preservation, customer/prescription handling, references/overpayment, permissions, allocation/Finance visibility, print/receipt output, filters, pagination and exclusive navigation. Existing service tests remain untouched. JavaScript tests cover scanner Enter, composition/repeat behavior, line reindexing, decimal display and completion disabling.

SQLite cannot prove PostgreSQL row-lock behavior. The existing Sales concurrency test is skipped there; the existing Finance concurrent-payment test may emit SQLite table-lock thread errors even when the runner reports success. PostgreSQL concurrency verification remains a separate integration gate.

Final local run: Django system check passed; Sales alone ran 39 tests (38 passed, one PostgreSQL-only skip). The combined Sales, Inventory, Finance, Prescriptions and Dashboard run attempted 199 tests: 197 passed, one skipped, and the existing `ConcurrentCustomerPaymentTests.test_two_full_balance_payments_cannot_both_post` failed with SQLite table-lock errors. No Finance service/test workaround was applied. CSS build, both JavaScript syntax checks, 39 JavaScript tests, and `git diff --check` passed.

Browser review uses only synthetic data: name/generic/barcode lookup, unknown barcode, add/remove/unit/quantity edits, saved and walk-in customers, prescription association/acknowledgment, insufficient stock and correction, cash/card completion, invoice/receipt pages, Finance entry link, registry pagination/filter reset, and desktop/mobile layouts. Physical printing is not claimed.

## Intentionally not exposed

No void action (there is no supporting Sales void service), manual batch selection, stock overrides, camera scanning, held-sale subsystem, clinical advice, duplicate Finance posting, PDF dependency, schema changes or production data writes.

## File inventory

Modified: `apps/sales/views.py`, `apps/sales/urls.py`, `config/navigation.py`, `apps/dashboard/tests.py`, `docs/COMPONENTS.md`.

Created: this handoff; `apps/sales/test_views.py`; `apps/sales/tests_js/pos.test.cjs`; `scripts/preview-sales.py`; `apps/sales/static/sales/{pos.js,print.js,print.css}`; `apps/sales/templates/sales/{pos.html,_pos_line.html,_totals.html,invoice_list.html,_invoice_filters.html,_payment_badge.html,_status_badge.html,_invoice_lines.html,invoice_detail.html,invoice_print.html}`.

Suggested commit: `feat(sales): deliver POS checkout and invoice workspace`.
