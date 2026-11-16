"""The quiz page and the endpoints behind it.

The code is the only state: the builder returns one, a shared link carries one, and
the runner posts answers back with the code it was built from.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.db import get_db
from app.models import User
from app.services import library as library_service
from app.services import quiz as quiz_service
from app.templating import render

router = APIRouter(tags=["quiz"])


class QuizFilters(BaseModel):
    exclude_topics: list[int] = []
    kind: str = ""
    exclude_computation: bool = False
    unanswered_only: bool = False
    favourites_only: bool = False


class QuizBuildRequest(BaseModel):
    # topic id -> how many questions from it
    selections: dict[int, int] = Field(default_factory=dict)
    timer_minutes: int = Field(default=30, ge=0, le=600)
    group: str = Field(default="mixed", pattern="^(mixed|topic|subject)$")
    title: str = Field(default="", max_length=120)
    filters: QuizFilters = QuizFilters()


class RandomRequest(BaseModel):
    exclude_topics: list[int] = []
    kind: str = ""
    exclude_computation: bool = False
    unanswered_only: bool = False
    favourites_only: bool = False
    subject_id: int | None = None


class QuizAnswerRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40000)
    answers: dict[str, str] = Field(default_factory=dict)


@router.get("/quiz")
async def quiz_page(
    request: Request, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
):
    sizes = await quiz_service.bank_sizes(db)
    subjects = await library_service.list_subjects(db)
    rows = [
        {
            "id": subject["id"],
            "name": subject["name"],
            "topics": [
                {
                    "id": topic["id"],
                    "name": topic["name"],
                    "bank": sizes.get(topic["id"], 0),
                    "pool": min(sizes.get(topic["id"], 0), quiz_service.POOL_PER_TOPIC),
                }
                for topic in subject["topics"]
            ],
        }
        for subject in subjects
    ]
    return render(
        request,
        "quiz.html",
        {
            "viewer": user,
            "subjects": rows,
            "pool_cap": quiz_service.POOL_PER_TOPIC,
            "max_questions": quiz_service.MAX_QUESTIONS,
        },
    )


@router.post("/api/quiz/build")
async def build_quiz(
    request: Request,
    body: QuizBuildRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.auth import check_csrf

    check_csrf(request)
    settings = {
        "timer_minutes": body.timer_minutes,
        "group": body.group,
        "title": body.title.strip(),
        "filters": body.filters.model_dump(),
    }
    settings, ids = await quiz_service.build(db, body.selections, settings, user)
    code = quiz_service.encode(settings, ids)
    questions = await quiz_service.questions_for(db, ids)
    views = []
    for question in questions:
        view = await library_service.question_view(db, question, user, with_solutions=False)
        views.append(view)
    return {"code": code, "settings": settings, "questions": views}


@router.get("/api/quiz/{code}")
async def open_quiz(
    code: str, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> dict:
    settings, ids = quiz_service.decode(code)
    questions = await quiz_service.questions_for(db, ids)
    views = []
    for question in questions:
        view = await library_service.question_view(db, question, user, with_solutions=False)
        views.append(view)
    return {"code": code, "settings": settings, "questions": views}


@router.post("/api/quiz/random")
async def random_question(
    request: Request,
    body: RandomRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.auth import check_csrf

    check_csrf(request)
    return await quiz_service.random_question(db, body.model_dump(), user)


@router.post("/api/quiz/submit")
async def submit_quiz(
    request: Request,
    body: QuizAnswerRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.auth import check_csrf

    check_csrf(request)
    _settings, ids = quiz_service.decode(body.code)
    allowed = set(ids)
    answers = {
        int(question_id): letter
        for question_id, letter in body.answers.items()
        if question_id.isdigit() and int(question_id) in allowed
    }
    if not answers:
        raise HTTPException(status_code=422, detail="No answers to submit")
    return await quiz_service.submit(db, user, answers)
