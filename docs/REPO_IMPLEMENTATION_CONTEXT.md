# Repository Implementation Context

This document records the current Phase 1 application so architecture, implementation, and AI-assisted work preserve what is already built. Repository facts are authoritative; behavior not technically verified is identified explicitly.

## 1. Repository snapshot inspected

- Repository: `https://github.com/MohammadHajeer/pharmacy-management-system.git`
- Branch: `main`
- Implementation commit: `2db2a4e2465151cc2ca3f56af83afcfa5e98a8d4`
- Commit date: `2026-09-03`
- Commit subject: `feat(finance): add derived statement queries`
- Inspection and reconciliation date: 2026-09-03
- Reconciliation scope: final Phase 1 repository, domain workflows, UI/routes, deployment configuration, migrations, and operational documentation
- Database state: `showmigrations --plan` on 2026-09-03 confirmed every repository migration applied on the configured Neon database; `makemigrations --check --dry-run` reported no model drift

The implementation snapshot remains valid when a later commit changes only documentation. Secrets are not reproduced here. Local and production settings are deliberately separate; see the configuration and risks sections.

### Maturity assessment

The project is **M3 (implementation-heavy)**. Authentication, permission administration, navigation, shared UI, domain models/migrations, transactional services, routed workflows, live dashboard/report queries, deployment configuration, and extensive domain tests exist. Cross-app stock and finance behavior remains architecture-sensitive. The final representative end-to-end technical gate (`E1-T07`) was explicitly deferred on 2026-09-03 and must not be described as passed.

## 2. Exact relevant tree

```text
pharmacy-management-system/
├── AGENTS.md
├── README.md
├── manage.py
├── pyproject.toml
├── uv.lock
├── package.json
├── package-lock.json
├── Dockerfile
├── build.sh
├── apps/
│   ├── accounts/
│   │   ├── management/commands/seed_dev_auth.py
│   │   ├── permissions.py, services.py, forms.py
│   │   ├── templates/accounts/{login,staff,permissions}/
│   │   ├── tests.py, test_administration.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── dashboard/
│   │   ├── queries.py
│   │   ├── templates/dashboard/
│   │   ├── tests.py, test_queries.py, test_template_integrity.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── dashboard_preview/     # isolated presentation-only comparison route
│   ├── core/                  # settings workflows, document numbers, pagination, UI, tests, migration 0001
│   ├── catalog/               # catalog workflows/UI, unit economics, tests, migration 0001
│   ├── parties/               # supplier/customer/prescriber workflows/UI, tests, migration 0001
│   ├── inventory/             # authoritative stock/FEFO services, UI, demo commands, tests, migrations 0001–0002
│   ├── purchasing/            # purchase draft/posting services and UI, tests, migration 0001
│   ├── prescriptions/         # prescription services/queries/UI, tests, migration 0001
│   ├── sales/                 # POS/completion/invoice services/UI, tests, migrations 0001–0002
│   ├── finance/               # payment and statement services/queries/UI, tests, migrations 0001–0002
│   ├── returns/               # customer/supplier return and refund services/UI, tests, migrations 0001–0002
│   └── reports/               # derived read-only report queries/UI; no business models
├── config/
│   ├── context_processors.py
│   ├── navigation.py
│   ├── settings.py
│   ├── settings_production.py
│   ├── urls.py
│   ├── urls_production.py
│   ├── visual_test_settings.py
│   ├── asgi.py
│   └── wsgi.py
├── assets/css/input.css
├── static/
│   ├── js/{custom-select,dashboard-charts,form-dirty-state,form-submit,modal,navigation-loading,registry-filters,settings-index,sidebar,theme,toast}.js
│   ├── logo-icon.png
│   ├── logo-white.png
│   └── logo.png
├── templates/
│   ├── base.html
│   ├── home.html
│   ├── layouts/{auth,dashboard}.html
│   └── components/{badge,button,card,checkbox,icon,input,modal,navigation_loading,pagination,registry_filters,select,sidebar,textarea,theme_init,theme_toggle,toast,topbar}.html
└── docs/
    ├── BACKUP_RUNBOOK.md
    ├── BRD.md
    ├── COMPONENTS.md
    ├── DEVELOPMENT_GUIDE.md
    ├── ERD.md
    ├── JIRA_BACKLOG.csv
    ├── DEPLOYMENT.md
    ├── DEMO_DATA.md
    ├── REPORTS.md
    ├── SALES_UI.md
    ├── FINANCE_UI.md
    ├── TEAM_DASHBOARD.html
    ├── task-status/
    └── REPO_IMPLEMENTATION_CONTEXT.md
```

Every listed app uses `name = "apps.<app>"`. All Phase 1 owning apps expose namespaced URLconfs from `config.urls`; `dashboard_preview` is isolated and presentation-only.

## 3. Current stack and versions

| Area                    | Repository evidence                                   |
| ----------------------- | ----------------------------------------------------- |
| Python                  | `requires-python = ">=3.13"`                          |
| Django                  | `6.1` in `uv.lock`; `django>=6.1` in `pyproject.toml` |
| Database URL parsing    | `dj-database-url 3.1.2`                               |
| PostgreSQL driver       | `psycopg 3.3.4` with binary extra                     |
| Environment loading     | `python-dotenv 1.2.3`                                 |
| Development reload      | `django-browser-reload 1.21.0`                        |
| Production server/static | `gunicorn 26.2.0`; `whitenoise 6.12.0`               |
| CSS                     | Tailwind CSS and `@tailwindcss/cli 4.3.3`             |
| Frontend process runner | `concurrently 10.0.5`                                 |
| Charts                   | Chart.js 4.5.1                                         |
| Templates/forms/ORM     | Django built-ins                                      |
| Browser behavior        | Vanilla JavaScript only                               |
| Python tooling          | `uv` and `uv.lock`                                    |
| Frontend tooling        | npm and `package-lock.json`                           |

No DRF, SPA framework, HTMX, Alpine.js, Bootstrap, task queue, Redis, or alternate authentication library is installed.

## 4. Authentication and authorization architecture

### Authentication flow

- Uses Django's built-in `User`; `AUTH_USER_MODEL` is not overridden.
- Uses username/password through Django's `AuthenticationForm`.
- Uses Django sessions with `SessionMiddleware` and `AuthenticationMiddleware`.
- `/accounts/login/` renders the custom login page, authenticates, and redirects to `dashboard:home`.
- `/accounts/logout/` is POST-only, CSRF-protected, and launched through the shared confirmation modal.
- `/dashboard/` is protected by `login_required` and `never_cache`.
- The Django admin remains at `/admin/`.

Self-service password reset/change, public registration, invitations, MFA, and login throttling are not implemented. Owner/Admin staff-account and role-permission administration screens are implemented.

### Groups and permissions

The exact groups are:

1. `Owner / Admin`
2. `Pharmacist`
3. `Inventory Manager`
4. `Accountant`

`seed_dev_auth` creates/fetches local users `owner`, `pharmacist`, `inventory`, and `accountant`, using `DEV_AUTH_PASSWORD`, and attaches each user to its group. It grants Owner / Admin every permission in the approved capability registry and grants `finance.view_financial_reports` to Accountant. It intentionally does not seed the rest of the operational-role matrix and does not make `owner` a superuser.

The approved BRD chooses **full group permissions** for Owner/Admin, not reliance on `is_superuser`. Owner/Admin permissions are deterministic; the final default operational-role permission assignment remains a documented team-lead decision.

`config.context_processors.dashboard_navigation` filters configured items through `request.user.has_perm()`, safely handles unavailable routes, and determines active state by namespace. Navigation visibility is not an authorization boundary; every protected view/action must enforce permissions server-side.

Implemented custom permission codenames are:

```text
purchasing.post_purchaseinvoice
sales.complete_sale
finance.post_customerpayment
finance.post_supplierpayment
returns.post_customerreturn
returns.post_supplierreturn
returns.process_refund
finance.view_financial_reports
```

`finance.view_financial_reports` is declared on `CustomerPayment`, avoiding a fake persistent reports model. Protected financial reports require it. Seed provisioning grants it to Owner / Admin and Accountant only; other operational capabilities are managed through the implemented Owner/Admin permission matrix until a deterministic default is approved.

## 5. App and module boundaries

| App             | Current implementation boundary                                                                                               |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `accounts`      | Login/logout plus Owner/Admin staff and permission administration; no project-owned model |
| `dashboard`     | Authenticated, permission-scoped live operational and commercial analytics; no project-owned model |
| `core`          | Settings/tax/payment-method workflows, UUID document numbering, and shared pagination |
| `catalog`       | Medicine/category/manufacturer/unit/barcode master-data workflows and unit economics |
| `parties`       | Supplier, customer, and prescriber master-data workflows |
| `inventory`     | Authoritative FEFO/stock mutation services, batch/movement visibility, and guarded demo data |
| `purchasing`    | Purchase-invoice draft and atomic posting/receiving workflows |
| `prescriptions` | Lightweight prescription workflows and POS warning query contract |
| `sales`         | POS lookup/drafts, atomic FEFO completion, invoice registry/detail/print, and allocations |
| `finance`       | Customer/supplier payment posting/reversal, invoice balances, and derived statements |
| `returns`       | Customer returns/refunds and exact-batch supplier-return workflows |
| `reports`       | Permission-scoped derived report queries and UI; no transaction models |

Do not create duplicate apps named after navigation labels. `catalog` owns Medicines; `parties` owns Suppliers and Customers; `sales`/`purchasing` own invoices; `finance` owns Payments; and `core` owns Settings.

## 6. Templates and UI structure

- `templates/base.html` is the HTML shell and loads the generated Tailwind CSS, toast markup, shared JavaScript, and reload script.
- Authentication pages extend `templates/layouts/auth.html`.
- Authenticated pages extend `templates/layouts/dashboard.html`, which composes the sidebar, topbar, mobile backdrop, and content region.
- Shared components live in `templates/components/`; `docs/COMPONENTS.md` is their usage contract.
- Shared JavaScript uses small `DOMContentLoaded` modules and `data-*` hooks.
- `assets/css/input.css` is the Tailwind source. `static/css/output.css` is generated, ignored, and must never be edited manually.
- The operational dashboard uses live, permission-scoped queries. The separate `/dashboard-preview/` route remains an intentionally illustrative design-comparison artifact.

Current navigation mapping:

| Label             | Namespace       | Permission currently configured   |
| ----------------- | --------------- | --------------------------------- |
| Dashboard         | `dashboard`     | none beyond login                 |
| Sales             | `sales`         | `sales.view_salesinvoice`         |
| Medicines         | `catalog`       | `catalog.view_medicine`           |
| Inventory         | `inventory`     | `inventory.view_medicinebatch`    |
| Suppliers         | `parties`       | `parties.view_supplier`           |
| Customers         | `parties`       | `parties.view_customer`           |
| Prescriptions     | `prescriptions` | `prescriptions.view_prescription` |
| Purchases         | `purchasing`    | `purchasing.view_purchaseinvoice` |
| Invoices          | `sales`         | `sales.view_salesinvoice`         |
| Payments          | `finance`       | either customer- or supplier-payment view permission |
| Returns & Refunds | `returns`       | either customer- or supplier-return view permission |
| Reports           | `reports`       | any permission for an available report |
| Settings          | `core`          | `core.change_pharmacysettings`    |
| Staff Accounts    | `accounts`      | Owner/Admin plus `auth.view_user` |
| Roles & Permissions | `accounts`    | Owner/Admin plus `auth.view_group` |

All Phase 1 business navigation destinations are routed. Navigation remains permission-filtered and each view repeats its server-side authorization checks.

## 7. Database and configuration conventions

- Normal configuration reads `DATABASE_URL` through `dj_database_url.config()` with `conn_max_age=600` and health checks.
- The repository pattern is compatible with Neon PostgreSQL; no database URL or credential is stored in this document.
- `.env`, `.env.*`, and `db.sqlite3` are ignored. `.env.example`/`.env.template` would be allowed but neither currently exists.
- `config.visual_test_settings` is a SQLite-only visual-test override, not the normal settings module.
- `USE_TZ = True` and `TIME_ZONE = "UTC"`; UTC is the explicit Phase 1 business timezone in the BRD/ERD.
- Local static assets use `STATIC_URL` plus `STATICFILES_DIRS`. No application media/upload workflow is enabled.
- `config.settings` remains development-only. `config.settings_production` requires environment-provided secret, hosts, trusted origins, and `DATABASE_URL`, disables debug/browser reload, enables secure cookies/HSTS, and serves collected static files through WhiteNoise. Render and local Docker procedures are documented in `docs/DEPLOYMENT.md`.

## 8. Existing models and migrations

All project-owned business models use UUID primary keys. Django auth/session/admin tables retain Django identifiers.

| App             | Existing models                                                                        | Existing schema migrations             |
| --------------- | -------------------------------------------------------------------------------------- | -------------------------------------- |
| `core`          | PharmacySettings, TaxRate, PaymentMethod                                               | `0001_initial`                         |
| `catalog`       | Category, Manufacturer, Medicine, MedicineUnit, MedicineBarcode                        | `0001_initial`                         |
| `parties`       | Supplier, Customer, Prescriber                                                         | `0001_initial`                         |
| `inventory`     | MedicineBatch, StockMovement                                                           | `0001_initial`, `0002_...source_line_unique` |
| `purchasing`    | PurchaseInvoice, PurchaseInvoiceLine                                                   | `0001_initial`                         |
| `prescriptions` | Prescription, PrescriptionItem                                                         | `0001_initial`                         |
| `sales`         | SalesInvoice, SalesInvoiceLine, SaleBatchAllocation                                    | `0001_initial`, `0002_...line_batch_unique` |
| `finance`       | CustomerPayment, SupplierPayment                                                       | `0001_initial`, `0002_alter_customerpayment_options` |
| `returns`       | CustomerReturn, CustomerReturnLine, CustomerRefund, SupplierReturn, SupplierReturnLine | `0001_initial`, `0002_...resalable...` |
| `reports`       | none                                                                                   | none beyond package marker             |

Established schema patterns include UUIDs, Decimal money/quantity fields, `PROTECT` for transaction relationships, `is_active` for deactivation, explicit status choices, model `clean()` validation, database checks/indexes, conditional uniqueness for posted/completed invoice numbers, and immutable-style stock history.

Follow-up migrations define uniqueness of `(sales_invoice_line, batch)` for sale allocations, uniqueness of non-null authoritative stock-movement source lines, and the finance-owned financial-report permission. Read-only verification on 2026-08-29 confirmed these migrations applied on Neon; no migration was applied by the verification task.

## 9. Reusable utilities and patterns

- `config.navigation.DASHBOARD_NAVIGATION` is the single sidebar definition.
- `config.context_processors.dashboard_navigation` handles permission filtering, URL resolution, and active state.
- `templates/components/` and `docs/COMPONENTS.md` define reusable presentation interfaces.
- `data-submit-form`/`data-submit-button` provide submit/loading behavior.
- The shared modal provides focus trapping, Escape/backdrop close, focus restoration, and confirmed POST actions.
- Django messages feed accessible toast notifications.
- Model `TextChoices`, `CheckConstraint`, `UniqueConstraint`, and named indexes are preferred over undocumented magic values.
- `apps.inventory.services` is the sole stock-mutation boundary; purchasing, sales, and returns delegate to it inside atomic transactions.
- `apps.core.document_numbers` owns deterministic UUID-derived document numbers.
- `apps.catalog.unit_economics` owns approved quantity and unit-price/cost conversions.
- Finance services own payment-only invoice balances; statement and report queries remain derived and read-only.

## 10. Integration constraints for Phase 1 features

1. Preserve Django `User`, sessions, Groups, exact role names, and current login/logout behavior.
2. Owner/Admin obtains full business access through assigned group permissions, not by requiring superuser status.
3. Use the existing owning apps and namespace mapping; do not create label-based duplicate apps.
4. `apps.inventory` is the only owner allowed to mutate `MedicineBatch.quantity_available_base`.
5. Every stock mutation and matching `StockMovement` must be created together.
6. Purchase posting, sale completion, returns, and payments use `transaction.atomic()` plus the targeted `select_for_update()` locks defined in the BRD/ERD.
7. Stock movements use the documented source mapping for purchase lines, sale allocations, customer-return lines, and supplier-return lines.
8. Document numbers use the approved deterministic full-UUID formats; do not add a sequence model in Phase 1.
9. Use `apps.catalog.unit_economics` for three-decimal base quantities, selected-unit selling prices, and four-decimal base acquisition costs. Use Decimal/`ROUND_HALF_UP` calculations and stored transaction snapshots; never use float for authoritative money.
10. Preserve posted/completed history; cancellation of an effective transaction requires a compensating workflow and is deferred.
11. `MANUAL_ADJUSTMENT_*` values are reserved and do not authorize a Phase 1 adjustment workflow.
12. No uploaded prescription attachment should be enabled until media storage, access control, and retention behavior are explicitly configured.

## 11. Files future AI agents must read

### Before any repository change

- `AGENTS.md`
- `docs/DEVELOPMENT_GUIDE.md`
- `docs/BRD.md`
- the relevant sections of `docs/ERD.md`
- this file

### Before authentication or authorization changes

- `apps/accounts/permissions.py`
- `apps/accounts/services.py`
- `apps/accounts/forms.py`
- `apps/accounts/views.py`
- `apps/accounts/urls.py`
- `apps/accounts/tests.py`
- `apps/accounts/test_administration.py`
- `apps/accounts/management/commands/seed_dev_auth.py`
- `config/context_processors.py`
- `config/navigation.py`
- `templates/components/sidebar.html`

### Before UI/navigation changes

- `docs/COMPONENTS.md`
- `templates/base.html`
- `templates/layouts/auth.html`
- `templates/layouts/dashboard.html`
- `templates/components/`
- `assets/css/input.css`
- `static/js/`
- `config/navigation.py`

### Before model, migration, or transaction-service changes

- `docs/ERD.md`
- `docs/BRD.md`
- every participating app's `models.py`, migrations, and tests
- `apps/inventory/models.py` for any stock-changing workflow
- `config/settings.py`

### Before settings, database, or deployment changes

- `docs/BACKUP_RUNBOOK.md`
- `docs/DEPLOYMENT.md`
- `config/settings.py`
- `config/settings_production.py`
- `config/urls_production.py`
- `pyproject.toml`
- `uv.lock`
- `package.json`
- `package-lock.json`
- `.gitignore`
- `.dockerignore`
- `Dockerfile`
- `build.sh`
- `README.md`

## 12. Current risks and implementation gaps

| Risk/gap                   | Current fact                                               | Required handling                                                                                           |
| -------------------------- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Operational-role defaults | Owner/Admin is deterministic, but the complete default Pharmacist/Inventory Manager/Accountant assignment is intentionally undecided | Keep the implemented permission matrix; do not silently invent defaults before the team lead decides |
| Final technical integration | Domain implementations and focused tests exist, but `E1-T07` was deferred on 2026-09-03 | Run and record the representative end-to-end and role-access gate before claiming final technical readiness |
| Applied schema verification | All repository migrations were shown as applied on the configured Neon database on 2026-09-03, with no model drift | Continue using coordinated, additive migrations; never rewrite shared migration history |
| Upload security            | No media configuration exists                              | Keep prescription attachments disabled unless storage/access/retention are approved                         |
| Environment separation     | Local settings are intentionally development-oriented; production uses strict environment-driven settings | Keep Render/Docker on `config.settings_production` and never commit secrets |
| Shared Neon coordination   | Baseline migrations now exist                              | Never rewrite applied migration history; coordinate and review every new migration                          |

## 13. Do Not Break checklist

- [ ] Keep Django's built-in `User`, sessions, and username/password authentication.
- [ ] Keep the exact groups: Owner / Admin, Pharmacist, Inventory Manager, Accountant.
- [ ] Enforce authorization server-side; navigation visibility is not security.
- [ ] Preserve POST-only, CSRF-protected logout and the current login flow.
- [ ] Do not create duplicate apps for navigation labels.
- [ ] Keep shared navigation in `config/navigation.py` and shared UI in the existing layouts/components.
- [ ] Do not edit generated `static/css/output.css`.
- [ ] Keep PostgreSQL/Neon configuration environment-driven and do not expose secrets.
- [ ] Use UUIDs and Decimal conventions from the ERD.
- [ ] Keep inventory quantity mutation inside `apps.inventory` services with a matching movement.
- [ ] Use atomic transactions and targeted locks for stock and financial posting.
- [ ] Preserve posted/completed snapshots and transaction history.
- [ ] Do not use reserved manual-adjustment codes as a shortcut.
- [ ] Do not reintroduce deferred Phase 2 entities without team approval.
- [ ] Do not rewrite existing migrations; add reviewed migrations for schema corrections.
- [ ] Run Django checks/tests and relevant frontend validation before merging implementation work.
