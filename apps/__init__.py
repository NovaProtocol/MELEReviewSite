from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from apps.config import get_config

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app() -> FastAPI:
    config = get_config()

    app = FastAPI(
        title="MELE Review",
        description="MELE Board Exam Reviewer",
        debug=config.DEBUG,
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
