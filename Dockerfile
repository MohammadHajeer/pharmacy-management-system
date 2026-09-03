# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.13
ARG NODE_VERSION=22
ARG UV_VERSION=0.12.5

FROM node:${NODE_VERSION}-bookworm-slim AS frontend

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

# Tailwind v4 scans the Django templates and apps declared in input.css. The
# JavaScript build also copies Chart.js from node_modules into static/vendor.
COPY assets/ ./assets/
COPY scripts/ ./scripts/
COPY templates/ ./templates/
COPY apps/ ./apps/
COPY static/ ./static/
RUN npm run build


FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv


FROM python:${PYTHON_VERSION}-slim-bookworm AS python-dependencies

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project


FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV DJANGO_SETTINGS_MODULE=config.settings_production \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8000 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system django \
    && adduser --system --ingroup django --home /home/django django

COPY --from=python-dependencies --chown=django:django /app/.venv /app/.venv
COPY --chown=django:django manage.py ./
COPY --chown=django:django config/ ./config/
COPY --chown=django:django apps/ ./apps/
COPY --chown=django:django templates/ ./templates/
COPY --chown=django:django static/ ./static/
COPY --from=frontend --chown=django:django /app/static/css/output.css /app/static/css/output.css
COPY --from=frontend --chown=django:django /app/static/vendor/chartjs/ /app/static/vendor/chartjs/

# collectstatic only needs a valid settings configuration. These non-secret,
# build-only placeholders are scoped to this command and are not retained in
# the runtime environment; the application still requires the real Neon URL
# and secret key when the container starts.
RUN DJANGO_SECRET_KEY=collectstatic-build-placeholder \
    DATABASE_URL=postgresql://build:build@localhost:5432/build \
    ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

USER django

EXPOSE 8000

CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --worker-class gthread --workers ${WEB_CONCURRENCY:-2} --threads ${GUNICORN_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-30} --access-logfile - --error-logfile -"]
