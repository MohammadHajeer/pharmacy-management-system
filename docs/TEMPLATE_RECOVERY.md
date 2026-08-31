# Django template recovery — 2026-08-31

## Incident and repair scope

The incident left 270 Django block/variable expressions split across physical
lines in 24 templates. Django's lexer can treat those expressions as literal
text instead of tags. A skipped opening tag then produces misleading errors at
a later `endif`, `endfor`, or `endblock`; other damaged expressions silently show
raw template text in otherwise renderable pages.

Repairs join only whitespace inside `{% ... %}` and `{{ ... }}`. No conditions,
include arguments, URL names, blocks, field values, or permissions were changed.
The existing surrounding HTML formatting and design were preserved, including
unrelated incident edits. No general HTML/Django formatter was run.

| Repaired template | Wrapped expressions |
| --- | ---: |
| `templates/components/pagination.html` | 2 |
| `apps/finance/templates/finance/_payment_table.html` | 6 |
| `apps/finance/templates/finance/_invoice_summary.html` | 6 |
| `apps/finance/templates/finance/payment_detail.html` | 7 |
| `apps/finance/templates/finance/invoice_detail.html` | 5 |
| `apps/purchasing/templates/purchasing/purchase_invoices/list.html` | 5 |
| `apps/purchasing/templates/purchasing/purchase_invoices/form.html` | 19 |
| `apps/purchasing/templates/purchasing/purchase_invoices/detail.html` | 20 |
| `apps/catalog/templates/catalog/medicines/unit_form.html` | 8 |
| `apps/catalog/templates/catalog/medicines/list.html` | 8 |
| `apps/catalog/templates/catalog/medicines/form.html` | 14 |
| `apps/catalog/templates/catalog/medicines/detail.html` | 30 |
| `apps/catalog/templates/catalog/medicines/barcode_form.html` | 5 |
| `apps/catalog/templates/catalog/manufacturers/list.html` | 10 |
| `apps/catalog/templates/catalog/manufacturers/form.html` | 6 |
| `apps/catalog/templates/catalog/categories/list.html` | 11 |
| `apps/catalog/templates/catalog/categories/form.html` | 5 |
| `apps/parties/templates/parties/suppliers/list.html` | 12 |
| `apps/parties/templates/parties/suppliers/form.html` | 11 |
| `apps/parties/templates/parties/customers/list.html` | 12 |
| `apps/parties/templates/parties/customers/form.html` | 10 |
| `apps/core/templates/core/settings/index.html` | 39 |
| `apps/parties/templates/parties/prescribers/list.html` | 11 |
| `apps/parties/templates/parties/prescribers/form.html` | 8 |

Shared `registry_filters.html` was already modified for Finance integration but
had no remaining wrapped expressions. Other new Finance templates were checked
too; the audit was not limited to tracked files or the finance app.

## Regression protection

- `apps/dashboard/test_template_integrity.py` compiles all 57 project templates
  and separately rejects multiline Django expressions. Both tests pass: compiler
  validation alone does not catch expressions silently treated as plain text.
- Existing Catalog, Settings, and pagination UI assertions now tolerate legal
  HTML whitespace while preserving heading-count, snapshot-value, and ARIA
  checks. These changes avoid needlessly reverting valid HTML wrapping.
- The dashboard navigation test now recognizes the implemented Payments route
  and checks its destination instead of expecting it to be unavailable.
- Existing finance service tests remain unchanged.

## Browser verification

Verified with a disposable, isolated local PostgreSQL test database and normal
permissioned QA account. No seeded application data or Neon was used.

- Customer and supplier registries render shared PHARMANEX controls and badges.
- Customer pagination, debounced search/page reset, immediate status filtering,
  and filtered empty states work in the browser.
- Customer missing-reference and overpayment errors retain entered values;
  valid posting leads to the payment detail and updated invoice totals.
- Customer and supplier reversals retain the original amount/record and restore
  invoice balances; reason omission works. Escape closes the modal and restores
  trigger focus. Automated tests also cover denied and repeated reversals.
- Purchase invoice payment history leads to the proper supplier entry form;
  supplier posting and reversal work through that flow.
- Desktop (1280/1440px) and mobile (390px) layouts were inspected. Browser checks
  found an additional Finance mobile issue: absolutely positioned screen-reader
  labels escaped the unpositioned table scroll container. Adding `relative` only
  to the Finance payment and invoice-selector scroll wrappers contains those
  labels. Both registries and invoice selection now have no page-level horizontal
  overflow; the tables still scroll locally. Forms and record summaries stack.
- No raw Django tags remain in inspected pages. No browser console errors or
  warnings occurred during the styled Finance verification. Initial QA-harness
  static-file 404s were resolved before UI verification, without app changes.

## Formatter follow-up

No formatter script was found in `package.json`, and `.vscode/settings.json`
contains file exclusions only. The exact external/editor formatter source was
not identified. Exclude Django templates from general HTML formatters or use a
Django-aware formatter in a separate follow-up. No formatting policy was changed.

## Check results and remaining caveat

- `uv run manage.py check`: passed.
- Finance: 68 tests passed, including all 42 UI tests and unchanged service tests.
- Purchasing: 18 tests passed.
- Dashboard/Core/Parties/Catalog/Sales: 135 tests passed, including the two new
  integrity checks across 57 templates.
- Final focused Finance/Purchasing/template-integrity run: 88 tests passed.
- Full suite: 287 tests run, 286 passed, one unrelated failure:
  `apps.accounts.tests.LoginViewTests.test_invalid_credentials_show_error_toast_and_keep_username`.
  The unchanged login template renders the default non-field authentication
  error while the unchanged test expects that text to be absent. The accounts
  app and its shared authentication template/components have no working-tree
  diff. Authentication behavior was intentionally not changed in this recovery.
- `npm run build:css`, `npm run build:js`, and all 12 registry-filter JavaScript
  tests passed. `git diff --check` passed (only Git LF/CRLF notices).

The formatter-induced breakage and Finance verification are resolved. The full
app-wide suite is not entirely green because of the separate login test mismatch.

Suggested commit message once reviewed: `fix: restore Django template integrity and verify finance UI`.

## Safety

No models, services, migrations, application schema, seeded data, dependency
versions, or production settings were modified. No commit or push was made.
