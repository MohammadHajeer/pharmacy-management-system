# Development demo dataset

`seed_demo_data` creates fictional catalog and inventory examples for PHARMANEX.
Names, prescription flags, strengths, costs, and prices are UI/testing metadata,
not medical, legal, or commercial reference information.

## Run manually after review

Confirm that your local `DATABASE_URL` points to the intended **development**
database and that you are using `config.settings`, not production settings.
The command does not choose or switch the database for you.

Prerequisites:

- An existing active `owner` user (owned by `seed_dev_auth`), or an explicit
  existing username supplied with `--actor`.
- An existing `PharmacySettings` row with the development pharmacy name/currency.
- The current project schema already present. The seed does not run migrations.

```powershell
uv run manage.py seed_demo_data
```

For a different existing audit actor:

```powershell
uv run manage.py seed_demo_data --actor your_existing_username
```

No users, groups, permissions, pharmacy settings, tax rates, or payment methods
are created or modified. Missing prerequisites cause a clear error before writes.
The command refuses `DEBUG=False`, production settings, Render deployments, and
non-development values in common environment markers (`ENVIRONMENT`, `APP_ENV`,
`DJANGO_ENV`, `ENV`, `NODE_ENV`). These are safeguards, not a substitute for
checking the target database. Do not change a production environment to pass them.

## Terminal progress

The command reports six phases matching its existing work order: database and
identity checks; categories/manufacturers; medicines with units/barcodes;
suppliers; purchase invoices with batches/movements; and verification.
Related records stay together in their existing creation loops.

Creation updates appear every 25 medicines, five invoices and 50 batch/movement
pairs, with completion counts at the end of each phase. Verification also reports
every 25 medicines and five invoices, and identifies stock and traceability checks.
Output is flushed promptly, including when redirected. Each phase and the whole
command show elapsed time using the standard library.

Reruns label existing deterministic records and skipped creation explicitly, then
report verification progress. Creation messages are provisional until commit;
only the final `PHARMANEX demo data ready` message confirms completion. Failures
identify the active phase on stderr and still propagate normally, with the same
atomic rollback behavior. Final statistics remain calculated from actual records.

## Exact initial dataset

| Record | Count |
| --- | ---: |
| Categories | 18 |
| Manufacturers | 24 |
| Medicines | 120 |
| Medicine units | 228 |
| Barcodes | 184 |
| Suppliers | 6 |
| Posted purchase invoices | 23 |
| Purchase invoice lines | 203 |
| Medicine batches / acquisition-cost layers | 203 |
| Purchase receipt stock movements | 203 |

Sixty generic concepts each have two fictional product variants. All master
names visibly include `[Demo]`. Every medicine has exactly one active base unit.
24 medicines have one unit, 84 have two, and 12 have three. Tablets/capsules use
strips of 10 and some boxes of 20. Other forms use bottles, tubes, inhalers,
sachets, ampoules or vials, with optional packs of six. Some packs are inactive;
base units stay active even on inactive medicines. Nine medicines, one category,
and two manufacturers are inactive. Both prescription-flag states are included.

Barcodes are unique deterministic synthetic 13-digit strings with check digits,
starting with `299`. They are development identifiers, not registered commercial
product codes. Some units intentionally have no barcode and some barcodes are
inactive. Selling prices are per base unit; purchase costs use the selected
purchase unit and batches store the converted four-decimal base-unit cost.
All quantity/price arithmetic uses `Decimal` and existing unit-economics helpers.

Initial inventory scenarios across all 120 medicines (including inactive ones):

- 70 have healthy normal stock; four also have an expired batch.
- 21 have low stock: seven exactly at their threshold, 14 below it.
- 11 have no batches at all; no fake zero-quantity purchase movements are created.
- 14 have both urgent and watch-window expiry batches and stock above threshold.
- Four have only expired stock, so they have no sellable quantity.
- 84 medicines have multiple batches. One lot/expiry has two different cost
  layers; other multi-batch examples exercise normal FEFO ordering.

The computed summary therefore reports **84 above threshold, 21 low stock,
15 without sellable stock**. Sellable here follows batch eligibility (active,
unexpired, positive stock); the summary includes inactive catalog medicines.

| Expiry relative to initial run date | Batches |
| --- | ---: |
| Expired, 1–180 days ago | 8 |
| Today through 30 days | 14 |
| 31–90 days | 14 |
| 91–730 days | 154 |
| More than 730 days | 13 |

Dates use Django's configured timezone (`UTC`) and `timezone.localdate()`.
Today-expiring batches remain eligible under the current inventory service.

## Historical receipt exception and traceability

The explicitly approved historical fixture path exists **only in the management
command**. It constructs purchase invoices and lines directly, then calls the
existing `apps.inventory.services.receive_purchase_stock` for both currently
valid and currently expired stock. No batch quantity is written directly.
No production service, model, migration, view, or form is changed.

The 23 deliveries contain five to nine related lines each, spread over six
fictional suppliers. Their business dates are 240–482 days before the initial
seed date. All batches were valid on their historical receipt dates. Purchase
posting dates and movement occurrence dates match those dates; `created_at`
records the actual fixture insertion time. This is a simulation of historical
receipts, not a way to post expired purchases through the application today.

Each line links to its batch. Each movement uses `PURCHASE_RECEIPT` for both
movement/source type, references the actual invoice and line UUIDs, carries the
approved invoice number, and matches its quantity, cost, medicine, batch, actor,
and receipt timestamp. Snapshots and invoice totals are verified against lines.
Purchases are unpaid, with zero demo tax/discount; balances equal grand totals.
They will add fictional supplier payables to development financial queries.
There are no supplier payments, sales, returns, or manual-adjustment movements.

## Reruns and shared-database safety

- The command inspects row counts before writing. All creation and verification
  run in one transaction; a failure rolls the entire seed back.
- Stable UUIDv5 master/document/line identities and `PHARMANEX-DEMO-V1` source
  markers identify this single dataset. A PostgreSQL transaction advisory lock
  serializes concurrent copies of the command, including the first run.
- Existing complete fixtures are validated without writes. User edits, receipt
  dates, consumed quantities and subsequent movements are preserved. No automatic
  replenishment or expiry-date refresh occurs; the dataset ages naturally.
- Batch balances are checked against all movements, so legitimate subsequent
  sales/returns/receipts remain compatible with reruns. The original demo purchase
  source chain must remain intact.
- Missing/partial fixtures, barcode/category collisions and inconsistent history
  cause an error, not deletion, automatic repair, or adoption of ordinary records.
- There is intentionally no reset flag or alternative random-seed namespace.

The dashboard now reads inventory metrics, stock health, expiry exposure, and
posted purchasing history directly from the database. Its stock-health totals
include **active medicines only**, unlike the all-catalog seed summary above.
Expiry exposure counts every batch cost layer with positive remaining quantity,
including inactive records. Both views age naturally with the data; do not expect
the original seed summary to stay equal to today's dashboard. See
[`DASHBOARD.md`](DASHBOARD.md) for definitions, permissions, and frontend builds.

## Isolated verification

Use a separate PowerShell session with SQLite overridden **before** Django loads
`.env`. The test runner creates/destroys only its isolated in-memory test database:

```powershell
$env:DATABASE_URL = 'sqlite:///:memory:'
uv run manage.py check
uv run manage.py test apps.catalog apps.inventory apps.purchasing --noinput
```

Focused tests: `uv run manage.py test apps.inventory.test_demo_seed --noinput`.
Tests cover source traceability, financial totals, stock reconciliation, expiry
and threshold scenarios, unique barcodes/base units, later-date reruns, subsequent
stock deductions, ordinary data preservation, production guards and full rollback.
SQLite does not exercise PostgreSQL advisory locking or concurrent row-lock behavior.
Do not use the SQLite test session to seed Neon; it intentionally overrides the URL.
