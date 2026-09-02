# Live dashboard

`apps.dashboard.queries` builds read-only operational, commercial, and finance
projections for the signed-in user. The dashboard performs no writes and uses no
sample or placeholder values.

## Measures and permissions

- `inventory.view_medicinebatch` enables the four inventory Daily Pulse cards,
  Stock Health, Expiry Exposure, and stock/expiry follow-up items. Stock Health
  reuses `apps.inventory.services.get_fefo_eligible_batches`; medicine-specific
  thresholds fall back to the pharmacy default only when unset. Expiry Exposure
  counts every physical batch layer with remaining quantity and uses the configured
  inclusive warning window.
- `sales.view_salesinvoice` enables Sales This Month, Sales Performance,
  Top-Selling Medicines, and completed-sale ledger entries. Revenue uses
  `SalesInvoice.grand_total` for `COMPLETED` invoices with a `completed_at` value.
  Draft and void invoices are excluded. Top sellers sum
  `SalesInvoiceLine.requested_quantity_base` for completed invoices and return the
  first seven medicines.
- `finance.view_financial_reports` enables Purchases vs Sales, Payment Method Mix,
  and Receivables. Purchases vs Sales compares `POSTED` purchase grand totals with
  `COMPLETED` sale grand totals; it is an activity comparison, not profit or margin.
  Both series use the continuous completed-sales period, with internal gaps
  zero-filled. If no completed sale exists, posted purchase months define the range.
- Payment Method Mix sums `POSTED` `CustomerPayment.amount` by the actual
  `PaymentMethod`. Reversed payments remain in history but are excluded.
- Receivables include completed invoices linked to a saved customer. Each balance
  is recalculated as invoice grand total minus posted customer payments. Only
  positive balances are counted; reversed payments, draft/void invoices, and
  walk-in sales are excluded. Partially paid means an effective posted payment is
  present; unpaid means none is present.
- `purchasing.view_purchaseinvoice`, `sales.view_salesinvoice`, and
  `finance.view_customerpayment` independently enable the matching posted/completed
  entries in Recent Activity. Events are merged by their business timestamps and
  limited to the newest five. Links are therefore never exposed without the
  corresponding record-view permission.

All monetary aggregates are filtered to the configured pharmacy currency and use
database Decimal sums. Missing settings use model defaults without creating a row.
Dates use Django's active timezone and monthly buckets use `TruncMonth`. The view
requires login, disables caching, and performs permission checks before business
queries.

## Presentation and accessibility

The dashboard keeps Daily Pulse, Stock Health, Expiry Exposure, Attention Required,
and Recent Activity. The old invoice-count Purchase Activity chart is replaced by
the grouped Purchases vs Sales value chart. New sections are Commercial Analytics,
Finance Overview, and Performance.

Chart.js receives server-prepared labels and values through Django `json_script`;
JavaScript does presentation and number formatting only. Sales Performance is a
line, Purchases vs Sales uses grouped bars, Payment Method Mix is a doughnut, and
Top-Selling Medicines uses horizontal bars. Static semantic chart tokens in
`assets/css/input.css` define all colors for light and dark themes. Theme and print
events recolor existing charts with `chart.update("none")`, so no animated color
transition occurs.

Cards stack below `xl`, canvases have bounded responsive heights, monthly labels do
not rotate, and long medicine labels are shortened only on the canvas. Full names
remain in tooltips, visible summaries, and keyboard-accessible exact-value tables.
Every chart has a server-rendered empty state and no canvas is emitted for an empty
dataset. If JavaScript or Chart.js fails, the visible summary and exact table remain
usable.

## Verification

Use an isolated test database, never the shared development database, for automated
tests:

```powershell
uv run manage.py check
uv run manage.py test apps.dashboard
node --test apps/dashboard/tests_js/*.test.cjs
npm run build:css
git diff --check
```

Dashboard coverage includes inventory boundaries, month aggregation and zero-filled
gaps, completed/draft/void sale handling, posted/draft purchases, posted/reversed
payments, receivable arithmetic, walk-in exclusion, completed-line top sellers,
permission filtering, empty states, theme refresh, and bounded query counts.

Returns, refunds, profit, margin, COGS, and income analytics remain intentionally
deferred until their authoritative posting/accounting workflows exist.
