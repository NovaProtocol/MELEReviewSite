from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.config import get_config

logger = logging.getLogger("melereview-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _init_db()
    yield


async def _init_db() -> None:
    from api.db import _get_engine
    from api.models import Base

    engine = _get_engine()
    for attempt in range(1, 11):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            await _drop_sources(engine)
            await _migrate_columns(engine)
            logger.info("database tables ready")
            return
        except Exception as e:
            if attempt == 10:
                logger.exception("database not ready after 10 attempts")
                raise
            logger.warning("database not ready (attempt %s/10): %s: %s", attempt, type(e).__name__, e)
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
    config = get_config()

    app = FastAPI(
        title="MELE Review API",
        description="MELE Board Exam Reviewer API",
        debug=config.DEBUG,
        lifespan=lifespan,
    )

    from api.routes.auth import router as auth_router
    from api.routes.questions import router as questions_router
    from api.routes.solutions import router as solutions_router
    from api.routes.thermo import router as thermo_router

    app.include_router(auth_router)
    app.include_router(questions_router)
    app.include_router(solutions_router)
    app.include_router(thermo_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
