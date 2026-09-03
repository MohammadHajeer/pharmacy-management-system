# Phase 1 Finance workspace

The existing `CustomerPaymentForm`, `SupplierPaymentForm`, and
`PaymentReversalForm` remain the input-validation contract. The four
`post_customer_payment`, `post_supplier_payment`, `reverse_customer_payment`,
and `reverse_supplier_payment` services are the only mutation paths. No model,
migration, service, or existing backend test was changed for the UI.

## Routes and permissions

All routes are under `/finance/` in the `finance` namespace. For both `customer`
and `supplier`, route names use these suffixes:

| Route suffix | Purpose | Required finance permission |
| --- | --- | --- |
| `payment-list` | Payment registry | `view_customerpayment` / `view_supplierpayment` |
| `payment-create` | Paginated eligible-invoice selector | `post_customerpayment` / `post_supplierpayment` |
| `payment-record` | GET entry form / POST immediate posting for an invoice | Corresponding `post_*` |
| `payment-detail` | Original transaction and reversal metadata | Corresponding `view_*` |
| `payment-reverse` | POST-only reversal | Corresponding `post_*` |
| `invoice-detail` | Invoice financial context and payment history | Corresponding `view_*` |

The `finance:payment-list` landing route requires either payment-view permission.
It directs supplier-only viewers to Supplier Payments. Navigation visibility is
not authorization. Add/change model permissions do not authorize posting or
reversal; the services explicitly use the custom post permission for both.
Post-only users can enter payments and return to the invoice selector on success
without being redirected to a forbidden view.

## Workflow decisions

- Customer payments target completed sales invoices; supplier payments target
  posted purchase invoices. Selectors and action visibility use stored positive
  balances. Services re-fetch and lock the invoice and recheck active payment
  totals before every write. No view or JavaScript recomputes balances.
- Parties and processed-by users are assigned by the service, never client input.
- Entry uses active payment methods; required-reference methods are labelled.
  Historical registries can filter by inactive methods as well.
- Paid-at is editable in the configured Django timezone (currently UTC). Recorded
  at is the actual creation timestamp; it is not confused with the paid-at input.
- Monetary displays use Decimal-backed fields and the invoice currency snapshot,
  falling back to PharmacySettings currency if absent. A later settings change
  must not relabel an old invoice's currency or imply foreign-exchange conversion.
- Reversal uses the shared confirmation modal and optional reason. Validation
  retains values and reopens the dialog. Reversed rows remain visible. Services
  reject walk-in reversals that would leave a completed sale owing money.
- Registries accept `q`, `status`, and `method`; search includes reference, invoice
  number, and party name/code. Invalid filter values safely return an explanatory
  empty result. Lists use 25 rows, `-paid_at, -id` ordering, and shared query-string
  pagination. Invoice selection uses `-created_at, -id` ordering.
- Shared registry behavior supplies 350 ms search, immediate Enter/select changes,
  and page reset. Invoice selectors use search only. No new JavaScript is needed.
- All finance pages use the 72rem workspace, flat local navigation, shared badges,
  controls, and ledger styling. Forms stack on smaller screens, monetary rows
  wrap, and ledger tables scroll locally.

## Invoice integration and deliberate boundaries

Purchase invoice details expose paid/balance/status, a permission-gated supplier
payment link for posted outstanding invoices, and a payment-history link. No
purchasing business logic changes are needed.

Sales currently exposes POS JSON routes, not a sales invoice detail template.
Finance therefore provides its own scoped sales-invoice financial context and
invoice selector; no sales document/POS redesign is introduced.

Derived customer/supplier statement and invoice-search queries are available in
`apps.finance.queries`. They remain read-only and are not yet exposed through
Finance routes or templates. No ledger accounting, new payment states,
approvals, editing, or deletion are exposed.

## Verification

`apps.finance.test_ui` adds isolated view/template coverage alongside unchanged
service tests. Run finance tests against an isolated local PostgreSQL instance:
the existing concurrency test needs actual row-lock semantics. Never point these
tests, local preview setup, or database migrations at Neon.

Also run purchasing and dashboard tests (invoice/shared navigation integration),
core/parties/catalog tests (shared filter component),
`node --test apps/dashboard/tests_js/registry-filters.test.cjs`,
`npm run build:css`, and `git diff --check`.
