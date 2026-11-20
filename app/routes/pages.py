from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import permissions
from app.config import get_config
from app.db import get_db
from app.models import User
from app.services import invites as invite_service
from app.services import users as user_service
from app.templating import render

router = APIRouter()


async def _viewer(request: Request, db: AsyncSession) -> User | None:
    """The signed-in user, or the reason the page should redirect instead."""
    from app.auth import SESSION_COOKIE
    from app.models import User as UserModel
    from app.security import read_session_token

    token = request.cookies.get(SESSION_COOKIE)
    user_id = read_session_token(token)
    if user_id is None:
        return None
    user = await db.get(UserModel, user_id)
    request.state.viewer = user
    return user


def _blocked(user: User | None) -> bool:
    return user is not None and user.status != "active"


@router.get("/users/{username}/edit")
async def user_edit_page(request: Request, username: str, db: AsyncSession = Depends(get_db)):
    """An account's own controls: identity, password, avatar, invitations.

    Reached from the member page by the member, or by the administrator for
    anyone. Nobody else may open it.
    """
    user = await _viewer(request, db)
    if user is None:
        return RedirectResponse("/", status_code=302)
    if user.status != "active":
        return RedirectResponse("/status", status_code=302)
    target = await user_service.get_by_login(db, username)
    if target is None:
        raise HTTPException(status_code=404, detail="No such member")
    if target.id != user.id and not user.is_system_admin:
        raise HTTPException(status_code=403, detail="Not your account")
    return render(
        request,
        "user_edit.html",
        {
            "viewer": user,
            "member": target,
            "is_self": target.id == user.id,
            "invites": await invite_service.list_invites(db, target)
            if permissions.has(target.permissions, permissions.INVITE)
            else [],
            "invite_limit": get_config().MAX_OPEN_INVITES,
        },
    )


@router.get("/topics/{rest:path}")
async def old_topic_path(rest: str):
    """The old /topics/... addresses, moved under /library."""
    return RedirectResponse(f"/library/{rest}", status_code=301)


@router.get("/profile")
async def profile_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Moved: the profile is the member's own page now.

    Kept as a redirect so an old bookmark, or a link in a chat, still lands.
    """
    user = await _viewer(request, db)
    if user is None:
        return RedirectResponse("/", status_code=302)
    if user.status != "active":
        return RedirectResponse("/status", status_code=302)
    return RedirectResponse(f"/users/{user.uid}", status_code=302)


