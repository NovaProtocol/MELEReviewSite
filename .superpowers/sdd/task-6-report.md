### Task 6: API Quality — Pagination, Error Handling, CORS, Health

**Status:** DONE

**Changes:**
- `api/services/question_service.py`: Replace `func.instr` with `ilike` for dialect-agnostic case-insensitive search; fix `count` query to include joins when `tag` filter is active (prevents wrong total / SQL error)
- `api/routes/questions.py`: Keep list return for backward compat but add `X-Total-Count` header and optional `envelope=true` param returning `{items, total, page, per_page}`; expose headers for CORS
- `api/schemas.py`: Add `PaginatedQuestions` envelope model (`items`, `total`, `page`, `per_page`)
- `api/config.py`: Add `CORS_ALLOW_ORIGINS: list[str]` configurable via env
- `api/app.py`: Add `CORSMiddleware` (allow_origins from Settings, expose `X-Total-Count`, `X-Request-ID`), `RequestIDMiddleware` (propagate/provide `X-Request-ID`, bind to structlog if available), OpenAPI tweaks (version, health tag, custom openapi)
- `tests/conftest.py`: Make `account` fixture handle 409 reuse across module-scoped clients (prevents cross-module pollution)
- `tests/test_config.py`: Restore `DATABASE_URL` and `SECRET_KEY` after each test that reloads config (prevents mysql fallback breaking downstream tests)
- `tests/test_pagination.py`: New TDD tests — pagination header (25 creates, `X-Total-Count` + envelope), case-insensitive search, request ID header, CORS header

**Commits:**
- `feat: add pagination header, case-insensitive search, request ID and CORS` (pending)

**Tests:** 45/45 passing (41 existing + 4 new pagination tests)

**Notes:**
- `GET /api/questions` now always sends `X-Total-Count` and `Access-Control-Expose-Headers`; `?envelope=true` returns paginated object for clients that prefer it
- Search uses `ilike` so `?search=thermo` matches `Thermo` on SQLite, MySQL, Postgres
- CORS `allow_origins=["*"]` by default; override via `CORS_ALLOW_ORIGINS` env (JSON list)
- Request ID is generated via `uuid4` if inbound `X-Request-ID` absent, echoed on response and exposed for CORS
