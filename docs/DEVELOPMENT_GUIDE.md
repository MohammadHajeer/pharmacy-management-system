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

## Creating a feature app

Use a short, plural feature name where practical. The following example creates `medicines` under `apps/`:

```bash
mkdir apps/medicines
uv run manage.py startapp medicines apps/medicines
```

Then:

1. Change `MedicinesConfig.name` in `apps/medicines/apps.py` to `"apps.medicines"`.
2. Add `"apps.medicines"` to `INSTALLED_APPS` in `config/settings.py`.
3. Create `apps/medicines/urls.py` with `app_name = "medicines"`.
4. Include it from `config/urls.py`, for example `path("medicines/", include("apps.medicines.urls"))`.
5. Create feature templates under `apps/medicines/templates/medicines/`.
6. Add the feature to `config/navigation.py` when it should appear in the sidebar.
7. Add focused tests in `apps/medicines/tests.py` or an app-local `tests/` package.

Create `forms.py`, service modules, or query modules only when the feature needs them. Avoid empty layers or new architectural patterns without a concrete use.

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
app_name = "medicines"

urlpatterns = [
    path("", views.medicine_list, name="index"),
]
```

Refer to it as `medicines:index` in Python, templates, redirects, tests, and navigation. Namespaces prevent collisions and power the sidebar's active-state handling.

## Sidebar navigation

Configure sidebar items once in `config/navigation.py`. `config/context_processors.py` then:

- resolves each namespaced URL;
- leaves not-yet-implemented routes disabled;
- filters items by group or permission; and
- marks the current namespace active.

Do not pass duplicate link lists from views or hardcode them in feature templates. When a feature becomes available, set its `url_name`, preserve its `namespace`, and set its Django permission when the model permission exists.

## Authentication, groups, and permissions

The project uses Django's built-in user model, sessions, groups, and permissions. Do not add a custom role model or another authentication system.

Current group names are exact:

- Owner / Admin
- Pharmacist
- Inventory Manager
- Accountant

Groups describe job responsibilities and collect permissions. They also control current sidebar visibility, but a hidden link is not an authorization boundary. Protected views must enforce access, preferably with Django model permissions such as `medicines.view_medicine`, `medicines.add_medicine`, `medicines.change_medicine`, and `medicines.delete_medicine`.

For example, use `permission_required(..., raise_exception=True)` for function views or `PermissionRequiredMixin` for class-based views. Add tests proving that anonymous and unauthorized users cannot reach protected actions. Superuser behavior should remain compatible with Django defaults.

## Development accounts

The repository does not provide or track shared credentials. Each teammate should create local-only accounts:

```bash
uv run manage.py createsuperuser
```

Use the local admin at `http://127.0.0.1:8000/admin/` to create regular test users, create the four groups with the exact names above if they are not present, assign users to groups, and attach the permissions needed for the feature under test. Sign in to the application at `/accounts/login/`.

Use clearly fake data and unique local passwords. Never commit credentials, `.env` files, or `db.sqlite3`, and do not depend on another developer's local database. Automated tests must create their own users, groups, permissions, and records.

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
