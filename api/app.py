from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from api.config import get_config

logger = logging.getLogger("melereview-api")


def _configure_structlog() -> None:
    """Configure structlog JSON logging if the library is installed (optional dep)."""
    try:
        import structlog  # type: ignore
        import structlog.contextvars  # ensure contextvars processor available
        import structlog.processors  # type: ignore

        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.NOTSET),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
        # Also set standard library root to INFO so JSON lines appear
        logging.basicConfig(level=logging.INFO, format="%(message)s")
    except ImportError:
        # structlog is optional — fall back to stdlib logging
        pass
    except Exception:
        # Never crash app startup on logging misconfig
        pass


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach X-Request-ID to every response; propagate inbound value or generate UUID.

    Also binds ``account_id`` to structlog context if a valid session cookie is present,
    so every log line includes both ``request_id`` and ``account_id`` when authenticated.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        # Bind request_id to structlog context if available (optional, no hard dep)
        try:
            import structlog.contextvars  # type: ignore

            structlog.contextvars.bind_contextvars(request_id=request_id)
        except Exception:
            pass
        # Also bind account_id if session cookie is valid
        _bound_account = False
        try:
            import structlog.contextvars as _ctx  # type: ignore

            cookie = request.cookies.get("session")
            if cookie:
                # Lazy import to avoid circular dependency at module import time
                from api.routes.auth import read_session_cookie

                aid = read_session_cookie(cookie)
                if aid is not None:
                    _ctx.bind_contextvars(account_id=aid)
                    _bound_account = True
        except Exception:
            pass
        # Also store on request state for handlers to use
        request.state.request_id = request_id
        # Structured log at start (optional — no hard dep on structlog)
        try:
            import structlog  # type: ignore

            _slog = structlog.get_logger("melereview-api.request")
            _slog.info("request.start", method=request.method, path=request.url.path)
        except Exception:
            logger.info(
                "request.start method=%s path=%s request_id=%s",
                request.method,
                request.url.path,
                request_id,
            )
        response = None
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            # Ensure CORS can expose it
            existing = response.headers.get("Access-Control-Expose-Headers", "")
            expose = "X-Request-ID, X-Total-Count"
            if existing:
                # merge without duplication
                parts = {p.strip() for p in existing.split(",") if p.strip()}
                for h in expose.split(","):
                    parts.add(h.strip())
                response.headers["Access-Control-Expose-Headers"] = ", ".join(sorted(parts))
            else:
                response.headers["Access-Control-Expose-Headers"] = expose
            return response
        finally:
            try:
                import structlog.contextvars as _ctx2  # type: ignore

                keys = ["request_id", "account_id"] if _bound_account else ["request_id"]
                _ctx2.unbind_contextvars(*keys)
            except Exception:
                pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _init_db()
    yield


def _run_alembic_upgrade(sync_url: str) -> None:
    """Synchronous helper to run alembic upgrade head (run in threadpool)."""
    from alembic.config import Config as AlembicConfig

    from alembic import command

    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(alembic_cfg, "head")


async def _init_db() -> None:
    from api.db import _get_engine
    from api.models import Base

    cfg = get_config()
    db_url = cfg.db_url

    # Fast path for tests: SQLite uses create_all (no alembic overhead)
    if "sqlite" in db_url:
        engine = _get_engine()
        for attempt in range(1, 11):
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                logger.info("database tables ready (sqlite create_all)")
                return
            except Exception as e:
                if attempt == 10:
                    logger.exception("database not ready after 10 attempts")
                    raise
                logger.warning(
                    "database not ready (attempt %s/10): %s: %s", attempt, type(e).__name__, e
                )
                await asyncio.sleep(3)
        return

    # Production MySQL: use alembic migrations with retry
    sync_url = db_url.replace("+aiomysql", "+pymysql").replace("+aiosqlite", "")
    for attempt in range(1, 11):
        try:
            await asyncio.to_thread(_run_alembic_upgrade, sync_url)
            logger.info("database tables ready (alembic upgrade head)")
            return
        except Exception as e:
            if attempt == 10:
                logger.exception("database not ready after 10 alembic attempts")
                raise
            logger.warning(
                "alembic not ready (attempt %s/10): %s: %s", attempt, type(e).__name__, e
            )
            await asyncio.sleep(3)


async def _drop_sources(engine) -> None:
    """One-time cleanup: the old PDF sources concept is gone. Drop the table."""
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS sources"))


async def _migrate_columns(engine) -> None:
    from sqlalchemy import text

    # Statements that apply to all dialects (MySQL and SQLite).
    universal = [
        "ALTER TABLE accounts ADD COLUMN disabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE accounts ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE questions ADD COLUMN account_id INT NULL",
    ]
    # MySQL-only statements (SQLite parses FKs inline at table-create time).
    mysql_only = [
        "ALTER TABLE questions ADD CONSTRAINT fk_question_author FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL",
    ]

    dialect = engine.dialect.name
    statements = list(universal)
    if dialect == "mysql":
        statements.extend(mysql_only)
    else:
        logger.info("skipping MySQL-only migrations on dialect=%s", dialect)

    async with engine.begin() as conn:
        for stmt in statements:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                # Idempotent migration: ignore "already exists" so re-runs are safe.
                # ANY OTHER error is unexpected and must be surfaced — it almost
                # certainly means a real schema problem.
                msg = str(e).lower()
                if "already exists" not in msg and "duplicate" not in msg:
                    logger.exception("unexpected migration failure for %s", stmt)
                    raise


def create_app() -> FastAPI:
    _configure_structlog()
    config = get_config()

    app = FastAPI(
        title="MELE Review API",
        description="MELE Board Exam Reviewer API",
        version="0.1.0",
        debug=config.DEBUG,
        lifespan=lifespan,
    )

    # CORS — allow_origins configurable via Settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Total-Count", "X-Request-ID"],
    )
    app.add_middleware(RequestIDMiddleware)

    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from api.routes.auth import limiter
    from api.routes.auth import router as auth_router
    from api.routes.questions import router as questions_router
    from api.routes.solutions import router as solutions_router
    from api.routes.thermo import router as thermo_router

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    app.include_router(auth_router)
    app.include_router(questions_router)
    app.include_router(solutions_router)
    app.include_router(thermo_router)

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok"}

    # OpenAPI tweaks: ensure X-Total-Count is documented
    orig_openapi = app.openapi

    def custom_openapi():
        schema = orig_openapi()
        schema["info"]["x-request-id"] = "X-Request-ID header is returned on every response"
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]

    return app


app = create_app()
