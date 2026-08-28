from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from web.routes import router

ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))

_ERROR_TITLES = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    408: "Request Timeout",
    429: "Too Many Requests",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}


def create_app() -> FastAPI:
    app = FastAPI(title="MELE Review")
    app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
    app.include_router(router)

    def _err(request: Request, code: int, title: str, msg: str):
        accept = request.headers.get("accept", "")
        if "application/json" in accept and "text/html" not in accept:
            return JSONResponse({"error": title, "code": code}, status_code=code)
        return templates.TemplateResponse(request, "error.html", {"code": code, "title": title, "message": msg}, status_code=code)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = exc.status_code if exc.status_code in _ERROR_TITLES else 500
        title = _ERROR_TITLES.get(code, "Error")
        msg = str(exc.detail) if code != 404 else "The page you're looking for doesn't exist."
        return _err(request, code, title, msg)

    @app.exception_handler(Exception)
    async def _exc(request: Request, exc: Exception):
        if isinstance(exc, StarletteHTTPException):
            return await _http(request, exc)
        return _err(request, 500, "Internal Server Error", "Something went wrong.")

    return app


app = create_app()
