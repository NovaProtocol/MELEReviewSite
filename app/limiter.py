from __future__ import annotations

from slowapi import Limiter
from starlette.requests import Request


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return str(forwarded).split(",")[0].strip()
    if request.client:
        return str(request.client.host)
    return "unknown"


limiter = Limiter(key_func=_client_ip)
