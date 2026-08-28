# Repository Implementation Context

This document records the implementation foundation that existed before pharmacy business features were added. It is intended for architecture, BRD, ERD, task planning, and future AI/developer handoffs. Repository facts are separated from planning-context comparisons so that an unimplemented proposal is not mistaken for existing code.

## 1. Repository snapshot inspected

- Repository: `https://github.com/MohammadHajeer/pharmacy-management-system.git`
- Branch: `main`
- Commit: `d45b168fc7f526d6767b52fd527a34d14482e781`
- Commit date: `2026-08-28T11:32:30+03:00`
- Commit author: Mohammad Hajeer
- Commit subject: `feat: implement logout confirmation modal and loading state in sidebar`
- Inspection date: 2026-08-28
- Working tree before this report: clean and aligned with `origin/main`
- Scope of change made by this inspection: this Markdown file only

No application code, model, migration, dependency, generated CSS, database, or deployment file was changed. No migrations were created or run, and nothing was committed or pushed.

Security note: the repository contains a hard-coded development `SECRET_KEY`. Its value is deliberately not copied into this report. No `.env` file or database URL was inspected or recorded.

### Evidence and confidence

The repository itself is authoritative for the current implementation. `AGENTS.md` is the repository's source of truth for project-wide AI rules, followed by `docs/DEVELOPMENT_GUIDE.md` and relevant feature/component documentation.

The “planned-specification conflicts” section also compares the repository with the referenced project conversation and its `phase-1.txt` attachment. Those planning materials are not tracked in this repository and must not be treated as implemented behavior. Where the repository cannot answer a question, this document says **not determinable**.

### Maturity assessment for implementation planning

This is an **M1 foundation** project: the Django project, authentication flow, role-aware navigation, shared UI system, dependency tooling, tests, and team conventions exist, but business-domain boundaries, BRD/ERD, domain models, service contracts, and project-owned migrations do not. New business schema work is therefore architecture-sensitive even though the codebase is small.

## 2. Exact tracked tree at the inspected commit

The tree below lists all 62 tracked files at commit `d45b168`. `.git/` and ignored/generated files are omitted. `docs/REPO_IMPLEMENTATION_CONTEXT.md` is the only file added after the snapshot and is shown as such.

```text
pharmacy-management-system/
├── .gitignore
├── .vscode/
│   └── settings.json
├── AGENTS.md
├── CLAUDE.md
├── README.md
├── apps/
│   ├── __init__.py
│   ├── accounts/
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── management/
│   │   │   ├── __init__.py
│   │   │   └── commands/
│   │   │       ├── __init__.py
│   │   │       └── seed_dev_auth.py
│   │   ├── migrations/
│   │   │   └── __init__.py
│   │   ├── models.py
│   │   ├── templates/
│   │   │   └── accounts/
│   │   │       └── login.html
│   │   ├── tests.py
│   │   ├── urls.py
│   │   └── views.py
│   └── dashboard/
│       ├── __init__.py
│       ├── admin.py
│       ├── apps.py
│       ├── migrations/
│       │   └── __init__.py
│       ├── models.py
│       ├── templates/
│       │   └── dashboard/
│       │       └── index.html
│       ├── tests.py
│       ├── urls.py
│       └── views.py
├── assets/
│   └── css/
│       └── input.css
├── config/
│   ├── __init__.py
│   ├── asgi.py
│   ├── context_processors.py
│   ├── navigation.py
│   ├── settings.py
│   ├── urls.py
│   ├── visual_test_settings.py
│   └── wsgi.py
├── docs/
│   ├── COMPONENTS.md
│   ├── DEVELOPMENT_GUIDE.md
│   └── REPO_IMPLEMENTATION_CONTEXT.md  # added by this inspection
├── manage.py
├── package-lock.json
├── package.json
├── pyproject.toml
├── static/
│   ├── favicon.svg
│   └── js/
│       ├── form-submit.js
│       ├── modal.js
│       ├── sidebar.js
│       └── toast.js
├── templates/
│   ├── base.html
│   ├── components/
│   │   ├── badge.html
│   │   ├── button.html
│   │   ├── card.html
│   │   ├── input.html
│   │   ├── modal.html
│   │   ├── select.html
│   │   ├── sidebar.html
│   │   ├── textarea.html
│   │   ├── toast.html
│   │   └── topbar.html
│   ├── home.html
│   └── layouts/
│       ├── auth.html
│       └── dashboard.html
└── uv.lock
```

Generated/ignored paths include `.venv/`, Python caches, `.env*` except explicit templates, `db.sqlite3`, `node_modules/`, `static/css/output.css`, `staticfiles/`, test/coverage caches, build output, and common OS files.

## 3. Current stack and discoverable versions

| Area | Current repository choice | Version evidence |
|---|---|---|
| Language | Python | `>=3.13` in `pyproject.toml` and `uv.lock`; exact developer/runtime patch version is not pinned |
| Web framework | Full-stack Django with templates, forms/auth, ORM, sessions, and admin | Declared `django>=6.1`; locked to `6.1` |
| Database URL parsing | `dj-database-url` | Declared `>=3.1.2`; locked to `3.1.2` |
| PostgreSQL driver | Psycopg 3 binary distribution | `psycopg[binary]>=3.3.4`; `psycopg` and `psycopg-binary` locked to `3.3.4` |
| Environment loading | `python-dotenv` | Declared `>=1.2.3`; locked to `1.2.3` |
| Development reload | `django-browser-reload` | Declared `>=1.21.0`; locked to `1.21.0` |
| Templates/UI | Django Templates + Tailwind CSS v4 | `tailwindcss` and `@tailwindcss/cli` locked to `4.3.3` |
| Browser behavior | Vanilla JavaScript | No JavaScript framework dependency |
| Concurrent dev tooling | `concurrently` | Locked to `10.0.5`; this package declares Node `>=22` |
| Python dependency manager | `uv` | Lockfile present; `uv` executable version is not pinned |
| Frontend package manager | npm | `package-lock.json` lockfile version 3; npm version is not pinned |

The Python project version is `0.1.0`; the npm package version is `1.0.0`. No semantic relationship between these two version fields is documented.

Explicitly prohibited by `AGENTS.md` unless approved: Django REST Framework, React, Vue, Angular, HTMX, Alpine.js, Bootstrap/another CSS framework, another authentication system, and unnecessary dependencies.

## 4. Authentication and authorization architecture

### User and session model

- The application uses Django's built-in user model. There is no `AUTH_USER_MODEL` setting and no custom user model.
- Credentials are username and password. `apps/accounts/views.py` uses Django's `AuthenticationForm` and `django.contrib.auth.login()`.
- Authentication state uses Django sessions through `SessionMiddleware` and `AuthenticationMiddleware`.
- Standard Django password validators are enabled.
- The built-in Django admin is mounted at `/admin/`.
- `LOGIN_URL` is the named route `accounts:login`.

### Routes and flows

| Route | Name | Behavior |
|---|---|---|
| `/` | `home` | Redirects anonymous users to login and authenticated users to `dashboard:home`; it does not render a second dashboard page |
| `/accounts/login/` | `accounts:login` | GET displays the custom login template; valid POST logs the user in and redirects to `dashboard:home`; already-authenticated users are redirected to the dashboard |
| `/accounts/logout/` | `accounts:logout` | POST only; calls Django logout and redirects to login; GET returns HTTP 405 |
| `/dashboard/` | `dashboard:home` | Protected by `login_required` and `never_cache`; renders `dashboard/index.html` |

The login view does not currently process a `next` parameter. Password reset/change, account profile, invitation, registration, MFA, login throttling/rate limiting, and custom staff-management screens are not present.

The sidebar logout is a confirmation modal containing a CSRF-protected POST form. `CsrfViewMiddleware` is active. Logout is deliberately not a GET link.

### Groups and role assumptions

These group names are exact in repository instructions, navigation, tests, and the development seed command:

1. `Owner / Admin`
2. `Pharmacist`
3. `Inventory Manager`
4. `Accountant`

Do not introduce a custom `Role` model or silently rename/merge these groups.

`seed_dev_auth` requires `DEV_AUTH_PASSWORD` in the environment and creates/fetches local users named `owner`, `pharmacist`, `inventory`, and `accountant`, then adds each user to the corresponding group. It sets the password only when a user is newly created. It does **not** create or attach model permissions and it does not make the `owner` user a Django superuser.

### Current authorization status

- The dashboard enforces authentication but not a group or model permission. This is consistent with a dashboard intended for all staff.
- `config/navigation.py` assigns group visibility to planned links.
- `config/context_processors.dashboard_navigation` filters by any configured Django permission and group, lets superusers bypass group filtering, safely disables unresolved URLs, and calculates active state from the URL namespace/name.
- At this snapshot every navigation item's `permission` is `None`. Current role filtering is therefore group-based UI filtering only.
- No business feature views exist yet, so no model permission is enforced outside the repository's documented requirement to add it later.
- Group membership and a hidden sidebar item are explicitly **not** considered a security boundary. Future protected views must enforce permissions server-side.
- The planning requirement “Owner/Admin has full system access” is not yet guaranteed by code. That group needs the relevant permissions assigned, or the intended owner account must be a superuser; the BRD/implementation plan must choose and test one approach.

### Authentication tests already present

`apps/accounts/tests.py` covers login-field rendering, invalid credentials, empty submissions, valid session login, redirecting authenticated users, rejecting GET logout, accepting POST logout, and the dashboard logout modal/CSRF/loading state. It uses Django `TestCase` and a fast password hasher override.

## 5. App and module boundaries

### Existing apps

#### `apps.accounts`

Owns login/logout routes, views, login template, authentication tests, and the `seed_dev_auth` management command. Its `models.py` and `admin.py` contain no project-owned implementation. There is no `forms.py`; the login view uses Django's built-in `AuthenticationForm` directly.

#### `apps.dashboard`

Owns the authenticated root page, dashboard demo template, role-navigation tests, and root URL namespace. Its `models.py` and `admin.py` contain no project-owned implementation. Dashboard content is explicitly mock/sample UI-foundation data, not calculated pharmacy data.

### Project-level modules

- `config/settings.py`: shared Django settings, installed apps, middleware, templates, database, internationalization, static files, and login URL.
- `config/urls.py`: admin, browser reload, accounts, and dashboard URL inclusion.
- `config/navigation.py`: the single sidebar-navigation definition.
- `config/context_processors.py`: navigation resolution, filtering, disabling, and active-state logic.
- `config/asgi.py` and `config/wsgi.py`: standard deployment entry points using `config.settings`.
- `config/visual_test_settings.py`: SQLite-only visual login-test override plus a login probe middleware. It is not the normal settings module.

### Boundaries for future feature apps

Repository instructions require feature apps under `apps/`, with feature-owned models, forms, views, URLconf, templates, migrations, and tests. App configs use dotted names such as `apps.accounts`. Each feature URLconf uses `app_name` and namespaced route names. Shared project configuration stays under `config/`; genuinely reusable presentation stays in root templates/static assets.

No `catalog`, `parties`, `inventory`, `purchasing`, `sales`, `prescriptions`, `finance`, `returns`, `reports`, `core`, or `audit` app exists. Their final boundaries and ownership are not determinable from the repository and must be fixed in the approved BRD/ERD before model creation.

## 6. Templates and UI structure

### Inheritance

- `templates/base.html` is the HTML shell. It loads the favicon, generated Tailwind CSS, shared toast markup, four shared JavaScript files, and the browser-reload script.
- `templates/layouts/auth.html` extends the base and supplies the centered authentication card/branding.
- `templates/layouts/dashboard.html` extends the base and composes the sidebar, mobile backdrop, topbar, and main content region.
- Authentication pages should extend `layouts/auth.html`.
- Authenticated feature pages should normally extend `layouts/dashboard.html`.

### Shared components

`templates/components/` contains documented reusable interfaces for buttons, inputs, textareas, selects, badges, cards, modals, toast messages, sidebar, and topbar. `docs/COMPONENTS.md` is the usage contract.

Important established behaviors:

- Components are included with Django `{% include %}`; callers commonly use `only` to constrain context.
- Button variants: `primary`, `secondary`, `danger`, `ghost`.
- Badge variants: `default`, `primary`, `success`, `warning`, `danger`, `info`.
- Form submit/loading behavior uses `data-submit-form` and `data-submit-button`.
- Modal behavior supports focus trapping, Escape/backdrop close, focus restoration, and optional CSRF-protected confirmed POST actions.
- Toasts translate Django messages or data-attribute triggers into accessible notifications.
- Sidebar behavior is responsive and keyboard-aware.
- Shared JavaScript lives in `static/js/` and uses small DOMContentLoaded modules with `data-*` hooks; no frontend state framework is present.

### Navigation and page context

Sidebar items must come from `config/navigation.py`; views/templates must not duplicate the list. The processor resolves namespaced routes, marks missing features disabled, filters visibility, and uses namespaces for active state. The topbar displays `page_context`, falling back to the current URL name or `Workspace`.

The navigation already reserves labels/namespaces for Dashboard, Sales, Medicines, Inventory, Suppliers, Customers, Prescriptions, Purchases, Invoices, Payments, Returns & Refunds, Reports, Settings, and Logout. Most have `url_name=None` and are intentionally disabled until implemented.

### Tailwind setup

- Source: `assets/css/input.css`.
- Generated output: `static/css/output.css`; ignored by Git and must never be edited manually.
- Theme tokens define `primary`, `sidebar`, semantic (`success`, `warning`, `danger`, `info`), and five chart colors.
- The source file explicitly adds `../../templates` and `../../static/js` as Tailwind sources and defines reusable toast styles/animations with reduced-motion handling.
- `npm run build:css` generates minified CSS; `npm run dev:css` watches; `npm run dev` runs Django and the Tailwind watcher together.
- Future templates must use complete static class names. Tailwind's scan must be verified when adding app-local templates; the explicit `@source` declarations name root templates and shared JS, while app-template discovery is not documented by this repository.

### Duplicate/unrouted template

`templates/home.html` and `apps/dashboard/templates/dashboard/index.html` contain the same dashboard UI-foundation markup at this snapshot. The active dashboard view renders the app-local template. No route renders root `home.html`; treat it as redundant/legacy unless Mohammad confirms another purpose. Do not casually edit both copies and assume both are used.

## 7. Database and configuration conventions

### Normal database configuration

`config/settings.py` loads a root `.env` file with `python-dotenv`, then obtains the entire default database configuration from `DATABASE_URL` through `dj_database_url.config()` with:

- persistent connections: `conn_max_age=600`
- connection health checks: `conn_health_checks=True`

Psycopg 3 binary support is installed, which supports PostgreSQL. The normal settings do not define a SQLite fallback. The database host/provider, database name, credentials, SSL query options, pooling mode, and whether the URL points to Neon are environment-owned and are **not determinable from tracked files**. Planning documents say Neon PostgreSQL, but the repository itself neither names Neon nor enforces Neon-specific parameters. Do not print or commit `DATABASE_URL`.

There is no tracked `.env.example` or `.env.template`, even though `.gitignore` permits those filenames. Future setup documentation will need a secret-free variable contract.

### Visual-test override

`config/visual_test_settings.py` imports normal settings, switches the database to a local SQLite file under `.venv/`, and prepends `LoginProbeMiddleware`. The probe prints the submitted username, password length, and whether the password matches; it does not print the password itself. This module is test-only and must never be selected for a deployed environment.

### Other settings

- `LANGUAGE_CODE = "en-us"`, `TIME_ZONE = "UTC"`, `USE_I18N = True`, and `USE_TZ = True`.
- `STATIC_URL = "static/"`; `STATICFILES_DIRS` includes root `static/`.
- `MEDIA_URL`, `MEDIA_ROOT`, `STATIC_ROOT`, custom storage backends, and uploaded-file policy are absent.
- The setting named `MAILERS` configures a console email backend, but no repository code consumes it and no standard email workflow is implemented. Its intended use is not determinable.
- There is one settings module for normal use plus the visual-test override; separate development/test/production settings modules do not exist.

### Development-only security posture

The current settings are not deployment-ready: `DEBUG=True`, `ALLOWED_HOSTS=[]`, and the development secret key is hard-coded. Secure cookies, proxy/TLS headers, HSTS, trusted CSRF origins, production logging, static-file serving, and provider deployment settings are not configured. These are risks to resolve before deployment, not permission to redesign the existing authentication flow.

## 8. Existing models and migrations

- `apps/accounts/models.py`: no project-owned models.
- `apps/dashboard/models.py`: no project-owned models.
- Both app `migrations/` directories contain only `__init__.py`.
- No project-owned migration file exists.
- The only schema implied by the current implementation is Django's installed built-in apps: admin, auth, content types, sessions, messages/static support as applicable. Their framework migrations are supplied by Django, not stored here.
- There are no business tables, foreign keys, UUID fields, timestamp mixins, money/quantity conventions, transaction status fields, indexes, constraints, or deletion policies in code.

Therefore, the BRD and ERD remain prerequisites. Do not infer a schema from the mock dashboard or navigation labels.

## 9. Reusable utilities and established patterns

No reusable Python base model, domain service layer, repository/query layer, custom form base, audit service, document-number service, money type, or shared transaction utility exists.

The reusable foundation that does exist is:

- `config.navigation.DASHBOARD_NAVIGATION`: immutable tuple of navigation dictionaries.
- `config.context_processors.dashboard_navigation`: central visible/resolved/active navigation output.
- Root layout and component templates described in `docs/COMPONENTS.md`.
- Vanilla-JS modules for submit locking/loading, modal focus behavior, responsive sidebar behavior, and toast notifications.
- Django messages integration through `templates/components/toast.html`.
- `seed_dev_auth` for local role/user setup without tracked credentials.
- Consistent app configuration (`name = "apps.<app>"`), namespaced URLconfs, app-local templates, and Django `TestCase` tests.
- Documented validation commands: `uv run manage.py check`, `uv run manage.py test`, and `npm run build:css`.

Future complex workflows—sale completion, purchase receipt, FEFO allocation, payment posting, and returns—may justify explicit service functions and `transaction.atomic()`, but no exact service interface is implemented yet.

## 10. Integration constraints for new pharmacy features

1. Preserve the full-stack Django architecture: Django views, forms/ModelForms, templates, ORM, sessions, groups, and permissions.
2. Preserve built-in username/password authentication and the existing login/logout routes and templates. Do not add a custom User or Role model merely to represent the current roles.
3. Put each feature under `apps/<feature>/`; keep its models, forms, views, URLs, templates, migrations, and tests with the owning app.
4. Fix app boundaries, model ownership, relationship direction, identifiers, precision, state transitions, and service contracts in the approved BRD/ERD before creating business models.
5. Use namespaced routes and reverse them by name. Coordinate changes to `config/urls.py`, `config/settings.py`, and `config/navigation.py` because they are shared integration surfaces.
6. Add server-side authentication and permissions to every protected business view. Navigation visibility alone is not authorization.
7. If a navigation item gains a route, update its stable `url_name` and appropriate model permission while preserving namespace-driven active state and unresolved-link behavior.
8. Use shared layouts/components and theme tokens. Keep feature-specific UI in its app; promote a pattern to root components only when genuinely reusable.
9. Use static Tailwind class names, keep JavaScript minimal and vanilla, and regenerate—never hand-edit—`static/css/output.css`.
10. Keep inventory mutation behind one agreed ownership boundary/service. Sales, purchases, returns, and corrections must not each invent independent stock arithmetic.
11. Use database transactions for workflows that create/update several dependent records. Exact locking/idempotency rules must come from the approved business rules and risk analysis.
12. Do not hard-delete shared financial/inventory history unless the approved BRD explicitly permits it. The repository does not yet implement deletion policy, reversal, or audit behavior.
13. Do not install dependencies or introduce infrastructure without a concrete need and team approval. Use `uv` and npm consistently and update their lockfiles deliberately.
14. Never commit `.env`, credentials, production data, local databases, generated CSS, or collected static files.
15. Coordinate authentication and shared UI/design changes with Mohammad Hajeer, the existing foundation owner in the team planning context. Repository instructions independently require coordination on shared files.

## 11. Files future AI agents must read

Every agent must start with:

1. `AGENTS.md`
2. `docs/DEVELOPMENT_GUIDE.md`
3. The approved BRD and ERD (**not present in this snapshot**)
4. The ticket/acceptance criteria and owning app's relevant files

Claude-based agents must also read `CLAUDE.md`.

| Planned change | Minimum files to read before editing |
|---|---|
| Authentication/login/logout/users | `AGENTS.md`; `docs/DEVELOPMENT_GUIDE.md`; `apps/accounts/views.py`; `apps/accounts/urls.py`; `apps/accounts/tests.py`; `apps/accounts/templates/accounts/login.html`; `apps/accounts/management/commands/seed_dev_auth.py`; `config/settings.py`; `config/urls.py`; `templates/layouts/auth.html`; affected shared components/JS |
| Groups, permissions, or role visibility | All authentication files above; `config/navigation.py`; `config/context_processors.py`; `apps/dashboard/tests.py`; owning feature's views/models/tests; approved RBAC matrix |
| Dashboard or navigation | `config/navigation.py`; `config/context_processors.py`; `apps/dashboard/views.py`; `apps/dashboard/urls.py`; `apps/dashboard/tests.py`; `apps/dashboard/templates/dashboard/index.html`; `templates/layouts/dashboard.html`; `templates/components/sidebar.html`; `templates/components/topbar.html` |
| Shared UI/component/design | `docs/COMPONENTS.md`; `templates/base.html`; both files in `templates/layouts/`; the affected files in `templates/components/`; `assets/css/input.css`; relevant files in `static/js/`; dashboard demo template/tests |
| New or changed model | `AGENTS.md`; database/model sections of `docs/DEVELOPMENT_GUIDE.md`; approved BRD and ERD; owning app's `models.py`, migrations, admin, forms/services/views/tests; every related model in other apps; `config/settings.py` for app registration |
| New feature app or URLs | `docs/DEVELOPMENT_GUIDE.md`; `config/settings.py`; `config/urls.py`; `config/navigation.py`; `config/context_processors.py`; `apps/accounts` authorization pattern; `apps/dashboard` URL/test pattern |
| Database/settings/environment | `config/settings.py`; `config/visual_test_settings.py`; `config/asgi.py`; `config/wsgi.py`; `manage.py`; `.gitignore`; `README.md`; `pyproject.toml`; `uv.lock`; any deployment docs/config added later |
| Tailwind/frontend tooling | `docs/COMPONENTS.md`; `assets/css/input.css`; `package.json`; `package-lock.json`; `templates/base.html`; affected layouts/components/templates; relevant shared JS |
| Tests | Existing tests in `apps/accounts/tests.py` and `apps/dashboard/tests.py`; owning app tests; settings/URLs/templates involved; repository validation section in `AGENTS.md` |

For Hala or Yasser working with an AI that cannot automatically read the repository, attach the listed general files plus the row matching their task, the approved BRD/ERD sections, and all related owning/cross-app model or service files. Do not attach `.env`, credentials, database exports, production logs, or secret-bearing configuration.

## 12. Risks and conflicts with the planned pharmacy specification

### Repository-only gaps

| Risk/gap | Current evidence | Required planning response |
|---|---|---|
| BRD/ERD absent | Repository docs repeatedly require them, but neither is tracked | Finalize and approve them before business model/migration work |
| Business app boundaries unresolved | Only `accounts` and `dashboard` exist | Choose bounded contexts and one owner per model/workflow; avoid app-per-model fragmentation |
| No identifier/base-model conventions | No business models or base utilities exist | Decide UUID scope, timestamps, money/quantity precision, codes, ordering, and deletion policy centrally |
| No inventory transaction authority | No inventory app/service exists | Establish one stock-movement and FEFO allocation contract consumed by sales, purchasing, and returns |
| Roles exist without permissions | Seed command creates groups/users but assigns no permissions; navigation permissions are all `None` | Define an RBAC matrix and deterministic group-permission provisioning; test view enforcement |
| Owner/Admin is not automatically full-access | Group membership alone does not grant Django permissions | Decide superuser versus comprehensive group permissions and test the result |
| Navigation names may not equal app boundaries | Menu reserves `medicines`, `invoices`, `payments`, and `returns` namespaces while planning suggests apps such as `catalog`, `finance`, or optional `returns` | Deliberately map stable UI namespaces/routes to owning apps before implementation |
| Mock dashboard can be mistaken for a feature | Metrics are literal sample values and the page says development-only | Replace with approved queries/widgets incrementally; never derive schema from the mock cards |
| Uploaded prescriptions lack media configuration | No media/storage settings or validation policy exist | Decide storage, allowed types/sizes, access control, retention, and safe serving before attachments |
| Production configuration absent | Development secret/debug/browser reload and no deployment/static settings | Add environment-specific production hardening before deployment without changing auth semantics |
| Neon is not encoded in tracked config | Only generic `DATABASE_URL` plus Psycopg is present | Document a secret-free Neon URL/SSL/pooling convention; never commit the real URL |
| No deployment or backup artifacts | No Dockerfile, Blueprint, Procfile, CI, backup script, or deployment guide is tracked | Select and document the actual deployment/backup approach before release |
| No audit, numbering, reversal, or financial utilities | No domain code exists | Define minimum traceability and reversal rules in the BRD/ERD before transaction models |
| No test/tool quality configuration beyond Django tests | No CI, formatter, linter, type checker, coverage config, or browser test suite is tracked | Keep validation realistic for nine days, but establish repeatable checks before parallel work |

### Conflicts or ambiguities in the external planning context

These comparisons are **not repository facts**; they identify decisions that must be reconciled before future agents act:

- A prior generated specification reportedly selected Django 5.2 LTS, while this repository declares and locks Django 6.1. The later planning instruction says the existing implementation wins. Do not downgrade or change Django without an explicit team decision and compatibility review.
- An earlier architecture recommendation mentioned a custom User model and separate role constants. The later phase plan and repository explicitly preserve Django's built-in User, sessions, Groups, and Permissions. Adding a custom User now would be a foundational migration and conflicts with the current source of truth.
- Earlier wording used `Cashier/Pharmacist`; the repository and later phase plan use the exact group `Pharmacist`. Do not add or merge roles until the final RBAC matrix explicitly changes the four current group names.
- The attached phase plan deferred enterprise purchase orders, cashier-shift reconciliation, idempotency, advanced immutable audit infrastructure, and complex discrepancy workflows. A later user instruction said all original mandatory requirements and refinements must be included in Phase 1. The final BRD must explicitly list which previously deferred items were reactivated; the repository cannot resolve that policy conflict.
- The original mandatory scope includes medicines, suppliers, customers, prescriptions, purchases, inventory, sales, invoices/receipts, payments, balances, returns/refunds, discounts, taxes, and connected end-to-end workflows. None of these business domains is implemented yet despite their disabled navigation placeholders.
- Planned business records use UUIDs, batch-specific acquisition costs, batch/expiry traceability, FEFO, stock movements, partial payments, professional invoices, and transaction-safe services. The repository contains no implementation or convention for any of them. Their exact field types, precision, state machines, and cross-app relationships remain BRD/ERD decisions.
- The agreed stock-discrepancy refinement allows a pharmacist to complete a physically available sale despite a system shortage, while recording and alerting the discrepancy. The attached phase plan says not to build an overly complex discrepancy investigation system. A minimal, explicit override workflow and authorization/audit rule must be defined so these requirements do not produce either an unsafe bypass or a nine-day overbuild.
- The plan excludes shelf/bin/location tracking. Do not infer it from FEFO requirements.
- UI/UX visual invention belongs to Mohammad Hajeer and is intended to remain flexible. Repository component and accessibility contracts still constrain integration behavior; visual changes should be coordinated instead of independently replacing the foundation.

## 13. Do Not Break checklist

- [ ] Read `AGENTS.md`, `docs/DEVELOPMENT_GUIDE.md`, relevant component docs, approved BRD/ERD, and the owning feature files first.
- [ ] Preserve built-in Django username/password authentication, sessions, login/logout URLs, and POST-only CSRF-protected logout.
- [ ] Preserve the exact group names: `Owner / Admin`, `Pharmacist`, `Inventory Manager`, `Accountant`.
- [ ] Do not treat sidebar visibility as authorization; enforce and test permissions in protected views.
- [ ] Keep feature code under `apps/`, use `apps.<name>` app configs, namespaced URLs, and app-local templates/tests.
- [ ] Do not create business models or migrations before the BRD/ERD and model ownership are approved.
- [ ] Keep one authoritative inventory/stock-movement path; do not directly mutate stock from several apps.
- [ ] Use shared dashboard/auth layouts, documented components, central navigation, existing Tailwind tokens, and minimal vanilla JS.
- [ ] Do not duplicate sidebar/topbar/navigation or add an unapproved frontend/API/auth framework.
- [ ] Never edit or commit generated `static/css/output.css`.
- [ ] Coordinate edits to settings, root URLs, navigation, shared components/layouts, authentication, and cross-app models.
- [ ] Do not expose or commit `.env`, `DATABASE_URL`, passwords, keys, production data, or secret-bearing logs.
- [ ] Do not assume the present settings are production-safe; harden deployment explicitly before release.
- [ ] Preserve existing tests and add focused authentication, authorization, validation, transaction, and edge-case coverage for each feature.
- [ ] Review generated migrations and do not rewrite shared migrations without team agreement.
- [ ] Keep work scoped; do not commit, push, merge, rebase, or change unrelated code unless explicitly requested.

## Inspection limitations

- No live `.env`, database, Neon project, deployment platform, GitHub settings, CI status, branch protections, or external service configuration was inspected.
- No production/runtime secrets were read.
- No BRD or ERD exists in the repository at this commit.
- Exact Node, npm, `uv`, PostgreSQL server, and Neon versions are not determinable from tracked files.
- Runtime checks and Django tests were not run because this was a documentation-only inspection and the user explicitly prohibited running migrations; Django tests ordinarily create and migrate a test database.
- The report describes the inspected commit. Re-check the commit and diff before relying on it after new merges.
