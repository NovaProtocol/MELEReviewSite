from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import check_csrf, require_user
from app.db import get_db
from app.models import User
from app.services import invites as invite_service

router = APIRouter(prefix="/api/invites", tags=["invites"])


@router.get("")
async def list_own(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await invite_service.list_invites(db, user)


@router.post("", status_code=201)
async def create(
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    invite = await invite_service.create_invite(db, user)
    return {
        "id": invite.id,
        "code": invite.code,
        "state": "open",
        "date_created": invite.date_created,
    }
