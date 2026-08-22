from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy import func, inspect, select, text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from api.config import get_config

logger = logging.getLogger("melereview-api")


def _configure_structlog() -> None:
    """Configure structlog JSON logging if the library is installed (optional dep)."""
    try:
        import structlog  # type: ignore

        # Ensure contextvars processor is available
        import structlog.contextvars
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


_grpc_server = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run adaptive DB migration on startup, start gRPC, then yield."""
    await _init_db()
    # Start gRPC server on 0.0.0.0:50051 (internal)
    global _grpc_server
    try:
        from api.grpc_server import create_grpc_server

        _grpc_server = await create_grpc_server()
        await _grpc_server.start()
        logger.info("grpc server started on 0.0.0.0:50051")
    except Exception as e:
        logger.warning("grpc server failed to start: %s: %s", type(e).__name__, e)
        _grpc_server = None
    try:
        yield
    finally:
        if _grpc_server is not None:
            try:
                await _grpc_server.stop(grace=5)
                logger.info("grpc server stopped")
            except Exception:
                pass


async def _init_db() -> None:
    """Create tables if missing and adapt columns. Retries 10x with clip check."""
    from api.db import _get_engine
    from api.models import Base

    engine = _get_engine()
    for attempt in range(1, 11):
        try:
            async with engine.begin() as conn:

                def _sync_migrate(sync_conn):
                    insp = inspect(sync_conn)
                    is_mysql = sync_conn.dialect.name == "mysql"
                    existing_tables = insp.get_table_names()
                    expected_tables = list(Base.metadata.tables.keys())
                    missing = set(expected_tables) - set(existing_tables)
                    if missing:
                        # MySQL needs FK checks off to create tables with FKs
                        if is_mysql:
                            sync_conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
                        Base.metadata.create_all(bind=sync_conn)
                        if is_mysql:
                            sync_conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
                        # Refresh inspector after creation
                        insp = inspect(sync_conn)
                        existing_tables = insp.get_table_names()
                    # Adaptive column handling for missing or resized columns
                    for table in Base.metadata.sorted_tables:
                        tname = table.name
                        if tname not in existing_tables:
                            continue
                        try:
                            existing_cols = {c["name"]: c for c in insp.get_columns(tname)}
                        except Exception:
                            continue
                        for col in table.columns:
                            cname = col.name
                            if cname not in existing_cols:
                                try:
                                    coltype = col.type.compile(dialect=sync_conn.dialect)
                                except Exception:
                                    coltype = str(col.type)
                                nullable = "" if col.nullable else " NOT NULL"
                                default_sql = ""
                                if col.server_default is not None:
                                    try:
                                        arg = col.server_default.arg
                                        if hasattr(arg, "text"):
                                            default_sql = f" DEFAULT {arg.text}"
                                        else:
                                            default_sql = f" DEFAULT {arg}"
                                    except Exception:
                                        pass
                                sql = (
                                    f"ALTER TABLE {tname} ADD COLUMN {cname} "
                                    f"{coltype}{nullable}{default_sql}"
                                )
                                sync_conn.execute(text(sql))
                            else:
                                existing_type = existing_cols[cname]["type"]
                                existing_len = getattr(existing_type, "length", None)
                                model_len = getattr(col.type, "length", None)
                                if (
                                    model_len is not None
                                    and existing_len is not None
                                    and model_len != existing_len
                                ):
                                    if model_len < existing_len:
                                        col_expr = table.c[cname]
                                        # Check MAX(CHAR_LENGTH) before shrinking — avoid clip
                                        max_len = sync_conn.scalar(
                                            select(func.max(func.char_length(col_expr)))
                                        )
                                        if max_len is not None and max_len > model_len:
                                            raise RuntimeError(
                                                f"would clip data in {tname}.{cname}: "
                                                f"max CHAR_LENGTH {max_len} > "
                                                f"new length {model_len}"
                                            )
                                    # MySQL MODIFY COLUMN for type/length change
                                    if is_mysql:
                                        try:
                                            new_type = col.type.compile(dialect=sync_conn.dialect)
                                        except Exception:
                                            new_type = str(col.type)
                                        nullable_sql = "NULL" if col.nullable else "NOT NULL"
                                        modify_sql = (
                                            f"ALTER TABLE {tname} MODIFY COLUMN {cname} "
                                            f"{new_type} {nullable_sql}"
                                        )
                                        sync_conn.execute(text(modify_sql))
                                    else:
                                        # SQLite lacks MODIFY COLUMN; skip safely
                                        pass

                await conn.run_sync(_sync_migrate)
            logger.info("database tables ready")
            return
        except RuntimeError:
            raise
        except Exception as e:
            if attempt == 10:
                logger.exception("database not ready after 10 attempts")
                raise
            logger.warning(
                "database not ready (attempt %s/10): %s: %s", attempt, type(e).__name__, e
            )
            await asyncio.sleep(3)


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
