"""The React shell.

The client is a Vite build inside `app/static/app`. Its asset names are hashed, so
the page is rendered from Vite's manifest rather than from a hand-written script
tag; a page that named a stale bundle would show an empty workspace.

Everything the client needs to draw its chrome arrives as one JSON payload: who is
signed in, which specialist tools exist, and where the library lives. No second
request, and no client copy of the tool list to keep in step with the server's.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app import permissions
from app.db import get_db
from app.models import User
from app.routes.tools import TOOLS
from app.templating import render

router = APIRouter()

STATIC_ROOT = Path(__file__).resolve().parent.parent / "static" / "app"
MANIFEST = STATIC_ROOT / ".vite" / "manifest.json"


@lru_cache(maxsize=1)
def assets() -> dict[str, str]:
    """The entry bundle and its stylesheet, by their built names."""
    try:
        manifest = json.loads(MANIFEST.read_text())
    except OSError, ValueError:
        return {"js": "", "css": ""}
    entry = manifest.get("index.html") or next(
        (item for item in manifest.values() if item.get("isEntry")), {}
    )
    return {"js": entry.get("file", ""), "css": (entry.get("css") or [""])[0]}


async def _viewer(request: Request, db: AsyncSession) -> User | None:
    from app.auth import SESSION_COOKIE
    from app.security import read_session_token

    user_id = read_session_token(request.cookies.get(SESSION_COOKIE))
    if user_id is None:
        return None
    user = await db.get(User, user_id)
    request.state.viewer = user
    return user


# Where the client owns the page. Everything else is still Jinja, and the list
# shrinks as a page moves: a route is React or it is server-rendered, never both.
# Routes the client owns: /app, /library, a topic, and a question inside it.
# Everything else is still server-rendered, and a route is one or the other.


async def _shell(request: Request, db: AsyncSession, active: str) -> RedirectResponse | Response:
    user = await _viewer(request, db)
    if user is None:
        return RedirectResponse("/", status_code=302)
    if user.status != "active":
        # A banned or revoked member is told why, not dropped on the front door.
        return RedirectResponse("/status", status_code=302)

    bundle = assets()
    bootstrap = {
        "viewer": {
            "username": user.username,
            "avatar": f"/media/{user.avatar_path}" if user.avatar_path else None,
            "is_admin": user.is_system_admin,
        },
        "specialists": [
            {"slug": tool["slug"], "name": tool["name"], "group": tool["group"]} for tool in TOOLS
        ],
        "formulas_url": "/api/formulas",
        "library_url": "/library",
        "route": active,
    }
    return render(
        request,
        "app_shell.html",
        {
            "viewer": user,
            "bundle": bundle,
            "bootstrap": bootstrap,
            "can_moderate": permissions.has(user.permissions, permissions.MODERATE),
        },
    )


@router.get("/app")
async def workspace(request: Request, db: AsyncSession = Depends(get_db)):
    return await _shell(request, db, "app")


@router.get("/library")
async def client_library(request: Request, db: AsyncSession = Depends(get_db)):
    return await _shell(request, db, "/library")


@router.get("/library/{topic_id:int}")
async def client_topic(request: Request, topic_id: int, db: AsyncSession = Depends(get_db)):
    return await _shell(request, db, f"/library/{topic_id}")


@router.get("/library/{topic_id:int}/{question_id:int}")
async def client_question(
    request: Request, topic_id: int, question_id: int, db: AsyncSession = Depends(get_db)
):
    return await _shell(request, db, f"/library/{topic_id}/{question_id}")
