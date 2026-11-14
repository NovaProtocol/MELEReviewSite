"""Cache-Control policy.

Caching is a production behaviour: under ``DEPLOYMENT_TYPE=debug`` nothing this
service hands out may be stored. In production a response that already carries a
``Cache-Control`` header keeps it, and only a response with none is given the
lifespan its path class implies.

Every page in this app is per-visitor, so HTML is ``private, no-store``. Static
assets keep their day-long public lifespan; uploads are per-visitor and are
proxied through the app, so they take the HTML branch.
"""

from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_STATIC_MAX_AGE = 86400
_MISC_MAX_AGE = 3600

_NO_STORE = "no-store"
_PRIVATE_NO_STORE = "private, no-store"

_VISITOR_SCOPED = ("private", "no-store")

_STATIC_PREFIX = "/static/"
_API_PREFIXES = ("/api/", "/media/")
_MISC_PATHS = frozenset({"/health"})


def _public_max_age(seconds: int) -> str:
    return f"public, max-age={seconds}"


def _cache_control_for(path: str) -> str:
    if path.startswith(_STATIC_PREFIX):
        return _public_max_age(_STATIC_MAX_AGE)
    if path.startswith(_API_PREFIXES):
        return _PRIVATE_NO_STORE
    if path in _MISC_PATHS:
        return _public_max_age(_MISC_MAX_AGE)
    return _PRIVATE_NO_STORE


def is_debug_deployment() -> bool:
    return os.environ.get("DEPLOYMENT_TYPE", "").lower() in ("debug", "true", "1", "yes")


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Set Cache-Control per deployment type, without overriding a route's own."""

    def __init__(self, app, is_debug: bool) -> None:
        super().__init__(app)
        self.is_debug = is_debug

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if self.is_debug:
            value = response.headers.get("Cache-Control")
            if not value or not any(d in value for d in _VISITOR_SCOPED):
                response.headers["Cache-Control"] = _NO_STORE
            return response
        if "Cache-Control" in response.headers:
            return response
        response.headers["Cache-Control"] = _cache_control_for(request.url.path)
        return response
