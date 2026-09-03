# Malik Phase 1 Implementation Plan

**Plan status:** Approved-source implementation sequence awaiting Malik's review  
**Repository baseline inspected:** `79174a0` (`main`)  
**Scope authority:** `docs/JIRA_BACKLOG.csv`, `docs/BRD.md`, and `docs/ERD.md`  
**Status authority inspected:** `docs/task-status/member-1.js`

This plan contains only work assigned to Malik. Other members' work appears only where it is a real prerequisite that blocks a Malik milestone.

## Execution rules

1. Work on exactly one milestone at a time, in the order below. Independent milestones are ordered by the value they unblock: core settings logic first unblocks Mhmd Hajeer's settings UI; centralized numbering then establishes the document contract used by transaction workflows; prescription and draft POS behavior precede effective sale completion.
2. Do not start a milestone until Malik says **continue** and the preceding milestone is `Done`.
3. At a milestone marked `Blocked`, do not create a stub, mock, duplicate service, temporary stock implementation, or interim financial implementation. Stop and report the named dependency and owner.
4. Commit each verified Malik milestone directly to `main`, push it to GitHub, then pull/fetch again to confirm local and remote `main` agree. Do not create pull requests for Malik's work. Review teammate pull requests before merging them, while preserving Mohammad Hajeer's changes exactly as submitted and reporting any notice instead of editing his work.
5. `docs/MALIK_IMPLEMENTATION_PLAN.md` must be updated whenever a milestone changes state. After its verification gate passes, update only Malik's corresponding entry and synchronization comment in `docs/task-status/member-1.js`, then update the Malik-only cache revision on the `member-1.js` script tag in `docs/TEAM_DASHBOARD.html`. Never edit `member-2.js`, `member-3.js`, or `member-4.js` as part of Malik's task completion.
6. A milestone becomes `Done` only after every command and every acceptance-criteria check in its verification gate passes. If a failure requires changing a file outside the milestone scope, stop and request Malik's confirmation before expanding scope.
7. Do not run application tests against the shared Neon development database. Use the configured isolated test database. The shared Neon database may be inspected or migrated only through the separately assigned coordinated migration task.
8. If Aider is used for a bounded implementation portion, Codex reviews its complete diff and validation results and reports the estimated percentage of Codex implementation effort saved.

## Milestone status summary

| Order | Backlog ID | Malik-owned story | Current status |
| ---: | --- | --- | --- |
| 0 | `E1-T01` / work item `1100` | Coordinate the approved Phase 1 source of truth and dated delivery plan | Done |
| 1 | `E1-T04` / work item `1400` | Complete core settings workflow logic over the existing models | Done |
| 2 | `E1-T06` / work item `1600` | Implement approved UUID-derived document numbering | Done |
| 3 | `E3-T01` / work item `3100` | Deliver lightweight prescription workflows over the existing models | Done |
| 4 | `E3-T02` / work item `3200` | Build server-side POS search, barcode, cart, and totals logic | Done |
| 5 | `E3-T03` / work item `3300` | Complete sales atomically with deterministic FEFO row locks | Done |
| 6 | `E3-T06` / work item `3600` | Verify prescription, POS, sale-completion, and invoice behavior | Done |
| 7 | `E1-T09` / work item `1800` | Coordinate final documentation and operational handoff | Done — technical integration gate remains deferred |

---

## Milestone 0 — Phase 1 source-of-truth coordination

**Backlog story:** `E1-T01` / work item `1100`

**Objective:** Keep every delivery item traceable to the approved BRD/ERD and within the dated Phase 1 scope.

**Exact scope**

- Documentation and planning files only: `docs/BRD.md`, `docs/ERD.md`, `docs/JIRA_BACKLOG.csv`, `docs/REPO_IMPLEMENTATION_CONTEXT.md`, `docs/DEVELOPMENT_GUIDE.md`, `docs/BACKUP_RUNBOOK.md`, `docs/TEAM_DASHBOARD.html`, and Malik's status/plan files.
- Must not touch application code, models, migrations, templates, configuration, credentials, or the shared database.

**Preconditions**

- The approved BRD and ERD exist.
- The backlog dates remain within `2026-08-29` through `2026-09-06`.

**Implementation steps**

1. Reconcile backlog items with the BRD, ERD, and repository implementation context.
2. Exclude completed baseline model work and deferred Phase 2 features.
3. Preserve the four-person ownership split and the exclusive authentication/design ownership assigned to Mhmd Hajeer.
4. Keep the Jira CSV and team dashboard task content synchronized.

**Verification gate**

Run:

```powershell
uv run manage.py check
uv run manage.py makemigrations --check --dry-run
uv run manage.py test
git diff --check
git diff --name-only origin/main...HEAD
git status --short
```

Executed on 2026-09-03: `manage.py check`, `makemigrations --check --dry-run`, `showmigrations --plan`, the documentation inventory/credential scan, CSV parsing, and `git diff --check`. The full `manage.py test` command was intentionally not run because Malik explicitly prioritized completing the documentation handoff within the remaining weekly usage limit. This exception does not count as `E1-T07` evidence and does not establish final technical readiness.

Confirm literally:

- [x] Every delivery item maps to an approved BRD/ERD requirement or documented repository gap.
- [x] Every due date is between `2026-08-29` and `2026-09-06`.
- [x] Completed baseline model work is not scheduled again.
- [x] Deferred Phase 2 features remain absent.
- [x] No unrelated files or migration drift are present.

**Status:** Done — mirrored from `docs/task-status/member-1.js`; this plan does not claim new execution or retroactive command output for the already-recorded completion.

---

## Milestone 1 — Core settings workflow logic

**Backlog story:** `E1-T04` / work item `1400`

**Objective:** Provide reusable, permission-scoped settings validation and update handlers over the existing `PharmacySettings`, `TaxRate`, and `PaymentMethod` models.

**Exact scope**

- May create/edit only:
  - `apps/core/forms.py`
  - `apps/core/services.py`
  - `apps/core/tests.py`
  - `docs/MALIK_IMPLEMENTATION_PLAN.md`
  - `docs/task-status/member-1.js` only after the gate passes
- Read-only references: `apps/core/models.py`, `apps/core/migrations/0001_initial.py`, authentication code, and shared UI/component files.
- Must not touch `apps/core/models.py`, any migration, `config/settings.py`, authentication/group provisioning, `config/navigation.py`, shared templates/components, CSS, JavaScript, or Mhmd Hajeer's settings UI task.

**Preconditions**

- Existing core models and `0001_initial` remain unchanged.
- Django's `core.change_pharmacysettings`, TaxRate, and PaymentMethod model permissions exist in the test database.
- Tests create their own users, groups, permissions, and settings data; they do not rely on `seed_dev_auth` or shared Neon state.

**Implementation steps**

1. Add ModelForms that expose only the approved operational fields; never include environment or deployment settings.
2. Normalize and validate the three-character single currency code without inventing multi-currency behavior.
3. Preserve the singleton record through a service-owned `get_or_create`/update path using `singleton_key = 1` and the existing database constraint.
4. Reuse model/database validation for the zero-to-100 tax range and non-negative default low-stock threshold; add useful form errors without duplicating contradictory rules.
5. Add permission-scoped service handlers for pharmacy settings, tax rates, and payment-method activation. Owner/Admin is represented by Django permissions, not `is_superuser` checks or hardcoded group-name checks.
6. Test success, invalid values, singleton preservation, inactive payment methods, anonymous/unauthorized denial at the handler boundary, and absence of secret/environment fields.
7. Hand the stable forms/service contract to Mhmd Hajeer; do not implement his templates or UI decisions.

**Verification gate**

Run:

```powershell
uv run manage.py check
uv run manage.py test apps.core
uv run manage.py makemigrations --check --dry-run
git diff --check
git diff --name-only origin/main...HEAD
git status --short
```

Confirm literally:

- [x] Only Owner/Admin-authorized callers can change settings.
- [x] Singleton settings, one currency, tax ranges, low-stock/expiry defaults, and payment-method activation are validated.
- [x] No secret or environment setting is exposed.
- [x] Existing model and database constraints remain authoritative and unchanged.
- [x] Only the milestone files are changed and there is no migration drift.

**Status:** Done

---

## Milestone 2 — Central UUID-derived document numbering

**Backlog story:** `E1-T06` / work item `1600`

**Objective:** Establish one deterministic, retry-safe helper contract for all five approved Phase 1 document-number formats.

**Exact scope**

- May create/edit only:
  - `apps/core/document_numbers.py`
  - `apps/core/tests.py`
  - `docs/MALIK_IMPLEMENTATION_PLAN.md`
  - `docs/task-status/member-1.js` only after the gate passes
- Read-only references: the ID and document-number fields in `apps/sales/models.py`, `apps/purchasing/models.py`, and `apps/returns/models.py`.
- Must not touch any model, migration, sequence table, admin page, template, domain posting/return service owned by another member, or user-entered supplier invoice reference.

**Preconditions**

- Project-owned documents continue to use UUID primary keys.
- Existing number fields remain `CharField(max_length=40)` with their approved uniqueness constraints.
- No `DocumentSequence` model or sequential-number requirement has been approved.

**Implementation steps**

1. Define the five allowed prefixes in one central module: `SAL`, `PUR`, `CRT`, `SRT`, and `CRF`.
2. Accept only a UUID and an approved document kind; reject unsupported kinds instead of silently generating a value.
3. Return `<PREFIX>-<complete uppercase 32-character UUID hex>` with no truncation or mutable counter.
4. Keep the helper deterministic so repeated calls for the same document return the same value.
5. Expose explicit functions/contracts for sales/purchase assignment at completion/posting and return/refund assignment at creation; do not use model `save()` overrides or signals.
6. Add focused tests for every prefix, uppercase/full-length output, invalid kinds, field-length compatibility, and retry-safe output.
7. Record the integration contract for the later owning-domain services without implementing another member's transaction workflow.

**Verification gate**

Run:

```powershell
uv run manage.py check
uv run manage.py test apps.core.tests.DocumentNumberTests
uv run manage.py makemigrations --check --dry-run
git diff --check
git diff --name-only origin/main...HEAD
git status --short
```

Confirm literally:

- [x] `SAL-`, `PUR-`, `CRT-`, `SRT-`, and `CRF-` use the complete uppercase UUID hex.
- [x] Draft sales and purchase numbers may remain blank until completion/posting.
- [x] The helper contract assigns return/refund numbers at creation time when called by the owning creation service.
- [x] Output is deterministic and compatible with database uniqueness.
- [x] Focused tests cover every prefix and retry behavior.
- [x] No sequence infrastructure, unrelated file, model change, or migration drift exists.

**Status:** Done

---

## Milestone 3 — Lightweight prescription backend workflow

**Backlog story:** `E3-T01` / work item `3100`

**Objective:** Implement the approved non-clinical prescription validation, queries, and request-handling contract over the existing prescription models.

**Exact scope**

- May create/edit only:
  - `apps/prescriptions/forms.py`
  - `apps/prescriptions/services.py`
  - `apps/prescriptions/queries.py`
  - `apps/prescriptions/views.py`
  - `apps/prescriptions/urls.py`
  - `apps/prescriptions/tests.py`
  - `config/urls.py` only for the `apps.prescriptions.urls` include
  - `docs/MALIK_IMPLEMENTATION_PLAN.md`
  - `docs/task-status/member-1.js` only after the gate passes
- Read-only references: `apps/prescriptions/models.py`, `apps/parties/models.py`, `apps/catalog/models.py`, authentication patterns, and shared component contracts.
- Must not touch prescription models/migrations, attachment/media configuration, shared navigation, shared templates/components, CSS/JavaScript, clinical rules, or Mhmd Hajeer's UI-UX task.

**Preconditions**

- `Prescription` and `PrescriptionItem` baseline models/migration exist unchanged.
- Customer and prescriber remain optional; a fake customer must not be created.
- Attachment storage/access/retention is not approved, so attachment upload remains disabled.
- Required Django model permissions are available for isolated tests.

**Implementation steps**

1. Add forms/formset validation for prescription metadata and one or more medicine items without exposing the attachment field.
2. Validate positive optional prescribed quantities and preserve dosage/instruction and notes behavior already approved by the schema.
3. Add transactional creation/update services that set `created_by`, use the existing models, and do not create clinical lifecycle states.
4. Add permission-scoped list/detail/create request handlers and namespaced routes; keep presentation context stable for Mhmd Hajeer's later templates.
5. Add a query contract that exposes only the non-clinical `prescription_required` warning data needed by POS.
6. Test optional customer/prescriber behavior, item validation, permissions, isolated data, and the disabled attachment boundary.

**Verification gate**

Run:

```powershell
uv run manage.py check
uv run manage.py test apps.prescriptions
uv run manage.py makemigrations --check --dry-run
git diff --check
git diff --name-only origin/main...HEAD
git status --short
```

Confirm literally:

- [x] Authorized callers can create and retrieve lightweight prescriptions with optional customer/prescriber and medicine items.
- [x] Required quantities and instructions validate according to the approved schema.
- [x] POS can consume non-clinical prescription-required warning data.
- [x] No clinical advice or complex prescription lifecycle was added.
- [x] File upload remains disabled because its prerequisites are not approved.
- [x] Only milestone files changed and there is no migration drift.

**Status:** Done

---

## Milestone 4 — Server-authoritative draft POS logic

**Backlog story:** `E3-T02` / work item `3200`

**Objective:** Implement server-authoritative medicine/barcode lookup, draft cart handling, unit conversion, and Decimal total previews without mutating stock.

**Exact scope**

- May create/edit only:
  - `apps/sales/forms.py`
  - `apps/sales/services.py`
  - `apps/sales/queries.py`
  - `apps/sales/views.py`
  - `apps/sales/urls.py`
  - `apps/sales/tests.py`
  - `config/urls.py` only for the `apps.sales.urls` include
  - `docs/MALIK_IMPLEMENTATION_PLAN.md`
  - `docs/task-status/member-1.js` only after the gate passes
  - `docs/TEAM_DASHBOARD.html` only for Malik's status-file cache marker after the gate passes
- Read-only references: `apps/sales/models.py`, `apps/catalog/models.py`, `apps/catalog/unit_economics.py`, `apps/parties/models.py`, `apps/prescriptions` public contracts, `apps/inventory/models.py`, and core tax/settings models.
- Must not touch any model/migration, `MedicineBatch.quantity_available_base`, `StockMovement`, inventory services, payment posting, shared navigation, templates/components, CSS/JavaScript, or Mhmd Hajeer's POS UI-UX task.

**Preconditions**

- Milestone 2 is `Done` so document-number behavior is fixed before transaction services are built.
- Milestone 3 is `Done` so POS uses the real prescription warning/association contract.
- The existing `apps.catalog.unit_economics` helper and sales baseline models pass their tests.

**Implementation steps**

1. Add active medicine, sale-allowed unit, and exact active-barcode query functions with no write side effects for unknown barcodes.
2. Add draft-sale/cart form and service logic for saved or walk-in customers, optional prescription association, and multiple lines.
3. Use `apps.catalog.unit_economics.base_quantity` and `selected_unit_selling_price`; never duplicate conversion rules or use float.
4. Recalculate line subtotal, discount, tax, line total, and invoice preview totals server-side using the approved `ROUND_HALF_UP` sequence.
5. Snapshot medicine/unit descriptions, base quantity, selected-unit price, tax, discount, and prescription-warning state into the existing draft models.
6. Reject tampered client totals and invalid/inactive medicine/unit/barcode inputs.
7. Keep stock and expiry data query-only. Do not allocate, decrement, reserve, or create stock movements in this milestone.
8. Add permission-scoped handlers and focused tests; leave keyboard interaction and visual design to Mhmd Hajeer.

**Verification gate**

Run:

```powershell
uv run manage.py check
uv run manage.py test apps.sales.tests.PosLookupTests apps.sales.tests.PosDraftServiceTests
uv run manage.py makemigrations --check --dry-run
git diff --check
git diff --name-only origin/main...HEAD
git status --short
```

Confirm literally:

- [x] Known barcodes resolve to the correct active medicine/unit and unknown barcodes write nothing.
- [x] Saved-customer and walk-in draft flows work.
- [x] Quantities, discounts, tax, and totals are recalculated server-side using the approved rounding sequence.
- [x] Tampered totals are rejected.
- [x] Stock/expiry information remains query-only until completion.
- [x] `Medicine.default_selling_price` is treated as the base-unit price.
- [x] Selected-unit price equals base-unit price times conversion, quantized to four decimals with `ROUND_HALF_UP`.
- [x] `SalesInvoiceLine.unit_price` stores the selected-unit price snapshot.
- [x] Inventory quantities remain in base units.
- [x] Only milestone files changed and there is no migration drift.

**Status:** Done

---

## Milestone 5 — Atomic sale completion with FEFO locking

**Backlog story:** `E3-T03` / work item `3300`

**Objective:** Complete a sale atomically through the authoritative inventory and finance services, with deterministic FEFO locks and rollback safety.

**Exact scope**

- After all blockers clear, may create/edit only:
  - `apps/sales/services.py`
  - `apps/sales/views.py`
  - `apps/sales/urls.py`
  - `apps/sales/tests.py`
  - `docs/MALIK_IMPLEMENTATION_PLAN.md`
  - `docs/task-status/member-1.js` only after the gate passes
- Read-only/call-only dependencies: `apps/inventory` public FEFO/mutation service, `apps/finance` public customer-payment service, `apps/core/document_numbers.py`, prescription contracts, and existing models/migrations.
- Must not edit `apps/inventory`, `apps/finance`, any model/migration, batch quantities directly, stock movements directly, auth provisioning, templates/shared UI, or another member's service to make the milestone pass.

**Preconditions**

- Malik milestones 2, 3, and 4 are `Done`.
- **Hala:** `E2-T02 — Implement authoritative inventory and FEFO services with row locking` is merged, tested, and exposes the approved public allocation/deduction service. This includes its prerequisite `E2-T03` uniqueness constraints.
- **Verified prerequisite:** Mhmd Hajeer's `E1-T08 — Review and apply pending Phase 1 follow-up migrations to Neon` is `Done`. On 2026-08-29, `showmigrations` confirmed the finance, inventory, returns, and sales follow-up migrations applied, and `migrate --plan` reported no planned operations.
- **Yasser:** `E4-T01 — Post and reverse customer and supplier payments with invoice row locks` is merged and exposes the approved customer-payment operation needed for an optional initial payment.
- An isolated PostgreSQL test database is available for real row-lock concurrency tests; SQLite is not accepted as proof of PostgreSQL locking behavior.

**Implementation steps**

1. Stop immediately if any precondition above is missing; report the exact dependency and owner.
2. Add a sale-completion service enclosed in `transaction.atomic()` and reject any state other than `DRAFT`.
3. Lock the `SalesInvoice`, re-read/revalidate status, permissions, totals, prescription acknowledgement, and settlement rules after locking.
4. Call Hala's inventory service for eligible-batch locking/allocation in `expiry_date`, `first_received_at`, `id` order; never reproduce FEFO or mutate batches in `apps.sales`.
5. Assign the deterministic `SAL-<UUIDHEX>` number through the approved central helper before changing status.
6. Persist allocations and acquisition-cost snapshots supplied by the inventory boundary, and rely on that boundary for matching negative `SALE` movements.
7. If an initial payment is supplied, call Yasser's finance service inside the coordinated atomic operation; never implement duplicate payment arithmetic in sales.
8. Recalculate and revalidate walk-in settlement, set completion fields/status, and ensure any failure rolls back invoice, allocations, stock, movements, and payment.
9. Add service, permission, failure, and PostgreSQL concurrency tests.

**Verification gate**

Run with an isolated PostgreSQL test configuration:

```powershell
uv run manage.py check
uv run manage.py test apps.sales.tests.SaleCompletionServiceTests apps.sales.tests.SaleCompletionConcurrencyTests
uv run manage.py makemigrations --check --dry-run
git diff --check
git diff --name-only origin/main...HEAD
git status --short
```

Confirm literally:

- [x] Completion locks the invoice and eligible batches in deterministic FEFO order.
- [x] Status, permission, totals, prescription acknowledgement, and stock are rechecked after locks.
- [x] Allocations, negative sale movements, cost snapshots, optional initial payment, and completion status commit atomically.
- [x] Insufficient/expired stock and every tested failure roll back all writes.
- [x] Concurrent completions cannot oversell on PostgreSQL.
- [x] No inventory or finance logic was duplicated and no dependency file was edited.
- [x] Only milestone files changed and there is no migration drift.

**Status:** Done. Sale completion now locks the invoice, revalidates the authoritative draft state, delegates deterministic FEFO deduction/movements to `apps.inventory`, delegates optional initial payments to `apps.finance`, assigns the approved UUID-derived sales number, and commits or rolls back the entire workflow atomically. On 2026-08-31, all 23 `apps.sales.tests` passed against PostgreSQL in 513.758 seconds, including the two-thread oversell test; `manage.py check` and `makemigrations --check --dry-run` also passed with no migration drift.

---

## Milestone 6 — Sales and prescription verification

**Backlog story:** `E3-T06` / work item `3600`

**Objective:** Prove the completed prescription, POS, sale-completion, payment integration, and invoice-output behavior with isolated focused tests.

**Exact scope**

- After all blockers clear, may edit only:
  - `apps/prescriptions/tests.py`
  - `apps/sales/tests.py`
  - `docs/MALIK_IMPLEMENTATION_PLAN.md`
  - `docs/task-status/member-1.js` only after the gate passes
- All application/services/templates under test are read-only during this verification milestone.
- Must not change production code merely to make an assertion pass, duplicate existing baseline tests, alter fixtures shared by other members, or weaken an acceptance criterion.

**Preconditions**

- Malik milestones 3, 4, and 5 are `Done`.
- **Mhmd Hajeer:** `E3-T05 — Deliver print-ready sales invoice and receipt output` is merged and ready for snapshot/output verification.
- Hala's inventory dependency and Yasser's payment dependency inherited through milestone 5 remain merged and passing.
- An isolated PostgreSQL test database is available for concurrency coverage.

**Implementation steps**

1. Stop and report the named blocker if milestone 5 or Mhmd Hajeer's invoice-output work is incomplete.
2. Inventory existing tests and add only missing acceptance coverage.
3. Cover barcode lookup, saved/walk-in behavior, prescription warnings, Decimal rounding, FEFO multi-batch allocation, acquisition-cost snapshots, optional payment, rollback, and permissions.
4. Add PostgreSQL concurrency coverage proving deterministic locking prevents overselling.
5. Verify invoice/receipt output reads stored snapshots rather than current master data.
6. Ensure every test creates isolated users, permissions, and business records.

**Verification gate**

Run with an isolated PostgreSQL test configuration:

```powershell
uv run manage.py check
uv run manage.py test apps.prescriptions apps.sales
uv run manage.py makemigrations --check --dry-run
git diff --check
git diff --name-only origin/main...HEAD
git status --short
```

Confirm literally:

- [x] Tests cover barcode lookup, walk-in/saved customers, prescription warnings, rounding, FEFO multi-batch allocation, cost snapshots, payments, rollback, and permissions.
- [x] PostgreSQL concurrency tests prove deterministic locks prevent overselling.
- [x] Invoice output uses stored snapshots.
- [x] Tests create isolated data and do not depend on shared Neon state.
- [x] No production or unrelated file changed and there is no migration drift.

**Status:** Done — all 58 `apps.prescriptions` and `apps.sales` tests passed against an isolated PostgreSQL test database in 957.929 seconds on 2026-09-01, including deterministic concurrent oversell prevention and the historical invoice/receipt snapshot regression. Django destroyed the isolated test database successfully; system checks and migration-drift checks also passed.

---

## Milestone 7 — Final documentation and operational handoff

**Backlog story:** `E1-T09` / work item `1800`

**Objective:** Reconcile the finished Phase 1 repository, operational guidance, and remaining documented gaps without changing approved scope.

**Exact scope**

- May edit only documentation and Malik-owned tracking files that are demonstrably stale after final implementation:
  - `docs/REPO_IMPLEMENTATION_CONTEXT.md`
  - `docs/DEVELOPMENT_GUIDE.md`
  - `docs/BACKUP_RUNBOOK.md`
  - `docs/JIRA_BACKLOG.csv` only when final implementation status makes an entry factually stale
  - `docs/TEAM_DASHBOARD.html` only to keep approved backlog content synchronized
  - `docs/MALIK_IMPLEMENTATION_PLAN.md`
  - `docs/task-status/member-1.js`
- `docs/BRD.md` and `docs/ERD.md` are read-only unless the team lead separately approves a requirements/schema change.
- Must not touch application code, models, migrations, credentials, shared database data, or rewrite history during handoff.

**Preconditions**

- **Mhmd Hajeer:** `E1-T07 — Integrate and verify the complete Phase 1 workflow` is `Done` with evidence.
- That integration milestone's own prerequisites are complete: Hala's purchase posting (`E2-T04`), Malik's sale completion (`E3-T03`), Yasser's payment/return/report work (`E4-T01`, `E4-T02`, `E4-T04`), and Mhmd Hajeer's migration verification (`E1-T08`).
- All Malik implementation milestones above are `Done`.
- Final repository commit and migration state are known.

**2026-09-03 execution exception:** Malik explicitly prioritized the documentation handoff because of the remaining weekly usage limit and accepted deferring `E1-T07`. This permits documentation reconciliation to proceed, but it does not satisfy or waive the technical readiness evidence: the representative end-to-end workflow and role-access gate must remain recorded as unverified.

**Implementation steps**

1. Stop if Mhmd Hajeer's final integration milestone is not `Done`; report that dependency instead of drafting a hypothetical final state.
2. Compare current code/migrations against the BRD, ERD, repository context, development guide, backlog, dashboard, and backup runbook.
3. Update only facts that changed during completed implementation; retain unresolved decisions as explicit gaps.
4. Confirm the backup runbook remains discoverable, operational, and free of credentials.
5. Confirm inventory ownership, targeted locks, applied migration state, permissions, document-numbering contract, and deferred Phase 2 boundaries are accurately documented.
6. Remove statements that call completed work unimplemented, without rewriting historical requirements.
7. Run the complete verification gate and prepare the focused documentation handoff.

**Verification gate**

Run:

```powershell
uv run manage.py check
uv run manage.py test
uv run manage.py makemigrations --check --dry-run
uv run manage.py showmigrations
git diff --check
git diff --name-only origin/main...HEAD
git status --short
```

Confirm literally:

- [x] Documentation matches the inspected repository and applied migration state.
- [x] The backup runbook is discoverable and contains no credentials.
- [x] Migration and authoritative inventory ownership rules are explicit.
- [x] Unresolved team-lead decisions are recorded without invented answers.
- [x] No completed work is described as unimplemented.
- [x] Only approved documentation/tracking files changed and there is no migration drift.

**Status:** Done — documentation and operational handoff reconciliation completed on 2026-09-03 under Malik's explicit verification exception. `E1-T07` remains an unverified external readiness gap and is not claimed as passed.

---

## Remaining external readiness gate

All Malik milestones in this plan are complete. Mhmd Hajeer's `E1-T07` representative end-to-end and role-access technical gate remains unverified and must not be reported as passed.
