# Reports workspace

`apps.reports` is the consolidated read-only Phase 1 reporting area. It owns no
models, migrations, snapshots, or mutable totals. `apps/reports/queries.py`
derives every row and summary from records owned by Sales, Purchasing,
Inventory, Finance, Returns, and Parties; views only enforce access, paginate,
and prepare presentation context.

## Available reports

- **Sales Report:** completed sales only, with effective payment state derived
  from active posted customer payments. Draft and void sales are excluded.
- **Purchase Report:** posted purchase invoices only. Purchase value is
  operational; effective paid and outstanding payable values are rendered only
  to users with `finance.view_financial_reports`.
- **Stock Report:** batch-layer quantity from `MedicineBatch`, with medicine
  sellable quantity and the existing medicine/default low-stock threshold rule.
- **Expiry Report:** positive remaining batch layers classified as expired,
  within 30 days, 31–90 days, or later using `timezone.localdate()`.
- **Customer Receivables:** completed saved-customer invoices less effective
  posted customer payments. Walk-ins and non-positive balances are excluded by
  the default outstanding filter.
- **Supplier Payables:** posted purchases less effective posted supplier
  payments, with outstanding-only as the default filter.
- **Payment Activity:** customer and supplier payment records. Active customer
  receipts and supplier disbursements are summarized separately. Reversals
  remain visible in history but are excluded from both active values.
- **Returns Report:** customer returns, customer refunds, and supplier returns
  from their authoritative models. Record types are limited to the return view
  permissions held by the user.

No report labels transaction differences as profit, margin, COGS, projection,
or forecast.

## Permissions

| Report | Required permission |
| --- | --- |
| Sales | `sales.view_salesinvoice` |
| Purchases | `purchasing.view_purchaseinvoice` |
| Purchase paid/payable columns | `finance.view_financial_reports` |
| Stock and expiry | `inventory.view_medicinebatch` |
| Receivables, payables, payment activity | `finance.view_financial_reports` |
| Customer return/refund rows | `returns.view_customerreturn` |
| Supplier return rows | `returns.view_supplierreturn` |

The Reports hub and sidebar entry are visible when the user can open at least
one report. Every report view repeats its permission check server-side. Source
detail links are shown only when the user also holds the source workspace's view
permission.

## Filtering and pagination

Reports use ordinary server-side GET filters and the shared 25-row paginator.
Date ranges are inclusive and invalid dates/ranges render field-level errors
with an empty result rather than falling back to an unfiltered query. The shared
`{% querystring %}` pagination component preserves active filters.

## Verification

Use a disposable test database rather than a shared development or Neon
database:

```powershell
$env:DATABASE_URL = "sqlite:///:memory:"
uv run manage.py test apps.reports
uv run manage.py check
npm run build:css
git diff --check
```
