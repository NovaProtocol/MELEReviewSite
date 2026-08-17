from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_db
from api.models import Question
from api.routes.auth import get_current_account
from api.schemas import QuestionOut, QuestionWrite, TagOut
from api.services import question_service

router = APIRouter(prefix="/api", tags=["questions"])


async def _q_out(db, q) -> dict:
    tags = (await question_service.tags_for_questions(db, [q.id])).get(q.id, [])
    return question_service.question_dict(q, tags)


@router.get("/questions", response_model=list[QuestionOut])
async def list_questions(
    search: str = "",
    tag: str = "",
    include_inactive: bool = False,
    page: int = 1,
    per_page: int = 100,
    db: AsyncSession = Depends(get_db),
):
    questions, _ = await question_service.list_questions(
        db, search=search, tag=tag, include_inactive=include_inactive, page=page, per_page=per_page
    )
    tags = await question_service.tags_for_questions(db, [q.id for q in questions])
    return [question_service.question_dict(q, tags.get(q.id, [])) for q in questions]


@router.get("/questions/{question_id}", response_model=QuestionOut)
async def get_question(
    question_id: int,
    db: AsyncSession = Depends(get_db),
):
    q = await question_service.get_question(db, question_id)
    return await _q_out(db, q)


@router.post("/questions", response_model=QuestionOut, status_code=201)
async def create_question(
    body: QuestionWrite,
    _: Question = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    q = await question_service.create_question(db, body)
    return await _q_out(db, q)


@router.put("/questions/{question_id}", response_model=QuestionOut)
async def update_question(
    question_id: int,
    body: QuestionWrite,
    _: Question = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    q = await question_service.update_question(db, question_id, body)
    return await _q_out(db, q)


@router.delete("/questions/{question_id}", status_code=204)
async def delete_question(
    question_id: int,
    _: Question = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    await question_service.delete_question(db, question_id)
    return Response(status_code=204)


@router.post("/questions/{question_id}/flag")
async def flag_question(
    question_id: int,
    _: Question = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    q = await question_service.toggle_flag(db, question_id)
    return {"id": q.id, "flagged": q.flagged}


@router.get("/tags", response_model=list[TagOut])
async def list_tags(
    db: AsyncSession = Depends(get_db),
):
    return await question_service.list_tags(db)
