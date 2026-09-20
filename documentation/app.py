from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from cache import CacheControlMiddleware

SITE_DIR = Path(__file__).resolve().parent / "site"

app = FastAPI(title="MELE Review Docs")
_DEBUG_DEPLOY = os.environ.get("DEPLOYMENT_TYPE", "").lower() in ("debug", "development")
app.add_middleware(CacheControlMiddleware, is_debug=_DEBUG_DEPLOY)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(SITE_DIR / "index.html")


@app.get("/{path:path}")
async def serve_docs(path: str):
    if not path:
        path = "index.html"
    parts = path.rstrip("/")
    candidates = [parts, os.path.join(parts, "index.html"), parts + ".html"]
    for c in candidates:
        full = os.path.normpath(os.path.join(str(SITE_DIR), c))
        if (full == str(SITE_DIR) or full.startswith(str(SITE_DIR) + os.sep)) and os.path.isfile(
            full
        ):
            return FileResponse(full)
    return JSONResponse({"error": "Not found"}, status_code=404)
