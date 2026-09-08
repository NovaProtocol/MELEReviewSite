# MELE Review

Board-exam reviewer for Philippine Mechanical Engineering licensure exams.
Question-only project: multiple-choice questions with per-user solutions, a
login/account system, and a suite of ME calculators including the thermodynamic
cycle solver.

**Stack:** Python 3.14 + FastAPI + Granian + CoolProp + MySQL; Caddy gateway. Auth PyJWT HS256 ISS=MELEReview AUD=account exp 30d (not itsdangerous).
Alembic for migrations, Ruff + Mypy + pre-commit for lint/type checks,
structlog JSON logging with X-Request-ID tracing.

## Structure

```text
api/     backend (port 8082, gRPC 50051 internal expose only): MySQL models + services + REST API + thermo solver + gRPC server
  routes/      auth, questions, solutions, thermo (/api/*)
  services/    account, question, solution services
  thermo/      cycle solver ported from MESimulator (CoolProp, no tables)
web/     frontend (port 8081): pages + static; the browser calls /api/* through caddy
caddy/   reverse proxy: /api/* -> api, everything else -> web (:7060) (gRPC 50051 never via Caddy)
alembic/ migrations (alembic.ini at project root)
```

## Features

- **Accounts** — Netflix-style login: pick a profile, enter its pin. Pins are
  stored plainly (low-value personal tool). Each account's answers/solutions
  are stored per question. See `docs/adr/001-plain-pin.md`.
- **Questions** — multiple choice, multiple tags per question, searchable and
  filterable by tag. A question can be temporarily hidden (`active=false`).
  Answering saves your per-account solution and shows instant right/wrong
  feedback with the stored solution.
- **Solution blocks** — rich per-question solutions (v2): typed blocks
  (`text`, `math`, `image`) stored as JSONB/JSON. Backend validates via
  `Block` union (Pydantic); frontend renders via `createBlocksEditor`.
  Endpoints `GET/PUT /api/questions/{id}/solution` persist the block array.
- **Counts** — every list endpoint returns `X-Total-Count` for pagination.
- **Edit in-app** — add / edit / delete questions via the menu (no upload API).
  Deleting a question cascades to its solutions.
- **Calculators**
  - Thermo cycles (Carnot, Otto, Diesel, Dual, Brayton, Rankine,
    vapor-compression) — live T-s / P-v / any-axis diagrams with the saturation
    dome (data returned, rendered with Plotly)
  - Unit converter, fluid mechanics (pipe flow), strength of materials,
    heat transfer, psychrometrics, machine design

## Development Setup

```bash
# 1. Clone and create venv
python -m venv .venv && source .venv/bin/activate
pip install -r api/requirements.txt -r web/requirements.txt
pip install -e ".[dev]"   # pytest, ruff, mypy, pre-commit, alembic, etc

# 2. Configure env
cp .env.example .env
# edit .env: set DEPLOYMENT_TYPE, MYSQL_PASS, SECRET_KEY (>=32 chars)

# 3. Install pre-commit hooks (ruff + ruff-format + mypy)
pre-commit install

# 4. Run linters / type checks
pre-commit run --all-files
ruff check .
ruff format --check .
mypy .

# 5. Apply DB migrations (production MySQL; SQLite tests use create_all)
alembic upgrade head
# New migration after model changes:
# alembic revision --autogenerate -m "add foo"

# 6. Run locally (without Docker)
export DEPLOYMENT_TYPE=debug MYSQL_PASS=... SECRET_KEY=...
uvicorn api.app:app --port 8082   # backend
uvicorn web.app:app --port 8081   # frontend

# 7. Run tests
pytest -q
```

## Run

```bash
export DEPLOYMENT_TYPE=debug MYSQL_PASS=... SECRET_KEY=...
python -m venv .venv && source .venv/bin/activate
pip install -r api/requirements.txt -r web/requirements.txt
pip install -e ".[dev]"
alembic upgrade head
uvicorn api.app:app --port 8082   # backend
uvicorn web.app:app --port 8081   # frontend
```

Migrations run automatically on container start via `alembic upgrade head`
(with retry). For local SQLite testing, tables are created via `create_all`.

### Deploy

```bash
docker compose up -d --build
```

Caddy on `:7060`; the tunnel ingress points at the caddy container.
Compose includes healthchecks for `api`, `web`, and `mysql-db`.

## Auth

Session cookie `session` (signed PyJWT HS256, httponly, samesite lax, secure=!DEBUG, max_age 30d, iss/aud/jti). `api/jwt.py` ISS=MELEReview AUD=account exp 30d. `get_current_account` → 401 when missing/invalid/expired/disabled.

## Ports

| Service | Port | Publish |
|---------|------|---------|
| API | 8082 | expose only via Caddy `:7060 /api/*` |
| Web | 8081 | expose only via Caddy `:7060 /*` |
| gRPC | 50051 | expose only internal, never `ports:` |
| Docs | 8005 | expose only via Caddy `/documentation/*` |

## Errors

JS: `console.error({status, request_id, stack})` + toast; Server: structlog JSON + X-Request-ID to docker logs; envelope `{error:{code,message,request_id}}`. No traceback to client.

## Observability

- Every response carries `X-Request-ID` (propagated or generated UUID).
- JSON logs via `structlog` include `request_id` and, when authenticated, `account_id` bound via `RequestIDMiddleware`.
- Server errors return `{error:{code,message,request_id}}` with `X-Request-ID` header; JS logs detailed object to browser console + toast.

## API

The browser talks to `/api/*` through caddy. Key endpoints:

- `POST /api/auth/accounts`, `POST /api/auth/login`, `GET /api/auth/me`
- `GET/POST/PUT/DELETE /api/questions`, `GET /api/tags`
- `GET/PUT /api/questions/{id}/solution`, `GET /api/my/solutions` (solution blocks)
- `POST /api/cycle` — thermo solver (`format: data|plot`)
