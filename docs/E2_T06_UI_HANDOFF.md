# E2-T06: Clinical Operations Console UI refinement

## Implemented

- Sidebar items use explicit local route-name sets plus their real Django namespace. Namespace fallback is allowed only when one configured area owns it; unavailable items cannot become active. Existing permission filtering is unchanged. Supplier and customer routes activate only their own area; medicine/unit/barcode/reference routes and purchase list/create/detail/post routes retain their parent.
- Medicines, categories, manufacturers, suppliers, customers, and existing prescribers use registry workspaces: clear headers, permitted primary actions, combined existing GET filters, status badges, secondary edit actions, outlined reversible activation actions, and useful empty states.
- Medicine detail separates product identity from commercial configuration, then connects unit and barcode ledgers. The active base unit is visibly protected from deactivation.
- Forms group related fields, use the existing controls, retain values/errors, and collapse on narrow screens. The previously omitted required `base_unit_name` field is now rendered on medicine creation; unchecked unit flags remain unchecked after validation.
- Purchase list uses a transaction ledger. Creation separates invoice information from the existing formset lines, with a save-draft summary panel. Detail presents stored lines/totals, draft supplier identity, posted supplier snapshots, and permission-aware posting. Posted and void documents have no edit controls.
- All changed screens supply explicit breadcrumbs. No URL-name labels, fake namespaces, new routes, or group-name checks were introduced.
- Shared addition: `templates/components/registry_filters.html`, composed from existing input/select/button controls. Shared input gains numeric `step`, `min`, and `max`; CSS gains small ledger/record-link roles. Existing sidebar, topbar, dashboard layout, modal, select behavior, and checkbox components were not rewritten.

## Small integration correction

Medicine search referenced a nonexistent direct `Medicine.barcodes` relationship. The existing lookup now follows `units__barcodes__barcode__iexact`; name, generic-name, and barcode searches keep their current GET contract and status filtering. This was reported before changing it and is covered by regression tests.

No form business rules, models, migrations, services, authorization decorators, purchasing posting logic, transactions, locking, FEFO, or unit economics were changed.

## Existing contract limits and deferred work

- The current purchase formset initially renders two static lines (one minimum plus one extra). Multiple submitted lines and deletion flags are supported and preserved. No dynamic add-line controls, live total calculations, purchase filters, or draft-edit endpoint were introduced. Totals appear after saving through the existing service.
- Inventory services/models exist, but no inventory views/URLconf/presentation-query contract is routed. Inventory UI remains deferred.
- Supplier Return UI remains explicitly deferred until E2-T05 is complete. No return forms, routes, services, or placeholder workflows were added.
- Prescriber master-data pages were styled; prescription functionality was not expanded. There is no prescriber sidebar item, so those routes do not incorrectly activate Suppliers or Customers.
- Walk-in sales still do not require a saved customer.

## Validation

Tests use `--settings=config.visual_test_settings --noinput` to isolate the database. The default PostgreSQL test invocation encountered an existing `test_neondb`; it was not deleted or reused.

- `uv run manage.py check`: passed.
- Affected app suites: **63 passed** (Catalog 17, Parties 9, Purchasing 14, Dashboard 23).
- `uv run manage.py test --settings=config.visual_test_settings --noinput`: **161 run, 159 passed, 2 pre-existing failures**, reproduced against untouched HEAD as described below.
- `npm run build:css`: passed; generated CSS is ignored and was not manually edited.
- `git diff --check`: passed.
- Browser QA used fake records in a disposable local SQLite database, including populated and empty registries, medicine detail/form, party forms, purchase list/create/posted detail, custom-select keyboard operation, and route-specific sidebar states.
- Desktop 1440 × 1000, tablet 768 × 1024, mobile 390 × 844, and narrow mobile 320 × 740: no horizontal page overflow in the checked screens. Dense tables scroll locally; empty states remain outside their scroll regions.

The full suite's Accounts login-message assertion and Sales `10` versus `10.000` stock-format assertion also fail in an untouched HEAD snapshot using the same SQLite settings. These unrelated failures were not changed. SQLite does not establish PostgreSQL row-locking/concurrency behavior.

## Files created

- `templates/components/registry_filters.html`
- `apps/catalog/test_ui.py`
- `apps/parties/test_ui.py`
- `apps/purchasing/test_ui.py`
- `docs/E2_T06_UI_HANDOFF.md`

## Files modified

- `config/navigation.py`, `config/context_processors.py`
- `assets/css/input.css`, `templates/components/input.html`
- `apps/catalog/views.py`, `apps/parties/views.py`, `apps/purchasing/views.py`
- `apps/dashboard/tests.py`
- Catalog templates: medicines `list.html`, `detail.html`, `form.html`, `unit_form.html`, `barcode_form.html`; categories and manufacturers `list.html` / `form.html`.
- Parties templates: suppliers, customers, and prescribers `list.html` / `form.html`.
- Purchasing templates: purchase invoices `list.html`, `form.html`, `detail.html`.
- `docs/COMPONENTS.md`, `docs/DEVELOPMENT_GUIDE.md`

Suggested commit message: `feat(ui): refine catalog, parties and purchasing workspaces`

No commits, pushes, or migrations were made.
