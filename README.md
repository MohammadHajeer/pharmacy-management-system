# Pharmacy Management System

## Requirements

- Python and [uv](https://docs.astral.sh/uv/)
- Node.js and npm
- Docker Desktop (optional, for production-style container testing)

## Setup

```bash
uv sync
npm install
uv run manage.py migrate
uv run manage.py seed_dev_auth
npm run dev
```

## Development

```bash
npm run dev
```

This starts the Django development server and the Tailwind CSS watcher. Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) and press `Ctrl + C` to stop development.

## Production-style Docker check

Docker runs the application locally with `config.settings_production`, Gunicorn,
WhiteNoise, built Tailwind assets, and the configured Neon PostgreSQL database.
Create the private, gitignored `docker.env` described in the
[deployment guide](docs/DEPLOYMENT.md), then run:

```bash
npm run docker:build
npm run docker:run
```

Open [http://localhost:8000](http://localhost:8000). From another terminal, stop
and remove the container with:

```bash
npm run docker:stop
```

The Docker workflow does not run migrations or seed data automatically. Render
remains the production deployment target; this container workflow is for local
production-style verification.

## Other useful commands

```bash
npm run makemigrations
npm run test
npm run shell
npm run build:css
```
