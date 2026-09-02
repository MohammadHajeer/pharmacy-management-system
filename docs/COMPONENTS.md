# UI components

Shared templates live in `templates/layouts/` and `templates/components/`. They use ordinary Django template inheritance and includes.

## Layouts

Use the dashboard layout for application pages that need the sidebar and topbar:

```django
{% extends "layouts/dashboard.html" %}
{% block content %}...{% endblock %}
```

Use the auth layout for login and password-related screens. It provides a centered card without dashboard navigation:

```django
{% extends "layouts/auth.html" %}
{% block content %}...{% endblock %}
```

## Light and dark themes

The operational dashboard and auth shells share a root `html.dark` theme with
Tailwind v4's class-based `dark` variant. `components/theme_init.html` resolves
the preference inline before the stylesheet and first paint; `static/js/theme.js`
owns the responsive topbar/login switch and its descriptive action label. The
switch is a compact icon control below the `md` breakpoint and a wide, labeled
Light/Dark segmented control from `md` upward.
`localStorage["pharmanex.theme"]` accepts `light`, `dark`, or `system` (the default).
The two-state button saves an explicit choice. System changes apply only while
following `system`; storage events and `pageshow` restore the current preference.
Blocked storage falls back safely to an in-memory choice. No server preference,
new dependency, or database change is involved.

Use semantic tokens from `assets/css/input.css` for themed presentation:

- `bg-canvas` for the shell; `bg-surface`, `bg-surface-muted`, and
  `bg-surface-hover` for workspaces, controls, and interaction states;
- `text-ink-strong`, `text-ink`, `text-ink-soft`, `text-body`, `text-copy`,
  `text-muted`, and `text-faint` for the existing text hierarchy;
- `border-line`, `border-line-soft`, and `border-line-strong` for separators;
- `accent`, `positive`, `caution`, `negative`, and `notice` text/soft/line roles
  for links, badges, validation, and alerts. Keep complete static class names.

These same roles cover ledgers, filters, pagination, selects (including JS-added
classes), modals, toasts, dirty bars, POS, and feature-owned surfaces. The
dashboard chrome additionally uses `shell-sidebar`, `shell-topbar`, and the
`sidebar-*` interaction roles. Light mode uses the branded teal sidebar against
the light neutral workspace. Dark mode overrides the same roles with the neutral
charcoal/teal-biased shell and reserves brighter teal for active and focus states.
The existing white logo sits directly on either sidebar without a plaque. White
logo plaques on auth screens remain intentional. The standalone historical
design-comparison page is not part of the operational theme system.

Authenticated account identity lives in the fixed sidebar footer rather than the
topbar. Only the middle navigation region scrolls. Its compact account trigger
opens upward, repeats the signed-in username and role for context, and launches
the existing POST-only logout confirmation flow. The topbar retains breadcrumbs
and the theme control.

Theme changes intentionally have **no transition**. Themed color-transition
utilities are removed; `data-theme-changing` also suppresses transitions and
animations during synchronous theme application/style resolution. Unrelated
sidebar transforms and toast motion remain. Native controls use `color-scheme`.
Chart.js reads the `--color-chart-*` roles, refreshes existing instances on
`pharmanex:theme-change`, and calls `update("none")`, including value labels,
axes, grids, tooltips, and series. Print events refresh chart colors too.

Dark token overrides are screen-only. `@media print` hides navigation, theme
controls, dialogs, and toasts and restores a white page with dark text, so invoices
and receipts stay light regardless of preference. Existing sales print layout
rules remain in place. Physical printer output is a separate device check.

Run the frontend suite with `node --test apps/dashboard/tests_js/*.test.cjs
apps/sales/tests_js/*.test.cjs`. For disposable cross-workspace browser review,
run `npm run build`, then `uv run python scripts/preview-theme.py`: port 8017 uses
synthetic fixtures in an in-memory SQLite database and prints a random local
login. Stopping the process discards the data; it never uses the `.env` database.

## Navigation loading

The dashboard layout loads `static/js/navigation-loading.js`, includes the shared
`components/navigation_loading.html` indicator, and marks the main workspace with
`data-navigation-workspace`. A normal same-origin link or valid native form submit
sets `data-navigation-pending` on the document and `aria-busy` on the workspace.
The thin teal bar advances without claiming a real percentage; reduced motion
uses a static bar. Workspace opacity becomes 0.85 and pointer interaction is
blocked; sidebar links are lightly muted and repeat navigations are canceled.
The sidebar and topbar keep their layout, and keyboard focus is not moved.

Modified clicks, other browsing targets, downloads, non-HTTP/external URLs,
same-page anchors, disabled links, and modal/button triggers are excluded.
Canceled events are checked after dispatch. Forms retain native validation,
submitter overrides, CSRF-protected POSTs, and existing button/dirty behavior.
There is no page fetching, routing, or HTML replacement in this helper.

Registry filters dispatch a cancelable `pharmanex:before-navigate` document event
with `detail: { url }` immediately before their existing `location.assign` flow.
If dispatch returns false, they must not navigate. This shares the lock without
changing debounce, serialization, or query preservation. Other genuine scripted
full-page navigations can use the same event. Put `data-navigation-loading="off"`
on a link, form, submitter, or containing element for interactions handled entirely
by a local component (such as downloads or non-navigating forms).

Initialization and every `pageshow` reset the indicator and lock, including
Back/Forward cache restoration. A 15-second safety timeout releases the UI if the
document stays open; this is not a request timeout and never cancels the request.
The reset event `pharmanex:navigation-reset` restores shared submitting buttons;
those buttons also recover on canceled submits, `pageshow`, and their own timeout
on auth pages. Dirty forms re-evaluate their current values without clearing them.

Run the dependency-free frontend tests with
`node --test apps/dashboard/tests_js/*.test.cjs`.

## Breadcrumb context

Dashboard-shell views provide explicit breadcrumb labels in page context; the topbar never derives labels from route names. Keep the final item unlinked, and only provide earlier-item URLs that are real and permitted for the current user:

```python
return render(request, "catalog/medicines/list.html", {
    "breadcrumbs": [
        {"label": "Catalog"},
        {"label": "Medicines"},
    ],
})
```

Simple pages use one item. When `breadcrumbs` is absent, the shell may display the existing explicit `page_context` value; it never falls back to `resolver_match.url_name`.

## Button

```django
{% include "components/button.html" with text="Save medicine" variant="primary" type="submit" %}
{% include "components/button.html" with text="Cancel" variant="secondary" href="/" %}
{% include "components/button.html" with text="Delete" variant="danger" disabled=True %}
{% include "components/button.html" with text="More actions" variant="ghost" size="sm" %}
```

Variants are `primary`, `secondary`, `outline`, `ghost`, and `destructive`. The existing `danger` name remains an alias for `destructive`. Sizes are `sm`, `default`, `lg`, and `icon`; omitting `size` uses `default`. Pass accessible text when using the compact `icon` size. Buttons can also open shared UI behaviors without custom markup:

```django
{% include "components/button.html" with text="Open modal" variant="primary" modal_target="confirm-modal" %}
{% include "components/button.html" with text="Show toast" variant="secondary" toast_level="success" toast_message="Saved successfully." %}
{% include "components/button.html" with text="Show details" variant="secondary" toast_level="info" toast_title="Report ready" toast_message="The report can now be downloaded." toast_duration=6000 %}
```

## Input

```django
{% include "components/input.html" with name="medicine_name" label="Medicine name" required=True %}
{% include "components/input.html" with name="sku" label="SKU" value=form.sku.value error=form.sku.errors %}
{% include "components/input.html" with name="reference" label="Reference" value="RX-1048" readonly=True help_text="Generated by the system." %}
{% include "components/input.html" with name="username" label="Username" autocomplete="username" maxlength="150" autofocus=True %}
{% include "components/textarea.html" with name="notes" label="Notes" rows="4" help_text="Visible to pharmacy staff." %}
{% include "components/select.html" with name="category" label="Category" options=category_options value=form.category.value error=form.category.errors %}
```

Select options are dictionaries with `value`, `label`, and an optional `disabled` value. Pass a bound field's `.errors` to show Django validation feedback.

Inputs also accept `type`, `placeholder`, `autocomplete`, `maxlength`, `autofocus`, `required`, `disabled`, `readonly`, and `help_text`. Textareas accept `placeholder`, `autocomplete`, `maxlength`, `required`, `disabled`, `readonly`, and `help_text`; selects accept `placeholder`, `required`, `disabled`, and `help_text`. Form controls associate help and error copy through `aria-describedby`. Buttons accept `full_width=True` when a form action should fill its container.

Numeric inputs also accept `step`, `min`, and `max` (including zero). Pass values matching the existing Django field; these attributes do not replace server-side validation.

## Checkbox

```django
{% include "components/checkbox.html" with id="payment-method-is-active" name="is_active" label="Active" checked=form.is_active.value description="Inactive methods cannot be selected for new work." error=form.is_active.errors %}
```

Checkboxes accept `id`, `name`, `value`, `checked`, `disabled`, `required`, `label`, `description` (or `help_text`), `error`, `aria_invalid`, and `aria_describedby`. The native checkbox remains responsible for form submission and keyboard interaction; the shared visual control supplies the PHARMANEX checked, focus, disabled, and error states. Pass a bound field's `.value` and `.errors` to preserve Django validation responses.

The select component progressively enhances its native `<select>` into the shared custom dropdown. Keep passing the original Django field `name`, current `value`, and `options` dictionaries; the native control remains the submitted form field and preserves required, disabled, initial-value, and validation behavior. The shared `static/js/custom-select.js` script is loaded by the base layout and provides click-outside closing plus Arrow Up, Arrow Down, Enter, Escape, Home, End, and Tab keyboard behavior. No page-specific JavaScript is needed.

For a reusable submit/loading state, mark the form with `data-submit-form` and pass `loading_text` to its submit button:

```django
<form method="post" data-submit-form>
  {% csrf_token %}
  {% include "components/button.html" with text="Save" loading_text="Saving..." type="submit" full_width=True %}
</form>
```

The shared form script waits for the browser's valid `submit` event, disables the button, sets `aria-busy`, and swaps in the spinner/loading label without interrupting the POST.

For forms whose submit action should remain disabled until a value differs from the initial rendered state, add `data-dirty-form`, pass both `disabled=True` and `dirty_submit=True` to the button, and load `static/js/form-dirty-state.js` from the page. The helper compares the complete form state on input/change, so restoring every original value disables the button again.

## Badge

```django
{% include "components/badge.html" with text="Paid" variant="success" %}
{% include "components/badge.html" with text="Low stock" variant="warning" %}
{% include "components/badge.html" with text="Overdue" variant="danger" %}
```

Variants are `default`, `secondary`, `success`, `warning`, `destructive`, and `outline`. The existing `primary`, `danger`, and `info` variants remain supported for compatibility.

## Card

```django
{% include "components/card.html" with eyebrow="Today's sales" metric="$2,450" text="8.4% above yesterday" %}
{% include "components/card.html" with title="Stock alert" description="Review medicines below their reorder point." content="12 medicines need attention." footer="Updated five minutes ago" %}
```

The optional values are `eyebrow`, `title`, `description`, `metric`, `content`, `text`, and `footer`. Header, content, and footer regions are rendered only when their values are supplied.

## Icon

Render a decorative interface icon by its centralized name and pass complete Tailwind classes for its size, color, and layout:

```django
{% include "components/icon.html" with name="dashboard" class="size-5" only %}
{% include "components/icon.html" with name=item.icon class="size-4.5 shrink-0" only %}
{% include "components/icon.html" with name="chevron-right" class="size-4 text-slate-400" only %}
```

The component supplies the shared `24 × 24` view box, current-color stroke, no fill, `1.8` stroke width, and `aria-hidden="true"`. It intentionally renders nothing for an unknown name. To register an icon, add its name to the supported-name condition and add one matching path branch in `templates/components/icon.html`; call sites then only reference that name.

## Modal

Render a modal once, then open it from any button whose `data-modal-open` matches its ID:

```django
{% include "components/button.html" with text="Open modal" variant="primary" modal_target="confirm-modal" %}
{% include "components/modal.html" with modal_id="confirm-modal" title="Confirm change" body="Review this change before continuing." confirm_text="Continue" %}
```

Buttons with `data-modal-close`, the backdrop, and the Escape key close it. Focus stays inside while it is open.

For a confirmed POST action, pass `confirm_action`. The modal renders a CSRF-protected form and can reuse the submitting state through `confirm_loading_text`:

```django
{% include "components/modal.html" with modal_id="logout-modal" title="Sign out?" body="Your session will end." close_text="Cancel" confirm_text="Sign out" confirm_action=logout_url confirm_variant="danger" confirm_loading_text="Signing out..." %}
```

Small server-rendered forms can be placed inside the shared dialog by passing `form_action`, `form_template`, `modal_form`, and a unique `field_prefix`. Pass `open_modal` to mark one dialog for automatic opening after a validation response. Form-dialog includes must retain the parent template context so Django's CSRF token is available:

```django
{% include "components/modal.html" with modal_id="tax-rate-create" title="Add tax rate" form_action=create_url form_template="core/tax_rates/_form_fields.html" modal_form=form field_prefix="tax-rate-create" confirm_text="Save tax rate" open_modal=open_modal %}
```

## Toasts

Use Django's standard messages API. The base template automatically turns messages into stacked, dismissible notifications.

```python
from django.contrib import messages

messages.success(request, "Medicine added successfully.")
messages.error(request, "Something went wrong.")
messages.warning(request, "Stock is running low.")
messages.info(request, "The report is being prepared.")
```

When a server-rendered message needs a separate title or a non-default display time, pass `toast_title` and `toast_duration` in the template context for that response. Untitled messages and existing button triggers keep their current behavior.

## Clinical operations surfaces

Use `workspace-container` on the outer feature-page wrapper, around the header,
local navigation, filters, and workspace surfaces. It centers the page at Tailwind's
`max-w-6xl` (72rem), matching Settings, and uses the available width on smaller
screens. The dashboard layout owns responsive page padding; do not add another
layer of horizontal padding or a page-specific maximum width to this wrapper.
Keep narrower controls/forms inside the container where appropriate.

Catalog pages include `catalog/_section_navigation.html` below their main header.
The flat Medicines / Categories / Manufacturers links retain view-permission
filtering and use exact namespaced `request.resolver_match.view_name` checks for
the active section, including its create/edit/detail and medicine unit/barcode
pages. The current section has `aria-current="page"` and a teal underline; these
ordinary links wrap on small screens and remain independent of breadcrumbs.

Dashboard and configuration workspaces can use the small shared presentation roles defined in `assets/css/input.css`:

- `workspace-surface` for a connected, bordered workspace region;
- `operational-kicker` for compact operational context labels;
- `operational-empty` for readable, action-aware empty states.

The shared theme also defines `status`, `control`, `workspace`, and `dialog` radius roles. Use the matching radius for the element's function rather than applying the largest radius to every region.

Dirty forms may include `data-dirty-indicator`, `data-pristine-indicator`, and `data-dirty-surface` elements. `form-dirty-state.js` toggles their presentation while preserving the existing form comparison and submit-button behavior.

## Registry controls and ledgers

Registry pages share `components/registry_filters.html`. Supply `query`, `status`, `status_options`, and a reversed `clear_url`; optional `search_label` and `search_placeholder` enable search only where supported. It composes the existing controls and remains a normal GET form.

Omit `status_options` for search-only registries. Feature-owned controls may be
included through `extra_filters_template`; set `has_filters` when those controls
are active so the shared Clear filters link remains available. Finance uses this
for its payment-method filter with the same native-change navigation behavior.

`static/js/registry-filters.js` enhances forms marked `data-registry-filter-form`: search input applies after 350 ms, Enter applies immediately, and the shared custom select's bubbling native `change` event applies immediately. Navigation sends the form's existing `q`/`status` values to Django, preserves unrelated URL parameters, and removes blank searches and `page` so filters restart at page 1. Search focus/caret are restored after navigation when session storage is available; no query/filter business logic runs in JavaScript. A conditional **Clear filters** link returns to the base route, clearing filters and page state. A submit button exists only inside `noscript`, supporting Enter and status-only forms without JavaScript; GET forms must not include a hidden `page` field.

Run the dependency-free interaction tests with `node --test apps/dashboard/tests_js/registry-filters.test.cjs`.

Use `ledger-scroll` around a `ledger-table` for a contained horizontal scroll region, with `tabindex="0"`, `role="region"`, and a descriptive `aria-label`. Tables retain captions and column headers. Use `ledger-number` on numeric cells and their headers for right alignment and tabular numerals. `registry-link` provides the shared record-link focus/hover treatment. These roles use existing theme colors and do not change the dashboard shell.

`ledger-scroll` also establishes the positioning context for screen-reader-only
captions/action text, preventing that absolute content from widening the page.

Render empty states outside the table's scroll region so their text and permitted actions remain visible on narrow screens.

### Server-side pagination

Large registries and transaction lists use **25 rows per page**, defined by
`DEFAULT_PAGE_SIZE` in `apps/core/pagination.py`. Apply existing permissions and
filters first, then pass an unevaluated queryset with deterministic ordering
(including `id` as the final tie-breaker) to the shared helper:

```python
**pagination_context(request, medicines, context_name="medicines"),
```

This keeps the existing row context name as a sliced queryset and supplies
`page_obj` and Django's elided `page_numbers`. Invalid page text resolves to page 1;
negative and out-of-range numbers resolve to the last page via `Paginator.get_page()`.
Include the footer outside the table scroll region, retaining request context:

```django
{% include "components/pagination.html" with label="medicines" %}
```

The component shows the **filtered** row range/count and uses Django's built-in
`querystring` tag to replace only `page`, retaining all other parameters (including
repeated values and sorting). One-page results show only the count; empty results
retain the existing empty state without a footer. Mobile shows Previous / Page X
of Y / Next; larger screens show an elided range with an accessible current page.
On browser history restoration, the filter form resets to its server-rendered
defaults so cached edits cannot disagree with the URL and displayed result page.

Currently applied to Medicines, Customers, Suppliers, Prescribers, Purchase
Invoices, Sales Invoices, and Finance payment registries, invoice selection, and invoice payment
history. Small configuration lists, document line items, and dashboard recent
subsets remain unpaginated. Inventory/history, returns/refunds, and reports
have no implemented list pages; prescription views currently
lack templates. Apply this convention when those screens are implemented.

## Sidebar navigation

Navigation is configured once in `config/navigation.py`; views do not pass link lists. When a routed feature is enabled, update its existing namespaced `url_name` (for example, `catalog:medicine-list`) and Django permission (for example, `catalog.view_medicine`). Do not create a duplicate app from a navigation label.

Items spanning separately permissioned workspaces may specify `any_permissions`:
at least one must be granted, in addition to any singular `permission`. Payments
uses this to admit customer-only or supplier-only viewers. Its finance landing
route enforces the same check and redirects to an authorized registry.

`config/context_processors.py` hides links the current user cannot access and safely disables unavailable routes. For active state, configure `active_url_names` with exact local route names; both the namespace and route name must match `request.resolver_match`. An explicit set is authoritative. Without it, the processor matches the fully qualified destination route, then permits namespace fallback only if that namespace belongs to one configured area. Unavailable links never become active. Suppliers and Customers have separate route sets; Catalog and Purchasing include their nested routes. Prescribers has no sidebar entry and does not activate Suppliers or Customers. Permissions remain the security boundary; there are no group-name checks.
