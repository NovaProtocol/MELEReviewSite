"""Who is making the request, and what they may do.

The session cookie names a user id only; the row is read on every request, which
is how a ban takes effect immediately. A user whose status is not ``active`` gets
no session at all, so every page route can treat "logged in" as "allowed in".
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app import permissions
from app.config import get_config
from app.db import get_db
from app.models import User
from app.security import read_session_token, tokens_match

SESSION_COOKIE = "melereview_session"
CSRF_COOKIE = "melereview_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    user_id = read_session_token(token)
    if user_id is None:
        return None
    user = await db.get(User, user_id)
    if user is None or user.status != "active":
        return None
    return user


async def require_user(user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    return user


async def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_system_admin:
        raise HTTPException(status_code=403, detail="System administrator only")
    return user


def require_permission(bit: int):
    async def _dependency(user: User = Depends(require_user)) -> User:
        permissions.require(user.permissions, bit)
        return user

    return _dependency


def check_csrf(request: Request) -> None:
    """Double-submit check for every mutating request.

    The token is not tied to the session, so the login form itself is covered,
    which is where a login-CSRF would matter most.
    """
    if request.method in SAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not tokens_match(cookie, header):
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token")


def ensure_csrf_cookie(request: Request, response: Response) -> str:
    existing = request.cookies.get(CSRF_COOKIE)
    if existing:
        return str(existing)
    from app.security import new_csrf_token

    token = new_csrf_token()
    response.set_cookie(
        CSRF_COOKIE,
        token,
        httponly=False,
        samesite="lax",
        secure=get_config().secure_cookies,
        max_age=30 * 24 * 3600,
        path="/",
    )
    return token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=get_config().secure_cookies,
        max_age=30 * 24 * 3600,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
