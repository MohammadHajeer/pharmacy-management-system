# Deployment and Docker

PHARMANEX has three distinct runtime workflows:

| Workflow | Settings | Environment source | Web server | Purpose |
| --- | --- | --- | --- | --- |
| Local development | `config.settings` | `.env` | Django `runserver` | Daily development with debug tools and the Tailwind watcher |
| Local Docker | `config.settings_production` | `docker.env` | Gunicorn | Production-style testing on the developer machine |
| Render | `config.settings_production` | Render environment variables | Gunicorn | Real production deployment |

Docker is a local production-style validation path. Render remains the real
production target.

## Environment files

`.env` belongs to the host-based `uv`/Django development workflow. The base
settings load it with `python-dotenv`.

`docker.env` belongs only to local Docker runs. The npm Docker command passes it
to the container with `--env-file docker.env`; Docker does not copy it into the
image. It is intentionally listed in both `.gitignore` and `.dockerignore`.
Treat it as a private local file and never commit, share, or deploy it to Render.

Create `docker.env` in the repository root with these values:

```dotenv
DATABASE_URL=<NEON_POSTGRESQL_CONNECTION_URL>
DJANGO_SECRET_KEY=<LONG_RANDOM_LOCAL_SECRET>
DJANGO_SETTINGS_MODULE=config.settings_production
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
DJANGO_SECURE_SSL_REDIRECT=False
DJANGO_SESSION_COOKIE_SECURE=False
DJANGO_CSRF_COOKIE_SECURE=False
```

`DATABASE_URL` must be the intended Neon PostgreSQL application connection URL.
Production settings require PostgreSQL SSL and do not fall back to SQLite.

The three `False` values allow plain HTTP only for local Docker testing. When
those variables are absent, the production settings default all three values to
`True`. Do not set them to `False` on Render; Render terminates HTTPS and forwards
the original protocol to Django.

Render should store its own `DATABASE_URL`, `DJANGO_SECRET_KEY`, allowed host,
trusted HTTPS origin, and other secrets in the Render environment—not in
`docker.env`. `RENDER_EXTERNAL_HOSTNAME` is also recognized by the production
settings.

## Build and run locally

Use the npm shortcuts:

```bash
npm run docker:build
npm run docker:run
```

`docker:build` creates the `pharmanex:local` image. `docker:run` starts a
temporary container named `pharmanex`, publishes container port 8000 as host
port 8000, and injects `docker.env`. Open
[http://localhost:8000](http://localhost:8000).

The underlying behavior is equivalent to building with `docker build --tag
pharmanex:local .` and running with `docker run --rm --name pharmanex --publish
8000:8000 --env-file docker.env pharmanex:local`.

The run command stays attached to the container. Press `Ctrl+C`, or stop it from
another terminal:

```bash
npm run docker:stop
```

Because the run command uses `--rm`, Docker removes the stopped container. The
reusable `pharmanex:local` image remains available.

## What the Docker image contains

The multi-stage `Dockerfile`:

1. installs locked frontend dependencies with `npm ci`;
2. builds Tailwind CSS v4 and copies the Chart.js browser distribution;
3. installs locked Python dependencies from `pyproject.toml` and `uv.lock` with
   `uv sync --frozen`;
4. copies only the application and built assets into a small Python runtime;
5. runs `collectstatic` with the production static configuration; and
6. starts `config.wsgi:application` with Gunicorn as a non-root user.

Gunicorn binds to `0.0.0.0:8000` by default and uses threaded workers so an
incomplete local connection does not block a worker. WhiteNoise serves the
compressed, content-hashed files created by `collectstatic`, including the
compiled Tailwind stylesheet. Node.js, npm, and the frontend dependency tree are
build-stage tools and are not included in the final runtime image.

The non-secret values used by the Dockerfile while running `collectstatic` are
build-only settings placeholders. They do not connect to a database and are not
a production database fallback. Real runtime values always come from the
container environment.

## Database, migrations, and seed data

Docker does not bundle PostgreSQL. The container connects over the network to
the Neon database in `DATABASE_URL`, so a PostgreSQL service and
`docker-compose.yml` are not needed for the current architecture.

The Docker image build and Gunicorn startup never run migrations. After reviewing
the target database and migration plan, an operator can apply them explicitly:

```bash
docker run --rm --env-file docker.env pharmanex:local python manage.py migrate --noinput
```

This command is intentionally separate from `npm run docker:run`. Do not add an
automatic migration entrypoint without a coordinated deployment decision.

Docker also never runs `seed_dev_auth`, `seed_demo_data`, or
`seed_demo_transactions`. Development/demo seeding remains an explicit,
development-only action and must not be part of a production-style container
startup.

## Render production

Render remains the real PHARMANEX production deployment target. Its environment
must provide the production database URL, secret key, hostname/origin values,
and any service-specific variables. Keep HTTPS redirect and secure-cookie
settings enabled by relying on their secure defaults.

The local Docker shortcuts do not replace or modify the Render deployment
pipeline. Use Docker to verify that the locked dependencies, frontend build,
static collection, Gunicorn startup, and Neon connectivity work together before
shipping a deployment.
