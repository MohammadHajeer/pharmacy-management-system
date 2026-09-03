# Development Guide

This guide describes how teammates should add features without breaking the project's Django, Tailwind CSS, and vanilla JavaScript architecture. AI coding agents must also follow the project-wide rules in `AGENTS.md`.

## Quick start

Requirements: Python 3.13+, `uv`, Node.js, and `npm`.

```bash
uv sync
npm install
npm run migrate
npm run dev
```

`npm run dev` starts the Django development server and Tailwind watcher. The local application is available at `http://127.0.0.1:8000/`.

It first builds CSS and copies the installed Chart.js browser assets. For direct
`runserver` use or deployment, run `npm run build` before serving/collecting static
files. See [`DASHBOARD.md`](DASHBOARD.md) for dashboard definitions and asset loading.

### Local production-style Docker testing

The normal development loop remains `npm run dev`. Use Docker when you need to
check the production settings, Gunicorn, WhiteNoise, built static files, and the
Neon connection together:

```bash
npm run docker:build
npm run docker:run
```

The run command reads the private, gitignored `docker.env` and publishes the
container at [http://localhost:8000](http://localhost:8000). Use
`npm run docker:stop` from another terminal to stop it. Docker does not create a
PostgreSQL service, apply migrations, or seed development/demo data. See
[`DEPLOYMENT.md`](DEPLOYMENT.md) for the required environment variables, the
manual migration command, and the distinction between local Docker and Render.

## Project structure

```text
apps/                         Feature apps
  accounts/                   Login and logout
  dashboard/                  Authenticated dashboard foundation
  <feature>/
    migrations/               Generated schema migrations
    templates/<feature>/      Feature-owned templates
    admin.py                  Django admin registration
    apps.py                   App configuration
    forms.py                  Forms and ModelForms, when needed
    models.py                 Feature-owned data models
    tests.py                  Feature tests (or a tests/ package)
    urls.py                   Namespaced feature routes
    views.py                  Request handling and authorization
assets/css/input.css          Tailwind entry point and theme tokens
config/                       Project settings, root URLs, and navigation
docs/                         Team and component documentation
static/js/                    Shared vanilla JavaScript
templates/                    Shared project templates
  components/                 Reusable UI components
  layouts/                    Dashboard and authentication layouts
```

Keep feature behavior inside its owning app. Project-wide configuration belongs in `config/`; reusable presentation belongs in shared templates or `static/js/`.

## Phase 1 model ownership

The approved Phase 1 business models have one authoritative owning app:

| App             | Models owned                                                                                     |
| --------------- | ------------------------------------------------------------------------------------------------ |
| `core`          | `PharmacySettings`, `TaxRate`, `PaymentMethod`                                                   |
| `catalog`       | `Category`, `Manufacturer`, `Medicine`, `MedicineUnit`, `MedicineBarcode`                        |
| `parties`       | `Supplier`, `Customer`, `Prescriber`                                                             |
| `inventory`     | `MedicineBatch`, `StockMovement`                                                                 |
| `purchasing`    | `PurchaseInvoice`, `PurchaseInvoiceLine`                                                         |
| `prescriptions` | `Prescription`, `PrescriptionItem`                                                               |
| `sales`         | `SalesInvoice`, `SalesInvoiceLine`, `SaleBatchAllocation`                                        |
| `finance`       | `CustomerPayment`, `SupplierPayment`                                                             |
| `returns`       | `CustomerReturn`, `CustomerReturnLine`, `CustomerRefund`, `SupplierReturn`, `SupplierReturnLine` |
| `reports`       | No database models; reports are derived queries/services                                         |

Keep the inventory boundary explicit: `Medicine` is the product definition and is not physical inventory. `MedicineBatch` is physical stock and its acquisition-cost layer. `StockMovement` is append-style stock-change history. Future stock-changing workflows must update `MedicineBatch.quantity_available_base` only through `apps.inventory` services and create the corresponding `StockMovement` in the same database transaction.

Unit conversion follows one shared Phase 1 rule: selected quantity × the six-decimal conversion snapshot is quantized to a three-decimal base quantity with `ROUND_HALF_UP`. `Medicine.default_selling_price` is the base-unit price; sales snapshot the derived selected-unit price. Purchase lines snapshot selected-unit cost, while batches store the cost divided by the conversion snapshot and quantized to four decimals. Use `apps.catalog.unit_economics` rather than duplicating these calculations.

## Extending the existing feature apps

All approved Phase 1 owning apps already exist and are registered. Do not create duplicate apps such as `apps.medicines`, `apps.suppliers`, `apps.customers`, `apps.invoices`, `apps.payments`, or `apps.settings`; those navigation concepts belong to `catalog`, `parties`, `sales`/`purchasing`, `finance`, and `core` respectively.

For work in an existing app:

1. confirm ownership in the table above and in `docs/ERD.md`;
2. add forms, services, queries, views, URLs, templates, and tests inside that owning app;
3. include a URLconf from `config/urls.py` only when the app exposes a routed feature;
4. update the existing item in `config/navigation.py` rather than adding a duplicate label;
5. coordinate schema changes and generate a new migration without rewriting existing migration history.

A new Django app requires explicit architecture approval and an update to the BRD/ERD ownership tables first. Create `forms.py`, service modules, or query modules only when the feature needs them; avoid empty layers or new architectural patterns without a concrete use.

## Models, forms, views, URLs, templates, and tests

- **Models:** Keep the feature's data model and relationships in `apps/<feature>/models.py`. Follow the agreed BRD and ERD; do not invent fields or workflows.
- **Forms:** Use Django `Form` or `ModelForm` classes in `apps/<feature>/forms.py`. Rely on Django validation and render errors accessibly.
- **Views:** Keep request handling in `apps/<feature>/views.py`. Require login and enforce permissions on the server.
- **URLs:** Define `app_name` and stable route names in `apps/<feature>/urls.py`. Reverse namespaced URLs instead of hardcoding paths.
- **Templates:** Put feature pages in `apps/<feature>/templates/<feature>/`. Use shared layouts and components.
- **Tests:** Test models, form validation, view authentication and authorization, response behavior, URL reversing, and important workflows. Prefer Django's test tools and keep test data local to each test.

Split a module into a package only when its size or distinct responsibilities justify it.

## Layouts and reusable components

Dashboard pages should normally begin with:

```django
{% extends "layouts/dashboard.html" %}
```

Authentication pages should begin with:

```django
{% extends "layouts/auth.html" %}
```

The dashboard layout already includes the sidebar and topbar. Do not copy them into feature pages. Reuse templates in `templates/components/` with `{% include %}` and review `docs/COMPONENTS.md` for supported component options.

If a UI pattern is used only by one feature, keep it in that feature. Move it to `templates/components/` only when it is genuinely reusable and its interface can remain stable.

## URL namespaces

Every feature URLconf must set an application namespace:

```python
app_name = "catalog"

urlpatterns = [
    path("medicines/", views.medicine_list, name="medicine-list"),
]
```

Refer to it as `catalog:medicine-list` in Python, templates, redirects, tests, and navigation. Namespaces prevent collisions and power the sidebar's active-state handling.

The stable mapping is: Medicines → `catalog`; Suppliers/Customers → `parties`; Invoices → `sales` or `purchasing` according to document type; Payments → `finance`; Settings → `core`. Keep the mappings in `config/navigation.py`, `docs/BRD.md`, and `docs/ERD.md` synchronized.

## Sidebar navigation

Configure sidebar items once in `config/navigation.py`. `config/context_processors.py` then:

- resolves each namespaced URL;
- leaves not-yet-implemented routes disabled;
- filters items by Django permission; and
- matches explicit `active_url_names` within the current namespace, falling back to namespace matching only for a uniquely configured area.

Do not pass duplicate link lists from views or hardcode them in feature templates. When a feature becomes available, set its `url_name`, preserve its `namespace`, and set its Django permission when the model permission exists.

The financial Reports navigation item uses `finance.view_financial_reports`. The permission is declared on `CustomerPayment` because `apps.reports` intentionally has no persistent model. Financial report views must enforce the same permission server-side. Deterministic group provisioning must grant it to Owner / Admin and Accountant only; Pharmacist and Inventory Manager retain scoped operational or inventory-report access through permissions in their owning apps.

## Authentication, groups, and permissions

The project uses Django's built-in user model, sessions, groups, and permissions. Do not add a custom role model or another authentication system.

Current group names are exact:

- Owner / Admin
- Pharmacist
- Inventory Manager
- Accountant

Groups describe job responsibilities and collect permissions. The sidebar checks the resulting Django permissions, but a hidden link is not an authorization boundary. Protected views must enforce access, preferably with Django model permissions such as `catalog.view_medicine`, `catalog.add_medicine`, `catalog.change_medicine`, and `catalog.delete_medicine`.

For example, use `permission_required(..., raise_exception=True)` for function views or `PermissionRequiredMixin` for class-based views. Add tests proving that anonymous and unauthorized users cannot reach protected actions. Superuser behavior should remain compatible with Django defaults.

Do not create a reports table solely for permissions. Use `finance.view_financial_reports` for financial reports and keep report data as derived queries/services.

## Development accounts

The repository does not provide or track shared credentials. For the four standard local users/groups, set a local-only password and run:

```bash
$env:DEV_AUTH_PASSWORD = "use-a-unique-local-password"
uv run manage.py seed_dev_auth
```

The command creates/fetches the four users/groups, grants Owner / Admin every permission in the approved capability registry, and assigns `finance.view_financial_reports` to Accountant. It intentionally does not yet seed the remaining operational-role permissions. An Owner/Admin can configure those permissions in the Roles & Permissions workspace (or through Django admin during development) until the team lead approves deterministic defaults. Test Owner/Admin as a normal group member, not only as a superuser, because the approved design grants full business access through group permissions.

Use clearly fake data and unique local passwords. Never commit credentials, `.env` files, or `db.sqlite3`, and do not depend on another developer's local database. Automated tests must create their own users, groups, permissions, and records.

For deterministic catalog and inventory development records, see
[`DEMO_DATA.md`](DEMO_DATA.md). The guarded `seed_demo_data` command creates
complete historical purchase fixtures without changing production posting rules.
Review its prerequisites and database target before running it manually.

## Feature ownership

Each ticket should identify one owning feature app and one primary developer. The owner is responsible for the feature's models, forms, views, URLs, templates, migrations, and tests through review.

Coordinate before changing shared surfaces such as `config/settings.py`, `config/urls.py`, `config/navigation.py`, shared layouts/components, or cross-app models. Keep pull requests focused on one feature or closely related change, and do not overwrite another teammate's in-progress work.

## Tailwind CSS

- Use Tailwind CSS v4 and existing tokens from `assets/css/input.css`.
- Prefer the established `primary`, `sidebar`, semantic, slate, and chart palette; do not add arbitrary brand colors.
- Write complete static classes. Tailwind cannot reliably detect dynamically assembled classes such as `bg-{{ color }}-500`.
- Update `assets/css/input.css` only for justified project-wide tokens or component styles.
- Never edit `static/css/output.css`; generate it with `npm run build:css`.
- Check responsive, focus, disabled, validation, and empty states for changed UI.

## JavaScript

Use minimal, progressively enhanced vanilla JavaScript. Put shared scripts in `static/js/`, use `data-*` attributes for hooks, and keep templates usable without unnecessary client-side state. Avoid large inline scripts, global variables, duplicated handlers, and new frontend frameworks.

Match the existing accessibility patterns: keyboard operation, focus handling, ARIA state, and reduced-motion support where animation is used.

## Database and migrations

- Change models only within the assigned feature and agreed BRD/ERD scope.
- Use `uv run manage.py makemigrations <app_name>` and review the generated migration.
- Apply migrations locally with `uv run manage.py migrate`.
- Do not edit generated migrations manually unless Django cannot express the required data/schema operation.
- Do not rewrite already-shared migrations without team agreement; add a new migration instead.
- Consider data integrity, indexes, deletion behavior, defaults, nullability, and backward compatibility.
- Transactional stock and payment services must follow the targeted `select_for_update()` and `transaction.atomic()` rules in the BRD/ERD; `transaction.atomic()` alone does not prevent stale availability/balance decisions.
- Never commit `db.sqlite3` or use production data for development or tests.

## Git workflow

1. Start from the team's agreed integration branch and create a short-lived feature branch.
2. Keep changes limited to the assigned ticket; separate unrelated cleanup.
3. Review `git diff` and run relevant checks before requesting review.
4. Use a clear commit subject such as `feat: add medicine catalog` or `fix: enforce inventory permissions`.
5. Open a focused pull request describing behavior, migrations, tests, and follow-up work.
6. Resolve conflicts carefully; do not delete or replace another developer's work.

Do not commit generated CSS, the local database, environments, secrets, or editor artifacts. AI agents must not commit, push, merge, or rebase unless the user explicitly requests it.

## Feature-done checklist

- [ ] The change matches the ticket and agreed BRD/ERD.
- [ ] Code lives in the owning app and unrelated files were not refactored.
- [ ] URLs are namespaced and reversed by name.
- [ ] Dashboard/auth pages use the correct shared layout.
- [ ] Existing components and theme tokens are reused.
- [ ] Views enforce authentication and permissions; navigation visibility is not treated as authorization.
- [ ] Forms validate input and show useful errors.
- [ ] Model changes have reviewed migrations.
- [ ] Tests cover success, validation, authentication, authorization, and key edge cases.
- [ ] `uv run manage.py check` passes.
- [ ] Relevant Django tests pass (`uv run manage.py test` or a focused app/test path).
- [ ] `npm run build:css` passes for template or styling changes.
- [ ] Changed UI was checked at relevant screen sizes and with keyboard navigation.
- [ ] No secrets, local database, generated CSS, or unrelated files are included.
- [ ] Documentation is updated when architecture or reusable behavior changes.
- [ ] Intentionally deferred work is recorded in the handoff or ticket.

## Using AI coding agents

Before asking any AI coding agent to work on the project, open with an instruction similar to:

> Read `AGENTS.md` and `docs/DEVELOPMENT_GUIDE.md` before making changes. Stay within this assigned feature/ticket and follow the project architecture.

Claude-based agents should also read `CLAUDE.md`. Give the agent the ticket, owning feature, acceptance criteria, relevant BRD/ERD references, allowed files, and expected checks. Review all generated changes; the developer remains responsible for scope, security, migrations, tests, and correctness.
