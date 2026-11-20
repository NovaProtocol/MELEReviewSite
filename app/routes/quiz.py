"""The quiz section: a list, a builder, and one saved paper.

Three pages and one API. A quiz is a row now, so the addresses are stable and the
share link is short.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app import markdown
from app.auth import check_csrf, require_admin, require_user
from app.db import get_db
from app.models import User
from app.services import library as library_service
from app.services import quiz as builder
from app.services import quizzes as saved

router = APIRouter(tags=["quiz"])


class QuizFilters(BaseModel):
    exclude_topics: list[int] = []
    kind: str = ""
    exclude_computation: bool = False
    unanswered_only: bool = False
    favourites_only: bool = False


class CreateQuizRequest(BaseModel):
    selections: dict[int, int] = Field(default_factory=dict)
    timer_minutes: int = Field(default=30, ge=0, le=600)
    group: str = Field(default="mixed", pattern="^(mixed|topic|subject)$")
    title: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=2000)
    is_private: bool = False
    scores_public: bool = True
    filters: QuizFilters = QuizFilters()


class SittingRequest(BaseModel):
    practice: bool = False


class AnswersRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    practice: bool = False


class RandomRequest(BaseModel):
    exclude_topics: list[int] = []
    kind: str = ""
    exclude_computation: bool = False
    unanswered_only: bool = False
    favourites_only: bool = False
    subject_id: int | None = None


def _settings(quiz) -> dict:
    try:
        return json.loads(quiz.settings or "{}")
    except ValueError:
        return {}


def _answers(raw: str | None) -> dict[str, str]:
    try:
        parsed = json.loads(raw or "{}")
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in parsed.items()} if isinstance(parsed, dict) else {}


async def _quiz_for(db: AsyncSession, uid: str, viewer: User):
    return await saved.get(db, uid)


@router.post("/api/quizzes", status_code=201)
async def create_quiz(
    request: Request,
    body: CreateQuizRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    check_csrf(request)
    settings = {
        "timer_minutes": body.timer_minutes,
        "group": body.group,
        "filters": body.filters.model_dump(),
    }
    settings, ids = await builder.build(db, body.selections, settings, user)
    quiz = await saved.create(
        db,
        user,
        title=body.title,
        description=body.description,
        settings=settings,
        question_ids=ids,
        is_private=body.is_private,
        scores_public=body.scores_public,
    )
    return {"uid": quiz.uid}


@router.get("/api/quizzes")
async def list_quizzes(
    scope: str = "all", user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> dict:
    return {"quizzes": await saved.listing(db, user, scope)}


@router.get("/api/quizzes/{uid}")
async def quiz_payload(
    uid: str, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> dict:
    quiz = await _quiz_for(db, uid, user)
    await saved.touch(db, quiz)
    questions = await saved.questions(db, quiz)
    lock = await saved.lock_reason(db, quiz)
    first = await saved.first_take(db, quiz, user)
    may_manage = quiz.owner_user_id == user.id or user.is_system_admin

    views = []
    for question in questions:
        view = await library_service.question_view(db, question, user, with_solutions=False)
        views.append(
            {
                "id": view["id"],
                "topic_id": view["topic_id"],
                "body": view["body"],
                "body_html": view["body_html"],
                "choices": view["choices"],
                "kind": view["kind"],
                # A one-line preview for the review list, without the markup.
                "preview": markdown.to_plain(question.body, 140),
                "deleted": question.is_deleted,
            }
        )

    owner = await db.get(User, quiz.owner_user_id)
    return {
        "uid": quiz.uid,
        "title": quiz.title,
        "description": quiz.description,
        "description_html": markdown.render(quiz.description),
        "is_private": quiz.is_private,
        "scores_public": quiz.scores_public,
        "settings": _settings(quiz),
        "created": quiz.date_created,
        "activity": quiz.last_activity,
        "owner": owner.username if owner else "unknown",
        "owner_uid": owner.uid if owner else "",
        "is_owner": quiz.owner_user_id == user.id,
        "may_manage": may_manage,
        "locked": lock,
        "questions": views,
        "my_first": (
            {
                "score": first.score,
                "correct": first.correct,
                "total": first.total,
                "duration_seconds": first.duration_seconds,
                "submitted": first.submitted_at is not None,
                "answers": _answers(first.answers),
                "started_at": first.started_at,
                "last_seen": first.last_seen,
            }
            if first
            else None
        ),
        "leaderboard": (
            await saved.leaderboard(db, quiz) if quiz.scores_public or may_manage else []
        ),
        "submissions": await saved.submissions_for(db, quiz) if may_manage else [],
    }


@router.post("/api/quizzes/{uid}/start")
async def start_quiz(
    uid: str,
    request: Request,
    body: SittingRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    check_csrf(request)
    quiz = await _quiz_for(db, uid, user)
    lock = await saved.lock_reason(db, quiz)
    if lock:
        raise HTTPException(status_code=409, detail=lock)
    first = await saved.first_take(db, quiz, user)
    if first is not None and first.submitted_at is not None and not body.practice:
        raise HTTPException(status_code=409, detail="You have already taken this quiz")
    sitting = await saved.open_sitting(db, quiz, user, practice=body.practice)
    return {
        "submission_id": sitting.id,
        "is_first_take": sitting.is_first_take,
        "answers": _answers(sitting.answers),
        "started_at": sitting.started_at,
    }


@router.post("/api/quizzes/{uid}/progress")
async def save_progress(
    uid: str,
    request: Request,
    body: AnswersRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Every answer is stored as it is picked, so a closed tab still scores."""
    check_csrf(request)
    quiz = await _quiz_for(db, uid, user)
    sitting = await saved.first_take(db, quiz, user)
    if sitting is None or sitting.submitted_at is not None:
        raise HTTPException(status_code=409, detail="No sitting in progress")
    await saved.save_progress(db, sitting, body.answers)
    return {"saved": len(body.answers)}


@router.post("/api/quizzes/{uid}/submit")
async def submit_quiz(
    uid: str,
    request: Request,
    body: AnswersRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    check_csrf(request)
    quiz = await _quiz_for(db, uid, user)
    questions = await saved.questions(db, quiz)
    sitting = await saved.first_take(db, quiz, user)

    if body.practice:
        sitting = await saved.open_sitting(db, quiz, user, practice=True)
    elif sitting is None:
        raise HTTPException(status_code=409, detail="Start the quiz first")
    elif sitting.submitted_at is not None:
        raise HTTPException(status_code=409, detail="You have already taken this quiz")

    result = await saved.submit(db, quiz, sitting, body.answers, questions)
    result["leaderboard"] = await saved.leaderboard(db, quiz) if quiz.scores_public else []
    return result


@router.delete("/api/quizzes/{uid}", status_code=204)
async def delete_quiz(
    uid: str,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    check_csrf(request)
    quiz = await saved.get(db, uid)
    await saved.remove(db, quiz, user)
    return None


@router.post("/api/quizzes/{uid}/clear/{user_id}")
async def clear_attempt(
    uid: str,
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    check_csrf(request)
    quiz = await saved.get(db, uid)
    return {"removed": await saved.clear_attempt(db, quiz, user_id)}


@router.post("/api/quiz/random")
async def random_question(
    request: Request,
    body: RandomRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    check_csrf(request)
    return await builder.random_question(db, body.model_dump(), user)
