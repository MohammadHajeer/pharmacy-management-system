# Pharmacy Management System

## Requirements

- Python and [uv](https://docs.astral.sh/uv/)
- Node.js and npm

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

## Other useful commands

```bash
npm run makemigrations
npm run test
npm run shell
npm run build:css
```
