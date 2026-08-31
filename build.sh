#!/usr/bin/env bash
set -o errexit
set -o pipefail

python -m pip install --disable-pip-version-check uv
uv sync --frozen --no-dev
npm ci
npm run build:css
uv run python manage.py collectstatic --noinput
uv run python manage.py migrate --noinput
