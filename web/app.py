from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from web.errors import RequestIDMiddleware, install_error_handlers
from web.cache import CacheControlMiddleware, is_debug_deployment
from web.routes import router

ROOT = Path(__file__).resolve().parent


def create_app() -> FastAPI:
    app = FastAPI(title="MELE Review")
    app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(CacheControlMiddleware, is_debug=is_debug_deployment())
    app.include_router(router)
    install_error_handlers(app)
    return app
