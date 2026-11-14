from __future__ import annotations

import logging
import uuid

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger("melereview")

ERROR_TITLES = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    413: "Too Large",
    429: "Too Many Requests",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
}

ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    413: "TOO_LARGE",
    429: "TOO_MANY_REQUESTS",
    500: "INTERNAL_ERROR",
}


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach X-Request-ID to every response; propagate an inbound value or make one."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


def _wants_json(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    path = request.url.path
    return path.startswith("/api/") or ("application/json" in accept and "text/html" not in accept)


def _error_page(request: Request, status: int, title: str, message: str, headers: dict) -> Response:
    """Render the error template with the context every page needs.

    The handlers run outside the route that would normally attach the viewer and
    the CSRF token, and the base template reads both, so they are supplied here
    rather than left undefined.
    """
    from app.auth import CSRF_COOKIE
    from app.security import new_csrf_token
    from app.templating import render

    token = request.cookies.get(CSRF_COOKIE) or new_csrf_token()
    return render(
        request,
        "error.html",
        {
            "viewer": None,
            "csrf_token": token,
            "code": status,
            "title": title,
            "message": message,
        },
        status_code=status,
        headers=headers,
    )


def _envelope(code: str, message: str, request_id: str, details=None) -> dict:
    body: dict = {"error": {"code": code, "message": message, "request_id": request_id}}
    if details is not None:
        body["error"]["details"] = details
    return body


async def handle_http_exception(request: Request, exc: StarletteHTTPException):
    request_id = _request_id(request)
    status = exc.status_code
    title = ERROR_TITLES.get(status, "Error")
    code = ERROR_CODES.get(status, "HTTP_ERROR")
    message = (
        "The page you are looking for does not exist."
        if status == 404
        else str(exc.detail or title)
    )
    if status >= 500:
        logger.error("http_exception status=%s path=%s", status, request.url.path, exc_info=True)
    if _wants_json(request):
        return JSONResponse(
            _envelope(code, message, request_id),
            status_code=status,
            headers={"X-Request-ID": request_id},
        )
    return _error_page(request, status, title, message, {"X-Request-ID": request_id})


async def handle_validation_error(request: Request, exc: RequestValidationError):
    request_id = _request_id(request)
    details = [
        {"loc": [str(part) for part in error.get("loc", ())], "msg": error.get("msg")}
        for error in exc.errors()
    ]
    if _wants_json(request):
        return JSONResponse(
            _envelope("VALIDATION_ERROR", "Check the form and try again", request_id, details),
            status_code=422,
            headers={"X-Request-ID": request_id},
        )
    first = details[0]["msg"] if details else "Check the form and try again"
    return _error_page(request, 422, "Check the form", first, {"X-Request-ID": request_id})


async def handle_generic_exception(request: Request, exc: Exception):
    request_id = _request_id(request)
    logger.error("unhandled_exception path=%s", request.url.path, exc_info=True)
    if _wants_json(request):
        return JSONResponse(
            _envelope("INTERNAL_ERROR", "Something went wrong", request_id),
            status_code=500,
            headers={"X-Request-ID": request_id},
        )
    return _error_page(
        request, 500, "Internal Server Error", "Something went wrong.", {"X-Request-ID": request_id}
    )


def install_error_handlers(app) -> None:
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_generic_exception)
