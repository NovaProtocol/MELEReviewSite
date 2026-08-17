from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from web.routes import router

ROOT = Path(__file__).resolve().parent


def create_app() -> FastAPI:
    app = FastAPI(title="MELE Review")
    app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
    app.include_router(router)
    return app


app = create_app()
