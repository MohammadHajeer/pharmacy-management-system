# Repository Implementation Context

This document records the current application foundation and Phase 1 schema scaffold so architecture, implementation, and AI-assisted work preserve what is already built. Repository facts are authoritative; planned behavior that is not implemented is identified explicitly.

## 1. Repository snapshot inspected

- Repository: `https://github.com/MohammadHajeer/pharmacy-management-system.git`
- Branch: `main`
- Implementation commit: `5a4a98bfe9be324128dcfcdd47e39a90c38ee5b5`
- Commit date: `2026-08-28T23:28:38+03:00`
- Commit subject: `feat(auth): enhance login experience with toast notifications for errors`
- Inspection date: 2026-08-29
- Scope of this refresh: documentation only; no application code or migration was changed

The implementation snapshot remains valid when a later commit changes only documentation. Secrets are not reproduced here. The tracked settings file currently contains development-only values; see the risks section.

### Maturity assessment

The project is **M1 (foundation with an approved schema scaffold)**. Authentication, navigation, shared UI, domain apps, baseline models, migrations, and model-level tests exist. Most transactional services, forms, routed feature workflows, real dashboard queries, and end-to-end tests do not yet exist. Cross-app financial and inventory work remains architecture-sensitive.

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
├── apps/
│   ├── accounts/
│   │   ├── management/commands/seed_dev_auth.py
│   │   ├── templates/accounts/login.html
│   │   ├── tests.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── dashboard/
│   │   ├── templates/dashboard/index.html
│   │   ├── tests.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── core/                  # models, admin, tests, migrations/0001_initial.py
│   ├── catalog/               # models/admin/tests/migration plus URLs/view/medicine-list template
│   ├── parties/               # models, admin, tests, migrations/0001_initial.py
│   ├── inventory/             # models, admin, tests, migrations/0001_initial.py
│   ├── purchasing/            # models, admin, tests, migrations/0001_initial.py
│   ├── prescriptions/         # models, admin, tests, migrations/0001_initial.py
│   ├── sales/                 # models, admin, tests, migrations/0001_initial.py
│   ├── finance/               # models, admin, tests, migrations/0001_initial.py
│   ├── returns/               # models/admin/tests plus migrations/0001 and 0002
│   └── reports/               # placeholder app; no business models
├── config/
│   ├── context_processors.py
│   ├── navigation.py
│   ├── settings.py
│   ├── urls.py
│   ├── visual_test_settings.py
│   ├── asgi.py
│   └── wsgi.py
├── assets/css/input.css
├── static/
│   ├── js/{form-submit,modal,sidebar,toast}.js
│   ├── logo-icon.png
│   ├── logo-white.png
│   └── logo.png
├── templates/
│   ├── base.html
│   ├── home.html
│   ├── layouts/{auth,dashboard}.html
│   └── components/{badge,button,card,input,modal,select,sidebar,textarea,toast,topbar}.html
└── docs/
    ├── BRD.md
    ├── COMPONENTS.md
    ├── DEVELOPMENT_GUIDE.md
    ├── ERD.md
    ├── JIRA_BACKLOG.csv
    └── REPO_IMPLEMENTATION_CONTEXT.md
```

Every listed app uses `name = "apps.<app>"`. Only `accounts`, `dashboard`, and `catalog` currently expose URLconfs; only `catalog` has a routed Phase 1 business page.

## 3. Current stack and versions

| Area | Repository evidence |
| --- | --- |
| Python | `requires-python = ">=3.13"` |
| Django | `6.1` in `uv.lock`; `django>=6.1` in `pyproject.toml` |
| Database URL parsing | `dj-database-url 3.1.2` |
| PostgreSQL driver | `psycopg 3.3.4` with binary extra |
| Environment loading | `python-dotenv 1.2.3` |
| Development reload | `django-browser-reload 1.21.0` |
| CSS | Tailwind CSS and `@tailwindcss/cli 4.3.3` |
| Frontend process runner | `concurrently 10.0.5` |
| Templates/forms/ORM | Django built-ins |
| Browser behavior | Vanilla JavaScript only |
| Python tooling | `uv` and `uv.lock` |
| Frontend tooling | npm and `package-lock.json` |

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

Password reset/change, registration, invitations, MFA, login throttling, and custom staff-management screens are not implemented.

### Groups and permissions

The exact groups are:

1. `Owner / Admin`
2. `Pharmacist`
3. `Inventory Manager`
4. `Accountant`

`seed_dev_auth` creates/fetches local users `owner`, `pharmacist`, `inventory`, and `accountant`, using `DEV_AUTH_PASSWORD`, and attaches each user to its group. It does not assign model/custom permissions and does not make `owner` a superuser.

The approved BRD chooses **full group permissions** for Owner/Admin, not reliance on `is_superuser`. Permission provisioning is therefore still an implementation task.

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
```

The reports permission is documented for implementation as `reports.view_financial_reports`; `apps.reports` currently has no business model declaring it.

## 5. App and module boundaries

| App | Current implementation boundary |
| --- | --- |
| `accounts` | Login/logout, auth tests, and development user/group seed command; no project-owned model |
| `dashboard` | Authenticated dashboard shell with permission-filtered illustrative data; no project-owned model |
| `core` | `PharmacySettings`, `TaxRate`, `PaymentMethod` models and initial migration |
| `catalog` | Medicine master-data models plus the implemented medicine-list route/view/template |
| `parties` | `Supplier`, `Customer`, `Prescriber` models and initial migration |
| `inventory` | `MedicineBatch`, append-style `StockMovement`, constraints/indexes; transactional services not yet implemented |
| `purchasing` | `PurchaseInvoice`, `PurchaseInvoiceLine`, custom posting permission; posting service/UI not yet implemented |
| `prescriptions` | `Prescription`, `PrescriptionItem`; routed workflows not yet implemented |
| `sales` | `SalesInvoice`, `SalesInvoiceLine`, `SaleBatchAllocation`, completion permission; POS/completion services not yet implemented |
| `finance` | Customer/supplier payment models and posting permissions; balance services not yet implemented |
| `returns` | Customer/supplier returns and customer refund models; posting/refund services not yet implemented |
| `reports` | Placeholder app with no transaction models; report queries/views not yet implemented |

Do not create duplicate apps named after navigation labels. `catalog` owns Medicines; `parties` owns Suppliers and Customers; `sales`/`purchasing` own invoices; `finance` owns Payments; and `core` owns Settings.

## 6. Templates and UI structure

- `templates/base.html` is the HTML shell and loads the generated Tailwind CSS, toast markup, shared JavaScript, and reload script.
- Authentication pages extend `templates/layouts/auth.html`.
- Authenticated pages extend `templates/layouts/dashboard.html`, which composes the sidebar, topbar, mobile backdrop, and content region.
- Shared components live in `templates/components/`; `docs/COMPONENTS.md` is their usage contract.
- Shared JavaScript uses small `DOMContentLoaded` modules and `data-*` hooks.
- `assets/css/input.css` is the Tailwind source. `static/css/output.css` is generated, ignored, and must never be edited manually.
- The dashboard currently displays explicit illustrative values filtered by permission. It is not yet connected to live pharmacy queries.

Current navigation mapping:

| Label | Namespace | Permission currently configured |
| --- | --- | --- |
| Dashboard | `dashboard` | none beyond login |
| Sales | `sales` | `sales.view_salesinvoice` |
| Medicines | `catalog` | `catalog.view_medicine` |
| Inventory | `inventory` | `inventory.view_medicinebatch` |
| Suppliers | `parties` | `parties.view_supplier` |
| Customers | `parties` | `parties.view_customer` |
| Prescriptions | `prescriptions` | `prescriptions.view_prescription` |
| Purchases | `purchasing` | `purchasing.view_purchaseinvoice` |
| Invoices | `sales` | `sales.view_salesinvoice` |
| Payments | `finance` | `finance.view_customerpayment` |
| Returns & Refunds | `returns` | `returns.view_customerreturn` |
| Reports | `reports` | not yet configured |
| Settings | `core` | `core.change_pharmacysettings` |

Most non-catalog business links remain disabled because their `url_name` is `None`.

## 7. Database and configuration conventions

- Normal configuration reads `DATABASE_URL` through `dj_database_url.config()` with `conn_max_age=600` and health checks.
- The repository pattern is compatible with Neon PostgreSQL; no database URL or credential is stored in this document.
- `.env`, `.env.*`, and `db.sqlite3` are ignored. `.env.example`/`.env.template` would be allowed but neither currently exists.
- `config.visual_test_settings` is a SQLite-only visual-test override, not the normal settings module.
- `USE_TZ = True` and `TIME_ZONE = "UTC"`; UTC is the explicit Phase 1 business timezone in the BRD/ERD.
- Static assets use `STATIC_URL` plus `STATICFILES_DIRS`. No application media/upload configuration is present.
- The settings file currently has `DEBUG = True`, empty `ALLOWED_HOSTS`, and a hard-coded development secret key. These are development-only and must be environment-driven before deployment.

## 8. Existing models and migrations

All project-owned business models use UUID primary keys. Django auth/session/admin tables retain Django identifiers.

| App | Existing models | Existing schema migrations |
| --- | --- | --- |
| `core` | PharmacySettings, TaxRate, PaymentMethod | `0001_initial` |
| `catalog` | Category, Manufacturer, Medicine, MedicineUnit, MedicineBarcode | `0001_initial` |
| `parties` | Supplier, Customer, Prescriber | `0001_initial` |
| `inventory` | MedicineBatch, StockMovement | `0001_initial` |
| `purchasing` | PurchaseInvoice, PurchaseInvoiceLine | `0001_initial` |
| `prescriptions` | Prescription, PrescriptionItem | `0001_initial` |
| `sales` | SalesInvoice, SalesInvoiceLine, SaleBatchAllocation | `0001_initial` |
| `finance` | CustomerPayment, SupplierPayment | `0001_initial` |
| `returns` | CustomerReturn, CustomerReturnLine, CustomerRefund, SupplierReturn, SupplierReturnLine | `0001_initial`, `0002_...resalable...` |
| `reports` | none | none beyond package marker |

Established schema patterns include UUIDs, Decimal money/quantity fields, `PROTECT` for transaction relationships, `is_active` for deactivation, explicit status choices, model `clean()` validation, database checks/indexes, conditional uniqueness for posted/completed invoice numbers, and immutable-style stock history.

The approved ERD now requires two follow-up constraints before the related services are completed: uniqueness of `(sales_invoice_line, batch)` for sale allocations and uniqueness of a non-null stock-movement source line. They are not present at the inspected implementation commit.

## 9. Reusable utilities and patterns

- `config.navigation.DASHBOARD_NAVIGATION` is the single sidebar definition.
- `config.context_processors.dashboard_navigation` handles permission filtering, URL resolution, and active state.
- `templates/components/` and `docs/COMPONENTS.md` define reusable presentation interfaces.
- `data-submit-form`/`data-submit-button` provide submit/loading behavior.
- The shared modal provides focus trapping, Escape/backdrop close, focus restoration, and confirmed POST actions.
- Django messages feed accessible toast notifications.
- Model `TextChoices`, `CheckConstraint`, `UniqueConstraint`, and named indexes are preferred over undocumented magic values.
- Business transaction services are not established yet; implement them deliberately rather than putting cross-record posting logic into views or model `save()` methods.

## 10. Integration constraints for Phase 1 features

1. Preserve Django `User`, sessions, Groups, exact role names, and current login/logout behavior.
2. Owner/Admin obtains full business access through assigned group permissions, not by requiring superuser status.
3. Use the existing owning apps and namespace mapping; do not create label-based duplicate apps.
4. `apps.inventory` is the only owner allowed to mutate `MedicineBatch.quantity_available_base`.
5. Every stock mutation and matching `StockMovement` must be created together.
6. Purchase posting, sale completion, returns, and payments use `transaction.atomic()` plus the targeted `select_for_update()` locks defined in the BRD/ERD.
7. Stock movements use the documented source mapping for purchase lines, sale allocations, customer-return lines, and supplier-return lines.
8. Document numbers use the approved deterministic full-UUID formats; do not add a sequence model in Phase 1.
9. Use Decimal/`ROUND_HALF_UP` calculations and stored transaction snapshots; never use float for authoritative money.
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

- `apps/accounts/views.py`
- `apps/accounts/urls.py`
- `apps/accounts/tests.py`
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

- `config/settings.py`
- `pyproject.toml`
- `uv.lock`
- `package.json`
- `package-lock.json`
- `.gitignore`
- `README.md`

## 12. Current risks and implementation gaps

| Risk/gap | Current fact | Required handling |
| --- | --- | --- |
| Permission provisioning | Groups are seeded without permissions | Add deterministic, tested group-permission provisioning before feature authorization is considered complete |
| Transaction races | No posting/allocation/payment services exist yet | Use the BRD/ERD targeted row-lock rules from the first implementation |
| Allocation/return identity | Baseline allocation schema lacks line/batch uniqueness | Add a reviewed migration before customer-return services depend on the pair |
| Movement idempotence | Generic source fields lack source-line uniqueness | Add the documented conditional uniqueness constraint before posting services |
| Document numbers | Models validate uniqueness but do not generate identifiers | Implement the approved UUID-derived service helper centrally |
| Dashboard truth | Values are illustrative samples | Replace with permission-scoped queries; never present sample values as live data |
| Navigation coverage | Only catalog has a Phase 1 business route | Add routes incrementally within owning apps and preserve disabled-link behavior |
| Upload security | No media configuration exists | Keep prescription attachments disabled unless storage/access/retention are approved |
| Development security | Hard-coded development secret, `DEBUG=True`, empty hosts | Move deployment values to environment configuration before production |
| Shared Neon coordination | Baseline migrations now exist | Never rewrite applied migration history; coordinate and review every new migration |

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
