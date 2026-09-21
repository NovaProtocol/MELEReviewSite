"""Cache-Control policy for the documentation service.

Kept local because this image does not carry the shared package. The policy is
the same as the application services so a docs page and an app page agree.
"""

from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Production cache lifespans, in seconds. Tuning one is a one-line edit here
# plus a redeploy; they are deliberately not env vars.
_STATIC_MAX_AGE = 86400
_HTML_MAX_AGE = 300
_MISC_MAX_AGE = 3600

# Debug value: forbids any cache from storing the response at all.
_NO_STORE = "no-store"

# Directives that already forbid a shared cache from storing the response.
# Debug keeps such a value rather than rewriting it.
_VISITOR_SCOPED = ("private", "no-store")

_STATIC_PREFIX = "/static/"
_API_PREFIXES = ("/api/",)
_MISC_PATHS = frozenset({"/health", "/api/health"})


def _public_max_age(seconds: int) -> str:
    return f"public, max-age={seconds}"


def _cache_control_for(path: str) -> str:
    if path.startswith(_STATIC_PREFIX):
        return _public_max_age(_STATIC_MAX_AGE)
    if path.startswith(_API_PREFIXES):
        # Per-visitor and often gated. Never let a shared cache hold it.
        return "private, no-store"
    if path in _MISC_PATHS:
        return _public_max_age(_MISC_MAX_AGE)
    return f"private, max-age={_HTML_MAX_AGE}"


def is_debug_deployment() -> bool:
    return os.environ.get("DEPLOYMENT_TYPE", "").lower() in ("debug", "true", "1", "yes")


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Set Cache-Control per deployment type, without overriding a route's own.

    Caching is a production behaviour. With ``is_debug`` set, anything
    shared-cacheable is replaced with ``no-store``, so a deliberately ``public``
    value never survives into a development deployment; a value that already
    forbids storage is kept verbatim. In production a response that already
    carries a ``Cache-Control`` header keeps it, and only a response with none
    is given the path class's lifespan.

    The invariant that makes keeping a header safe:

        A response may be ``public``-cacheable only when the path is ungated
        (the gate resolved ``action == "none"``) **and** the upstream chose
        that header itself.

    This service is not the gate, so it cannot know whether a path was gated and
    it does not demote. On a stack behind GateKeeper the gateway applies that
    demotion before the response reaches a shared cache.
    """

    def __init__(self, app, is_debug: bool) -> None:
        super().__init__(app)
        self.is_debug = is_debug

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if self.is_debug:
            # `DEPLOYMENT_TYPE=debug` disables caching outright: nothing this
            # service hands out may be stored, whatever the upstream asked for.
            # Every lifespan below is a production behaviour. A value that
            # already forbids storage is kept verbatim so the gate's own
            # `private, no-store` survives; anything else, including a
            # deliberately `public` one, is replaced.
            value = response.headers.get("Cache-Control")
            if not value or not any(d in value for d in _VISITOR_SCOPED):
                response.headers["Cache-Control"] = _NO_STORE
            return response
        if "Cache-Control" in response.headers:
            return response
        response.headers["Cache-Control"] = _cache_control_for(request.url.path)
        return response
