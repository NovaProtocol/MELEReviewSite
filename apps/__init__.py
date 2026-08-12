from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from apps.config import get_config

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    from apps.db import _get_engine
    from apps.models import Base

    async with _get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


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

    app.include_router(api_router)
    app.include_router(web_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
