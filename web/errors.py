from __future__ import annotations

import logging
import uuid

import grpc
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.templating import Jinja2Templates
from pathlib import Path

try:
    import structlog  # type: ignore

    _HAS_STRUCTLOG = True
except ImportError:
    _HAS_STRUCTLOG = False

ROOT = Path(__file__).resolve().parent
_templates = Jinja2Templates(directory=str(ROOT / "templates"))

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


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach X-Request-ID to every response; propagate inbound or generate UUID."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        try:
            import structlog.contextvars as _ctx  # type: ignore

            _ctx.bind_contextvars(request_id=request_id)
        except Exception:
            pass
        request.state.request_id = request_id
        try:
            import structlog as _sl  # type: ignore

            _sl.get_logger("melereview-web.request").info(
                "request.start", method=request.method, path=request.url.path
            )
        except Exception:
            logging.getLogger("melereview-web").info(
                "request.start method=%s path=%s request_id=%s",
                request.method,
                request.url.path,
                request_id,
            )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        existing = response.headers.get("Access-Control-Expose-Headers", "")
        expose = "X-Request-ID"
        if existing:
            parts = {p.strip() for p in existing.split(",") if p.strip()}
            parts.add(expose)
            response.headers["Access-Control-Expose-Headers"] = ", ".join(sorted(parts))
        else:
            response.headers["Access-Control-Expose-Headers"] = expose
        try:
            import structlog.contextvars as _ctx2  # type: ignore

            _ctx2.unbind_contextvars("request_id")
        except Exception:
            pass
        return response


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID") or uuid.uuid4().hex


def _log(level: str, event: str, request: Request, **kw):
    rid = _request_id(request)
    extra = {"request_id": rid, "path": request.url.path, "method": request.method, **kw}
    if _HAS_STRUCTLOG:
        try:
            logger = structlog.get_logger("melereview-web")
            getattr(logger, level)(event, **extra)
            return rid
        except Exception:
            pass
    logging.getLogger("melereview-web").log(
        getattr(logging, level.upper(), logging.INFO), "%s %s", event, extra
    )
    return rid


def _envelope(code: str, message: str, request_id: str, details=None):
    body = {"error": {"code": code, "message": message, "request_id": request_id}}
    if details is not None:
        body["error"]["details"] = details
    return body


def _is_json_request(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "application/json" in accept and "text/html" not in accept


def _html_or_json(request: Request, code: int, title: str, message: str, rid: str, error_code: str, status_code: int):
    if _is_json_request(request):
        return JSONResponse(_envelope(error_code, message, rid), status_code=status_code, headers={"X-Request-ID": rid})
    return _templates.TemplateResponse(
        request, "error.html", {"code": code, "title": title, "message": message, "request_id": rid}, status_code=status_code, headers={"X-Request-ID": rid}
    )


async def handle_http_exception(request: Request, exc: StarletteHTTPException):
    rid = _request_id(request)
    code = exc.status_code if exc.status_code in _ERROR_TITLES else 500
    title = _ERROR_TITLES.get(code, "Error")
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        429: "TOO_MANY_REQUESTS",
    }
    error_code = code_map.get(code, "HTTP_ERROR")
    msg = str(exc.detail) if code != 404 else "The page you're looking for doesn't exist."
    if code >= 500:
        _log("error", "http_exception", request, status_code=code, error_code=error_code, exc_info=True)
    else:
        _log("warning", "http_error", request, status_code=code, error_code=error_code)
    # HTML for browser, JSON for API clients, both carry X-Request-ID and envelope code
    if _is_json_request(request):
        return JSONResponse(_envelope(error_code, msg, rid), status_code=code, headers={"X-Request-ID": rid})
    return _templates.TemplateResponse(
        request, "error.html", {"code": code, "title": title, "message": msg, "request_id": rid}, status_code=code, headers={"X-Request-ID": rid}
    )


async def handle_validation_error(request: Request, exc: RequestValidationError):
    rid = _request_id(request)
    _log("warning", "validation_error", request, status_code=400, error_code="VALIDATION_ERROR")
    details = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
    if _is_json_request(request):
        return JSONResponse(_envelope("VALIDATION_ERROR", "Validation failed", rid, details=details), status_code=400, headers={"X-Request-ID": rid})
    return _templates.TemplateResponse(
        request,
        "error.html",
        {"code": 400, "title": "Bad Request", "message": "Validation failed", "request_id": rid},
        status_code=400,
        headers={"X-Request-ID": rid},
    )


async def handle_grpc_error(request: Request, exc: grpc.aio.AioRpcError):
    rid = _request_id(request)
    mapping = {
        grpc.StatusCode.NOT_FOUND: (404, "NOT_FOUND"),
        grpc.StatusCode.INVALID_ARGUMENT: (400, "INVALID_ARGUMENT"),
        grpc.StatusCode.ALREADY_EXISTS: (409, "ALREADY_EXISTS"),
        grpc.StatusCode.PERMISSION_DENIED: (403, "PERMISSION_DENIED"),
        grpc.StatusCode.UNAUTHENTICATED: (401, "UNAUTHENTICATED"),
        grpc.StatusCode.UNAVAILABLE: (503, "UPSTREAM_UNAVAILABLE"),
        grpc.StatusCode.DEADLINE_EXCEEDED: (504, "UPSTREAM_TIMEOUT"),
    }
    status, code = mapping.get(exc.code(), (503, "UPSTREAM_UNAVAILABLE"))
    msg = exc.details() or "Upstream unavailable"
    _log("error", "grpc_upstream_failed", request, status_code=status, error_code=code, grpc_code=str(exc.code()))
    if _is_json_request(request):
        return JSONResponse(_envelope(code, msg, rid), status_code=status, headers={"X-Request-ID": rid})
    title = _ERROR_TITLES.get(status, "Error")
    return _templates.TemplateResponse(
        request, "error.html", {"code": status, "title": title, "message": msg, "request_id": rid}, status_code=status, headers={"X-Request-ID": rid}
    )


async def handle_generic_exception(request: Request, exc: Exception):
    rid = _request_id(request)
    _log("error", "unhandled_exception", request, status_code=500, error_code="INTERNAL_ERROR", exc_info=True)
    if _is_json_request(request):
        return JSONResponse(_envelope("INTERNAL_ERROR", "Internal server error", rid), status_code=500, headers={"X-Request-ID": rid})
    return _templates.TemplateResponse(
        request,
        "error.html",
        {"code": 500, "title": "Internal Server Error", "message": "Something went wrong.", "request_id": rid},
        status_code=500,
        headers={"X-Request-ID": rid},
    )


def install_error_handlers(app):
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(grpc.aio.AioRpcError, handle_grpc_error)
    app.add_exception_handler(Exception, handle_generic_exception)
