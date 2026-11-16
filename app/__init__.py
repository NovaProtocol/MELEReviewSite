from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.cache import CacheControlMiddleware, is_debug_deployment
from app.config import get_config
from app.db import _get_engine
from app.errors import RequestIDMiddleware, install_error_handlers

logger = logging.getLogger("melereview")
ROOT = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.bootstrap import bootstrap

    config = get_config()
    config.upload_dir.mkdir(parents=True, exist_ok=True)
    await bootstrap(_get_engine(), config.ADMIN_USER, config.ADMIN_PASS)

    # Clearing unused uploads only at startup means they pile up between restarts.
    from app.services.media_cleanup import run_periodically

    sweeper = asyncio.create_task(
        run_periodically(config.MEDIA_SWEEP_HOURS, config.MEDIA_GRACE_HOURS)
    )
    try:
        yield
    finally:
        sweeper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweeper


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = get_config()

    app = FastAPI(
        title="MELE Review",
        description="Board-exam reviewer for the Philippine mechanical engineering licensure exam",
        version="1.0.0",
        debug=config.DEBUG,
        lifespan=lifespan,
    )

    app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(CacheControlMiddleware, is_debug=is_debug_deployment())

    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from app.limiter import limiter
    from app.routes import (
        accounts,
        admin,
        auth,
        invites,
        library,
        media,
        media_api,
        pages,
        quiz,
        search,
        tools,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    app.include_router(auth.router)
    app.include_router(accounts.router)
    app.include_router(invites.router)
    app.include_router(library.router)
    app.include_router(media.router)
    app.include_router(media_api.router)
    app.include_router(search.router)
    app.include_router(admin.router)
    app.include_router(tools.router)
    app.include_router(pages.router)
    app.include_router(quiz.router)
    install_error_handlers(app)

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok"}

    return app
