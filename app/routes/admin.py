from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import permissions
from app.auth import check_csrf, require_admin, require_user
from app.db import get_db
from app.models import Question, QuestionReport, Solution, User
from app.services import invites as invite_service
from app.services import library as library_service
from app.services import metrics, taxonomy
from app.services import reports as report_service
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
        "open_reports": await report_service.open_count(db),
        "questions": int((await db.execute(select(func.count()).select_from(Q))).scalar_one()),
        "solutions": int((await db.execute(select(func.count()).select_from(S))).scalar_one()),
        "subjects": int((await db.execute(select(func.count()).select_from(Sub))).scalar_one()),
        "topics": int((await db.execute(select(func.count()).select_from(T))).scalar_one()),
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
    }


@router.get("/questions")
async def admin_questions(
    q: str = "",
    subject: int | None = None,
    topic: int | None = None,
    tags: str = "",
    filter: str = "all",
    sort: str = "newest",
    limit: int = 200,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Every question, including hidden and deleted, with live filters.

    `filter` is one of: all, negative, hidden, deleted, unsolved, active.
    `sort` is one of: newest, attempts, tries, solve_rate, score.
    """
    selected = [part.strip() for part in tags.split(",") if part.strip()]
    questions = await taxonomy.search_questions(
        db,
        term=q,
        tags=selected,
        subject_id=subject,
        topic_id=topic,
        include_hidden=filter in {"all", "hidden", "deleted", "negative", "unsolved"},
        include_deleted=filter in {"all", "hidden", "deleted", "negative", "unsolved"},
        only_deleted=filter == "deleted",
        only_negative=filter == "negative",
        limit=limit,
    )
    if filter == "hidden":
        questions = [question for question in questions if question.is_hidden]
    elif filter == "active":
        questions = [
            question for question in questions if not question.is_hidden and not question.is_deleted
        ]

    from app.routes.search import results_for

    results = await results_for(db, questions, with_stats=True)
    if filter == "unsolved":
        results = [item for item in results if not item.get("solved")]

    # "Lowest solve rate" and "lowest score" are ascending: the point of both is
    # to put the problems at the top, which is what an administrator is hunting.
    ascending = {
        "solve_rate": lambda item: item.get("solve_rate", 0.0),
        "score": lambda item: item.get("score", 0),
    }
    descending = {
        "attempts": lambda item: item.get("attempters", 0),
        "tries": lambda item: item.get("average_attempts", 0.0),
    }
    if sort in ascending:
        results.sort(key=ascending[sort])
    elif sort in descending:
        results.sort(key=descending[sort], reverse=True)
    return {"items": results, "total": len(results), "count": len(results)}


@router.post("/questions/{question_id}/delete")
async def delete_question_soft(
    question_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a question from the metrics and the site, keeping the row.

    Deleted is not hidden: hidden stays part of the record and still counts, a
    delete removes it from everybody's numbers. The row survives so it can be
    restored and so the audit trail stays intact.
    """
    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    question.is_deleted = True
    question.deleted_by_user_id = admin.id
    question.deleted_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    await db.flush()
    await metrics.refresh_all_for_question(db, question_id)
    await db.commit()
    return {"deleted": question_id}


@router.post("/questions/{question_id}/restore")
async def restore_question(
    question_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    question.is_deleted = False
    question.deleted_by_user_id = None
    question.deleted_at = None
    await db.flush()
    await metrics.refresh_all_for_question(db, question_id)
    await db.commit()
    return {"restored": question_id}


@router.get("/reports")
async def reports(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return {"reports": await report_service.open_reports(db)}


@router.post("/reports/{report_id}/{action}")
async def settle_report(
    report_id: int,
    action: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    row = await db.get(QuestionReport, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No such report")
    return await report_service.resolve(db, row, admin, action)
