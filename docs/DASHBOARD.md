# Live operational dashboard

`apps.dashboard.queries` provides read-only projections for the existing dashboard.
There are no schema changes, write operations, API fetches, or seed operations.
The separate visual comparison page retains its original, clearly labeled sample
records in `apps.dashboard_preview.sample_data`; live dashboard code never uses them.

## Measures and permissions

- `inventory.view_medicinebatch` enables the four Daily Pulse counts (active
  medicines, low stock, out of stock, and expiring soon), inventory charts, and
  inventory attention records. Data and JSON are omitted without this permission.
- Stock Health includes active medicines only. Its aggregate subquery reuses
  `apps.inventory.services.get_fefo_eligible_batches`: active batches, positive
  remaining quantity, expiry on or after `timezone.localdate()`. Healthy means
  quantity above threshold; low means `0 < quantity <= threshold`; out means zero,
  including medicines without batches. A null medicine threshold uses the pharmacy
  default, while an explicit zero remains zero. Missing pharmacy settings use the
  model's defaults without creating a settings row.
- Expiry Exposure counts physical batch cost layers with positive quantity,
  including inactive batches/medicines. Buckets are expired, today through
  `min(30, expiry_warning_days)`, the rest of the warning window if any, and beyond
  the window. At the default 90 days these are Expired / 0–30 / 31–90 / 91+.
  Warning boundaries are inclusive; expired means strictly before today. The
  expiring-soon KPI excludes already expired stock. A zero-day window means today.
- Attention shows at most three stock records (out first, then lowest sellable
  quantity) and three expiry records (earliest expiry first). Stock names link to
  the existing medicine detail only with `catalog.view_medicine`. There is no
  invented batch route. Counts in chart summaries describe the full population.
- `purchasing.view_purchaseinvoice` enables the latest five posted receipt events
  and their invoice amounts/currencies, matching the existing purchase detail
  permission. Financial-report permission alone does not grant purchasing access.
  Supplier names use invoice snapshots, with a joined supplier fallback. Drafts
  and voids are excluded; dates use `posted_at`, not seed insertion time.
- Purchase Activity counts posted invoices in the twelve calendar months ending
  with the latest receipt month. Months without receipts are zero-filled; the
  exact historical range is visible. It is shown only with receipts in at least
  two months. Counts avoid mixing currencies. The demo's 23 historical receipts
  span enough months to make this useful.
- Sales, payment, refund, revenue, and net receivables measures are intentionally
  deferred. No fake amounts are displayed. In particular, invoice balances are
  payment-only history and must not be mislabeled as the net customer position
  defined by the BRD/ERD (which also accounts for returns and refunds).

Dates use Django's current timezone (the project's business timezone is UTC).
The view requires login and disables caching. Permission checks run before
business queries, not just during template rendering. Query count stays bounded
as data grows; attention and activity use joined, limited queries.

## Frontend build and accessibility

The repository has no JavaScript bundler. `npm run build:js` copies the installed
Chart.js browser distribution, source map, and MIT license to the ignored
`static/vendor/chartjs/` directory. No CDN or additional dependency is used.
`npm run build` runs that copy and the existing CSS build. `npm run dev` runs both
in `predev`; the deployment build runs both before `collectstatic`. If starting
Django directly with `uv run manage.py runserver`, run `npm run build` first.

The dashboard alone loads the vendor script and `static/js/dashboard-charts.js`,
in deferred order through the existing `extra_scripts` block. Django's
`json_script` serializes prepared chart dictionaries. JavaScript renders them
without business calculations. Colors resolve the existing CSS theme tokens.

Charts have bounded heights, stack below the desktop breakpoint, use integer
axes, and disable animation (including for reduced-motion users). Each canvas is
associated with its heading and a visible text summary. A native expandable
table provides exact monthly purchase counts. Without JavaScript or with a failed
library load, summaries remain visible and canvases remain hidden.
No-data cards show a useful empty state. The activity ledger scrolls within its
own keyboard-focusable region rather than widening the page.

## Verification

Use isolated SQLite, never the shared Neon database, for automated tests:

```powershell
$env:DATABASE_URL = 'sqlite:///:memory:'
uv run manage.py check
uv run manage.py test apps.dashboard apps.inventory --noinput
node --test apps/dashboard/tests_js/*.test.cjs
npm run build
git diff --check
```

Tests cover threshold/expiry boundaries, inactive/empty stock, settings fallbacks,
permission filtering, JSON/template escaping, receipt chronology, monthly gaps,
local date boundaries, and bounded query counts. SQLite does not test PostgreSQL
locking; the dashboard itself never locks or mutates business data.
