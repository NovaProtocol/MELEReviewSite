from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import permissions
from app.auth import check_csrf, require_admin, require_user
from app.db import get_db
from app.models import Question, Solution, User
from app.services import invites as invite_service
from app.services import library as library_service
from app.services import users as user_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


class PermissionsBody(BaseModel):
    permissions: int = Field(ge=0)

    def clamped(self) -> int:
        return self.permissions & permissions.ALL


class SubjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TopicBody(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    subject_id: int


class TopicActiveBody(BaseModel):
    is_active: bool


class RestoreBody(BaseModel):
    kind: str = Field(pattern="^(question|solution)$")


def _user_row(user: User) -> dict:
    return {
        "id": user.id,
        "uid": user.uid,
        "username": user.username,
        "email": user.email,
        "permissions": user.permissions,
        "permission_labels": permissions.describe(user.permissions),
        "is_system_admin": user.is_system_admin,
        "status": user.status,
        "status_reason": user.status_reason,
        "status_root_user_id": user.status_root_user_id,
        "invited_by_user_id": user.invited_by_user_id,
        "date_created": user.date_created,
        "date_last_login": user.date_last_login,
    }


@router.get("/users")
async def list_users(
    search: str = "",
    status: str = "",
    page: int = 1,
    per_page: int = 50,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    users, total = await user_service.list_users(db, search, status, page, per_page)
    return {
        "items": [_user_row(u) for u in users],
        "total": total,
        "counts": await user_service.counts_by_status(db),
    }


@router.get("/users/{user_id}/chain")
async def user_chain(
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await user_service.get_user(db, user_id)
    chain = await invite_service.descendants(db, user_id)
    rows = []
    if chain:
        result = await db.execute(select(User).where(User.id.in_(chain)).order_by(User.id))
        for member in result.scalars().all():
            rows.append(
                {
                    "id": member.id,
                    "username": member.username,
                    "status": member.status,
                    "invited_by_user_id": member.invited_by_user_id,
                }
            )
    inviter = await db.get(User, target.invited_by_user_id) if target.invited_by_user_id else None
    return {
        "user": _user_row(target),
        "invited_by": inviter.username if inviter else None,
        "descendants": rows,
    }


@router.put("/users/{user_id}/permissions")
async def set_permissions(
    user_id: int,
    request: Request,
    body: PermissionsBody,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    target = await user_service.get_user(db, user_id)
    if target.is_system_admin and target.id != admin.id:
        raise HTTPException(status_code=400, detail="The system administrator's grants are fixed")
    updated = await user_service.set_permissions(db, target, body.clamped())
    return _user_row(updated)


@router.get("/users/{user_id}/ban-preview")
async def ban_preview(
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await invite_service.ban_preview(db, user_id)


@router.post("/users/{user_id}/ban")
async def ban_user(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    return await invite_service.ban(db, user_id, admin)


@router.post("/users/{user_id}/revoke-subtree")
async def revoke_subtree(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    return await invite_service.revoke_subtree(db, user_id, admin)


@router.post("/users/{user_id}/reactivate")
async def reactivate(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    return await invite_service.reactivate(db, user_id)


@router.get("/invites")
async def list_all_invites(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await invite_service.list_invites(db, admin, all_users=True)


@router.delete("/invites/{invite_id}", status_code=204)
async def revoke_invite(
    invite_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    await invite_service.revoke_invite(db, invite_id, admin)


@router.get("/content")
async def hidden_content(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await library_service.hidden_content(db)


@router.post("/content/{kind}/{content_id}/restore")
async def restore_content(
    kind: str,
    content_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    if kind == "question":
        question = await db.get(Question, content_id)
        if question is None:
            raise HTTPException(status_code=404, detail="Question not found")
        question.is_hidden = False
        question.hidden_by_user_id = None
        question.hidden_at = None
        await db.commit()
        return {"restored": content_id, "kind": kind}
    if kind == "solution":
        solution = await db.get(Solution, content_id)
        if solution is None:
            raise HTTPException(status_code=404, detail="Solution not found")
        solution.is_hidden = False
        solution.hidden_by_user_id = None
        solution.hidden_at = None
        await db.commit()
        return {"restored": content_id, "kind": kind}
    raise HTTPException(status_code=400, detail="Unknown content kind")


@router.post("/subjects", status_code=201)
async def create_subject(
    request: Request,
    body: SubjectBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    permissions.require(user.permissions, permissions.MANAGE_TAXONOMY)
    subject = await library_service.create_subject(db, body.name)
    return {"id": subject.id, "name": subject.name}


@router.put("/subjects/{subject_id}")
async def rename_subject(
    subject_id: int,
    request: Request,
    body: SubjectBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    permissions.require(user.permissions, permissions.MANAGE_TAXONOMY)
    subject = await library_service.rename_subject(db, subject_id, body.name)
    return {"id": subject.id, "name": subject.name}


@router.post("/topics", status_code=201)
async def create_topic(
    request: Request,
    body: TopicBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    permissions.require(user.permissions, permissions.MANAGE_TAXONOMY)
    topic = await library_service.create_topic(db, body.subject_id, body.name)
    return {"id": topic.id, "name": topic.name, "subject_id": topic.subject_id}


@router.put("/topics/{topic_id}")
async def set_topic_active(
    topic_id: int,
    request: Request,
    body: TopicActiveBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    permissions.require(user.permissions, permissions.MANAGE_TAXONOMY)
    topic = await library_service.set_topic_active(db, topic_id, body.is_active)
    return {"id": topic.id, "is_active": topic.is_active}


@router.get("/overview")
async def overview(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func

    from app.models import Question as Q
    from app.models import Solution as S
    from app.models import Subject as Sub
    from app.models import Topic as T

    return {
        "users": await user_service.counts_by_status(db),
        "questions": int((await db.execute(select(func.count()).select_from(Q))).scalar_one()),
        "solutions": int((await db.execute(select(func.count()).select_from(S))).scalar_one()),
        "subjects": int((await db.execute(select(func.count()).select_from(Sub))).scalar_one()),
        "topics": int((await db.execute(select(func.count()).select_from(T))).scalar_one()),
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
    }
