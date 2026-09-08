# Getting Started

## Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Docker & Docker Compose | Latest | All services (recommended) |
| Python | >= 3.14 | Local dev without Docker |
| `pre-commit` | Latest | Lint / type gates |

## 1. Configure Environment

Env vars are injected by `compose.yaml` interpolation — no `.env` file is read by the app. `.env.example` documents every variable; export them in your shell or deployment tool.

Required:

| Variable | Description |
|----------|-------------|
| `DEPLOYMENT_TYPE` | `debug` or `production` |
| `MYSQL_PASS` | MySQL root password |
| `SECRET_KEY` | >=32 chars, JWT signing HS256 |

Optional (with defaults):

| Variable | Default | Description |
|----------|---------|-------------|
| `MYSQL_HOST` | `mysql-db` | Compose service DNS |
| `MYSQL_PORT` | `3306` | MySQL port |
| `MYSQL_USER` | `root` | DB user |
| `MYSQL_DATABASE` | `MELEReview` | DB name |
| `DATABASE_URL` | (built from MYSQL_*) | Full SQLAlchemy URL override |
| `CORS_ALLOW_ORIGINS` | `["*"]` | CORS origins |

Generate a secret:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## 2. Local Development (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r api/requirements.txt -r web/requirements.txt
pip install -e ".[dev]"   # pytest, ruff, mypy, pre-commit, alembic

export DEPLOYMENT_TYPE=debug MYSQL_PASS=devpass SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
# optional: DATABASE_URL=sqlite+aiosqlite:////tmp/dev.db

alembic upgrade head  # or rely on adaptive boot migration

uvicorn api.app:app --port 8082 --reload
uvicorn web.app:app --port 8081 --reload  # separate terminal
# Docs preview:
pip install -r documentation/requirements.txt
mkdocs serve  # http://localhost:8000
```

## 3. Docker (production-like)

```bash
export DEPLOYMENT_TYPE=debug MYSQL_PASS=changeme SECRET_KEY=changeme-must-be-at-least-32-characters-long
docker compose up -d --build
# Caddy on :7060; tunnel ingress points at the caddy container
docker compose ps
curl http://127.0.0.1:7060/health
```

Migrations run automatically on container start via adaptive boot (`api/app.py` `lifespan`) with retry + `FOREIGN_KEY_CHECKS` toggling. Alembic is still available for explicit migrations:

```bash
alembic revision --autogenerate -m "add foo"
alembic upgrade head
```

## 4. Tests and Gates

```bash
pre-commit run --all-files
ruff check .
ruff format --check .
mypy .
pytest -q
# docs build
mkdocs build --strict --site-dir /tmp/site
```
