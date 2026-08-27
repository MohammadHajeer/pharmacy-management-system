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

## Button

```django
{% include "components/button.html" with text="Save medicine" variant="primary" type="submit" %}
{% include "components/button.html" with text="Cancel" variant="secondary" href="/" %}
{% include "components/button.html" with text="Delete" variant="danger" disabled=True %}
```

Variants are `primary`, `secondary`, `danger`, and `ghost`. Buttons can also open shared UI behaviors without custom markup:

```django
{% include "components/button.html" with text="Open modal" variant="primary" modal_target="confirm-modal" %}
{% include "components/button.html" with text="Show toast" variant="secondary" toast_level="success" toast_message="Saved successfully." %}
```

## Input

```django
{% include "components/input.html" with name="medicine_name" label="Medicine name" required=True %}
{% include "components/input.html" with name="sku" label="SKU" value=form.sku.value error=form.sku.errors %}
{% include "components/textarea.html" with name="notes" label="Notes" rows="4" %}
{% include "components/select.html" with name="category" label="Category" options=category_options value=form.category.value %}
```

Select options are dictionaries with `value`, `label`, and an optional `disabled` value. Pass a bound field's `.errors` to show Django validation feedback.

## Badge

```django
{% include "components/badge.html" with text="Paid" variant="success" %}
{% include "components/badge.html" with text="Low stock" variant="warning" %}
{% include "components/badge.html" with text="Overdue" variant="danger" %}
```

Variants are `default`, `primary`, `success`, `warning`, `danger`, and `info`.

## Card

```django
{% include "components/card.html" with eyebrow="Today's sales" metric="$2,450" text="8.4% above yesterday" %}
```

The optional values are `eyebrow`, `title`, `metric`, `text`, and `footer`.

## Modal

Render a modal once, then open it from any button whose `data-modal-open` matches its ID:

```django
{% include "components/button.html" with text="Open modal" variant="primary" modal_target="confirm-modal" %}
{% include "components/modal.html" with modal_id="confirm-modal" title="Confirm change" body="Review this change before continuing." confirm_text="Continue" %}
```

Buttons with `data-modal-close`, the backdrop, and the Escape key close it. Focus stays inside while it is open.

## Toasts

Use Django's standard messages API. The base template automatically turns messages into stacked, dismissible notifications.

```python
from django.contrib import messages

messages.success(request, "Medicine added successfully.")
messages.error(request, "Something went wrong.")
messages.warning(request, "Stock is running low.")
messages.info(request, "The report is being prepared.")
```

## Sidebar navigation

Navigation is configured once in `config/navigation.py`; views do not pass link lists. When a feature app is added, set its namespaced `url_name` (for example, `medicines:index`) and optionally its Django permission (for example, `medicines.view_medicine`).

`config/context_processors.py` hides links the current user cannot access, safely disables links whose URL does not exist yet, and marks items active by comparing the configured namespace with `request.resolver_match.namespace`. Use Django Groups and Permissions for roles—do not add a separate authorization system.
