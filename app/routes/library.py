from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import media as media_module
from app import permissions
from app.auth import check_csrf, require_user
from app.config import get_config
from app.db import get_db
from app.models import Solution, User
from app.services import library as library_service

router = APIRouter(prefix="/api", tags=["library"])


class QuestionBody(BaseModel):
    topic_id: int
    body: str = Field(min_length=1)
    choice_a: str = Field(min_length=1)
    choice_b: str = Field(min_length=1)
    choice_c: str = Field(min_length=1)
    choice_d: str = Field(min_length=1)
    choice_e: str | None = None
    correct_choice: str = Field(min_length=1, max_length=1)
    explanation: str | None = None
    tags: list[str] = []


class AttemptBody(BaseModel):
    chosen: str = Field(min_length=1, max_length=1)


class VoteBody(BaseModel):
    direction: int = Field(ge=-1, le=1)


class SolutionNoteBody(BaseModel):
    note: str = Field(default="", max_length=500)


@router.get("/subjects")
async def subjects(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await library_service.list_subjects(db)


@router.get("/topics/{topic_id}/questions")
async def questions(
    topic_id: int,
    search: str = "",
    favourites: bool = False,
    show_hidden: bool = False,
    show_downvoted: bool = False,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """List a topic's questions.

    `show_hidden` reveals what this member hid themselves. A moderator's view of
    moderator-hidden questions is a separate switch, so their own eye button keeps
    working instead of being silently overridden by VIEW_HIDDEN.
    """
    moderator = permissions.has(user.permissions, permissions.VIEW_HIDDEN)
    return await library_service.list_questions(
        db,
        topic_id,
        search=search,
        include_moderated_hidden=moderator,
        include_personal_hidden=show_hidden,
        viewer=user,
        favourites_only=favourites,
        show_downvoted=show_downvoted,
    )


@router.post("/questions", status_code=201)
async def create_question(
    request: Request,
    body: QuestionBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    question = await library_service.create_question(db, user, body.model_dump())
    return await library_service.question_view(db, question, user)


@router.get("/questions/{question_id}")
async def get_question(
    question_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    question = await library_service.get_question(db, question_id)
    include_hidden = permissions.has(user.permissions, permissions.VIEW_HIDDEN)
    if question.is_hidden and not include_hidden:
        raise HTTPException(status_code=404, detail="Question not found")
    return await library_service.question_view(db, question, user, include_hidden=include_hidden)


@router.put("/questions/{question_id}")
async def update_question(
    question_id: int,
    request: Request,
    body: QuestionBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    updated = await library_service.update_question(db, question, user, body.model_dump())
    return await library_service.question_view(db, updated, user, include_hidden=True)


@router.post("/questions/{question_id}/attempt")
async def attempt(
    question_id: int,
    request: Request,
    body: AttemptBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    return await library_service.record_attempt(db, question, user, body.chosen)


@router.post("/questions/{question_id}/favourite")
async def favourite(
    question_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    return await library_service.set_favourite(db, question, user)


@router.post("/questions/{question_id}/hide-for-me")
async def hide_for_me(
    question_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Hide the question from this member's own list, not from anyone else's."""
    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    return await library_service.set_personal_hidden(db, question, user)


@router.post("/questions/{question_id}/vote")
async def vote(
    question_id: int,
    request: Request,
    body: VoteBody,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    return await library_service.set_vote(db, question, user, body.direction)


@router.post("/questions/{question_id}/solution")
async def upload_solution(
    question_id: int,
    request: Request,
    file: UploadFile,
    note: str = "",
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    permissions.require(user.permissions, permissions.ANSWER_QUESTION)
    question = await library_service.get_question(db, question_id)
    config = get_config()
    relative = await media_module.save(
        file, config.upload_dir, "solutions", config.MAX_UPLOAD_BYTES
    )
    existing = (
        (
            await db.execute(
                select(Solution).where(
                    Solution.question_id == question.id, Solution.author_user_id == user.id
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is None:
        db.add(
            Solution(
                question_id=question.id,
                author_user_id=user.id,
                image_path=relative,
                note=(note.strip() or None) if note else None,
            )
        )
    else:
        media_module.remove(config.upload_dir, existing.image_path)
        existing.image_path = relative
        existing.note = (note.strip() or None) if note else None
        existing.is_hidden = False
        existing.hidden_by_user_id = None
        existing.hidden_at = None
    await db.commit()
    refreshed = await library_service.get_question(db, question_id)
    return await library_service.question_view(db, refreshed, user)


@router.delete("/questions/{question_id}/solution", status_code=204)
async def delete_solution(
    question_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    solution = (
        (
            await db.execute(
                select(Solution).where(
                    Solution.question_id == question_id, Solution.author_user_id == user.id
                )
            )
        )
        .scalars()
        .first()
    )
    if solution is None:
        raise HTTPException(status_code=404, detail="You have no solution here")
    media_module.remove(get_config().upload_dir, solution.image_path)
    await db.delete(solution)
    await db.commit()
    return None


@router.post("/questions/{question_id}/hide")
async def hide_question(
    question_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    question = await library_service.get_question(db, question_id)
    updated = await library_service.hide_question(db, question, user, True)
    return {"id": updated.id, "is_hidden": updated.is_hidden}


@router.post("/solutions/{solution_id}/hide")
async def hide_solution(
    solution_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    permissions.require(user.permissions, permissions.MODERATE)
    solution = await db.get(Solution, solution_id)
    if solution is None:
        raise HTTPException(status_code=404, detail="Solution not found")
    solution.is_hidden = True
    solution.hidden_by_user_id = user.id
    solution.hidden_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    await db.commit()
    return {"id": solution.id, "is_hidden": solution.is_hidden}


@router.get("/me/progress")
async def progress(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await library_service.progress_for(db, user)
