from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app import permissions
from app.auth import (
    check_csrf,
    clear_session_cookie,
    current_user,
    set_session_cookie,
)
from app.db import get_db
from app.limiter import limiter
from app.models import User
from app.security import create_session_token
from app.services import invites as invite_service
from app.services import library as library_service
from app.services import users as user_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    identifier: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class RegisterBody(BaseModel):
    invite_code: str = Field(min_length=8, max_length=64)
    username: str = Field(min_length=3, max_length=32)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=200)


def _public(user: User, extra: dict | None = None) -> dict:
    payload = {
        "id": user.id,
        "uid": user.uid,
        "username": user.username,
        "email": user.email,
        "bio": user.bio,
        "avatar_url": f"/media/{user.avatar_path}" if user.avatar_path else None,
        "permissions": user.permissions,
        "permission_labels": permissions.describe(user.permissions),
        "is_system_admin": user.is_system_admin,
        "status": user.status,
        "invited_by": user.invited_by_user_id,
        "date_created": user.date_created,
    }
    if extra:
        payload.update(extra)
    return payload


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginBody,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    user = await user_service.authenticate(db, body.identifier, body.password)
    user.date_last_login = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    await db.commit()
    set_session_cookie(response, create_session_token(user.id))
    return _public(user)


@router.post("/logout")
async def logout(request: Request, response: Response):
    check_csrf(request)
    clear_session_cookie(response)
    return {"ok": True}


@router.post("/register", status_code=201)
@limiter.limit("5/minute")
async def register(
    request: Request,
    body: RegisterBody,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    user = await invite_service.register(
        db, body.invite_code, body.username, body.email, body.password
    )
    set_session_cookie(response, create_session_token(user.id))
    return _public(user)


@router.get("/me")
async def me(user: User | None = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")

    # The profile draws the breakdown, so it belongs in the payload the client
    # already asks for rather than a second round trip.
    from app.services import metrics as metrics_service

    progress = await library_service.progress_for(db, user)
    mastery = await metrics_service.topic_mastery(db, user.id)
    progress["by_subject"] = mastery["subjects"]
    return _public(user, {"progress": progress})
