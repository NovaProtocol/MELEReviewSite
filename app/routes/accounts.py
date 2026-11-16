"""Account editing.

A member edits their own account; the system administrator edits anyone's. The
target is named in the path so the two cases share one implementation instead of
a self route with an admin-only copy beside it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app import media as media_module
from app.auth import check_csrf, require_user
from app.config import get_config
from app.db import get_db
from app.media import save as save_upload
from app.models import User
from app.services import users as user_service

router = APIRouter(prefix="/api/users", tags=["accounts"])


class UsernameBody(BaseModel):
    username: str = Field(min_length=3, max_length=32)


class EmailBody(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class PasswordBody(BaseModel):
    # Only a member editing themselves has to prove they know the old password.
    # An administrator resetting someone else's cannot, so it is left blank.
    current: str = Field(default="", max_length=200)
    new: str = Field(min_length=8, max_length=200)


class PrivacyBody(BaseModel):
    progress_private: bool


class BioBody(BaseModel):
    bio: str = Field(default="", max_length=500)


async def editable(
    uid: str,
    actor: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """The account named in the path, if the caller may change it."""
    target = await user_service.get_by_login(db, uid)
    if target is None:
        raise HTTPException(status_code=404, detail="No such member")
    if target.id != actor.id and not actor.is_system_admin:
        raise HTTPException(status_code=403, detail="Not your account")
    return target


@router.put("/{uid}/username")
async def change_username(
    request: Request,
    body: UsernameBody,
    target: User = Depends(editable),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    updated = await user_service.set_username(db, target, body.username)
    return {"uid": updated.uid, "username": updated.username}


@router.put("/{uid}/email")
async def change_email(
    request: Request,
    body: EmailBody,
    target: User = Depends(editable),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    updated = await user_service.set_email(db, target, body.email)
    return {"uid": updated.uid, "email": updated.email}


@router.put("/{uid}/bio")
async def change_bio(
    request: Request,
    body: BioBody,
    target: User = Depends(editable),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    updated = await user_service.set_bio(db, target, body.bio)
    return {"uid": updated.uid, "bio": updated.bio}


@router.put("/{uid}/privacy")
async def change_privacy(
    request: Request,
    body: PrivacyBody,
    target: User = Depends(editable),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    target.progress_private = body.progress_private
    await db.commit()
    return {"progress_private": target.progress_private}


@router.put("/{uid}/password")
async def change_password(
    request: Request,
    body: PasswordBody,
    actor: User = Depends(require_user),
    target: User = Depends(editable),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    current = body.current if target.id == actor.id else None
    await user_service.set_password(db, target, current, body.new)
    return {"ok": True}


@router.post("/{uid}/avatar")
async def upload_avatar(
    request: Request,
    file: UploadFile,
    target: User = Depends(editable),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    config = get_config()
    relative = await save_upload(file, config.upload_dir, "avatars", config.MAX_UPLOAD_BYTES)
    media_module.remove(config.upload_dir, target.avatar_path)
    target.avatar_path = relative
    await db.commit()
    return {"avatar_url": f"/media/{relative}"}
