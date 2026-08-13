from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from apps.config import get_config

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _init_db()
    yield


async def _init_db() -> None:
    from apps.db import _get_engine
    from apps.models import Base

    import asyncio
    import logging

    logger = logging.getLogger("melereview")
    engine = _get_engine()
    for attempt in range(1, 11):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("database tables ready")
            return
        except Exception:
            if attempt == 10:
                raise
            logger.warning("database not ready (attempt %s/10), retrying...", attempt)
            await asyncio.sleep(3)


def create_app() -> FastAPI:
    config = get_config()

    app = FastAPI(
        title="MELE Review",
        description="MELE Board Exam Reviewer",
        debug=config.DEBUG,
        lifespan=lifespan,
    )

    static_dir = _PROJECT_ROOT / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    from apps.routes.api import router as api_router
    from apps.routes.web import router as web_router
    from apps.routes.solution_api import router as sol_router

    app.include_router(api_router)
    app.include_router(web_router)
    app.include_router(sol_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
