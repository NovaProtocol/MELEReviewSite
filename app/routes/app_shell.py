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
from app.auth import require_user
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
# Every route the client owns. The server hands over the shell and the client
# reads the API; a path is either this or a redirect, never a second renderer.


async def _shell(
    request: Request, db: AsyncSession, active: str, *, allow_guest: bool = False
) -> RedirectResponse | Response:
    user = await _viewer(request, db)
    if user is None:
        # The landing page is the one client route a guest may see; everything else
        # is behind a session.
        if allow_guest:
            return _render_shell(request, None, active)
        return RedirectResponse("/", status_code=302)
    if user.status != "active":
        # A banned or revoked member is told why, not dropped on the front door.
        return RedirectResponse("/status", status_code=302)

    if active.startswith("/admin") and not user.is_system_admin:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Administrator only")

    return _render_shell(request, user, active)


def _render_shell(request: Request, user: User | None, active: str) -> Response:
    bundle = assets()
    bootstrap = {
        "viewer": {
            "username": user.username if user else "",
            "avatar": f"/media/{user.avatar_path}" if user and user.avatar_path else None,
            "is_admin": bool(user and user.is_system_admin),
            "signed_in": user is not None,
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
            "can_moderate": bool(user and permissions.has(user.permissions, permissions.MODERATE)),
        },
    )


# One table, one registration: every path the client owns. A path is either this
# or a redirect, never a second renderer, which is what keeps the chrome and the
# theme from diverging again.
CLIENT_ROUTES: tuple[tuple[str, str], ...] = (
    ("/app", "workspace"),
    ("/resource/{topic_id:int}", "resource"),
    ("/problem-sets", "problem_set_index"),
    ("/problem-sets/{topic_id:int}", "problem_set"),
    ("/problem-sets/{topic_id:int}/{question_id:int}", "problem"),
    ("/tags", "tags"),
    ("/tags/{name}", "tag"),
    ("/quiz", "quiz"),
    ("/quiz/new", "quiz_new"),
    ("/quiz/{uid}", "quiz_run"),
    ("/admin", "admin"),
    ("/search", "search"),
    ("/me", "me"),
    ("/users/{username}", "member"),
)


def _client(route: str):
    async def handler(request: Request, db: AsyncSession = Depends(get_db)):
        return await _shell(request, db, request.url.path)

    handler.__name__ = f"client_{route}"
    return handler


for _path, _name in CLIENT_ROUTES:
    router.add_api_route(_path, _client(_name), methods=["GET"], include_in_schema=False)


# Old addresses keep working: a link somebody saved, or a bookmark in a browser,
# is not a reason to show them a 404.
@router.get("/library", include_in_schema=False)
async def library_moved():
    # Library is the resources index, which is the workspace's Library view.
    return RedirectResponse("/app", status_code=302)


@router.get("/library/{topic_id:int}", include_in_schema=False)
async def topic_moved(topic_id: int):
    return RedirectResponse("/app", status_code=302)


@router.get("/library/{topic_id:int}/{question_id:int}", include_in_schema=False)
async def question_moved(topic_id: int, question_id: int):
    return RedirectResponse("/app", status_code=302)


@router.get("/", include_in_schema=False)
async def front_door(request: Request, db: AsyncSession = Depends(get_db)):
    """The landing page for a guest, the explorer for a member.

    A member following an old link should not be asked to sign in again, which is
    what made /library feel broken.
    """
    user = await _viewer(request, db)
    if user is not None and user.status == "active":
        return RedirectResponse("/app", status_code=302)
    if user is not None:
        return RedirectResponse("/status", status_code=302)
    return await _shell(request, db, "/", allow_guest=True)


@router.get("/editor/partial", include_in_schema=False)
async def editor_partial(request: Request, user: User = Depends(require_user)):
    """The editor's markup, for a client that mounts it rather than renders it.

    The editor is a proven piece of this app: two modes over one value, media upload
    that writes its own /media/<uid> reference, formulas, and the rule that a
    cancelled edit discards what it uploaded. Rebuilding it in the client is how
    those features were lost once already, so the client mounts the real one and the
    markup stays in one place.
    """
    from app.templating import templates

    return templates.TemplateResponse(request, "_editor_fragment.html", {"viewer": user})
