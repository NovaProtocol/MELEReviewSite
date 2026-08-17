# MELE Review

Board-exam reviewer for Philippine Mechanical Engineering licensure exams.
Question-only project: multiple-choice questions with per-user solutions, a
login/account system, and a suite of ME calculators including the thermodynamic
cycle solver.

**Stack:** Python 3.14 + FastAPI + Granian + CoolProp + MySQL; Caddy gateway.

## Structure

```
api/     backend (port 8082): MySQL models + services + REST API + thermo solver
  routes/      auth, questions, solutions, thermo (/api/*)
  services/    account, question, solution services
  thermo/      cycle solver ported from MESimulator (CoolProp, no tables)
web/     frontend (port 8081): pages + static; the browser calls /api/* through caddy
caddy/   reverse proxy: /api/* -> api, everything else -> web (:7060)
```

## Features

- **Accounts** — Netflix-style login: pick a profile, enter its pin. Pins are
  stored plainly (low-value personal tool). Each account's answers/solutions
  are stored per question.
- **Questions** — multiple choice, multiple tags per question, searchable and
  filterable by tag. A question can be temporarily hidden (`active=false`).
  Answering saves your per-account solution and shows instant right/wrong
  feedback with the stored solution.
- **Edit in-app** — add / edit / delete questions via the menu (no upload API).
  Deleting a question cascades to its solutions.
- **Calculators**
  - Thermo cycles (Carnot, Otto, Diesel, Dual, Brayton, Rankine,
    vapor-compression) — live T-s / P-v / any-axis diagrams with the saturation
    dome (data returned, rendered with Plotly)
  - Unit converter, fluid mechanics (pipe flow), strength of materials,
    heat transfer, psychrometrics, machine design

## Run

```bash
export DEPLOYMENT_TYPE=debug MYSQL_PASS=... SECRET_KEY=...
python -m venv .venv && source .venv/bin/activate
pip install -r api/requirements.txt -r web/requirements.txt -r requirements-dev.txt
uvicorn api.app:app --port 8082   # backend
uvicorn web.app:app --port 8081   # frontend
```

### Deploy

```bash
docker compose up -d --build
```

Caddy on `:7060`; the tunnel ingress points at the caddy container.

## API

The browser talks to `/api/*` through caddy. Key endpoints:

- `POST /api/auth/accounts`, `POST /api/auth/login`, `GET /api/auth/me`
- `GET/POST/PUT/DELETE /api/questions`, `GET /api/tags`
- `GET/PUT /api/questions/{id}/solution`, `GET /api/my/solutions`
- `POST /api/cycle` — thermo solver (`format: data|plot`)
