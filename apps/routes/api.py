from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_config
from apps.db import get_db
from apps.schemas import (
    AnswerUpdate,
    QuestionCreate,
    QuestionList,
    QuestionOut,
    SourceList,
    SourceOut,
)
from apps.services import question_service, source_service

router = APIRouter(prefix="/api")


async def verify_write_access(
    request: Request,
    x_access_password: str | None = Header(None),
):
    config = get_config()
    # Method 1: API key header
    if x_access_password and x_access_password == config.ACCESS_PASSWORD:
        return
    # Method 2: web session cookie
    cookie = request.cookies.get("access_token")
    if cookie:
        from apps.routes.web import verify_access_cookie
        if verify_access_cookie(config.SECRET_KEY, cookie):
            return
    raise HTTPException(status_code=401, detail="Write access required")


@router.get("/sources", response_model=SourceList)
async def list_sources(db: AsyncSession = Depends(get_db)):
    sources = await source_service.list_sources(db)
    return SourceList(data=[SourceOut.model_validate(s) for s in sources])


@router.post("/sources", response_model=SourceOut, status_code=201)
async def upload_source(
    file: UploadFile = File(...),
    title: str = Form(""),
    _: str = Depends(verify_write_access),
    db: AsyncSession = Depends(get_db),
):
    pdf_bytes = await file.read()
    source = await source_service.upload_source(db, title, pdf_bytes)
    return SourceOut.model_validate(source)


@router.get("/sources/{source_id}/pdf")
async def get_source_pdf(source_id: int, db: AsyncSession = Depends(get_db)):
    pdf_bytes = await source_service.get_source_pdf(db, source_id)
    return Response(content=pdf_bytes, media_type="application/pdf")


@router.get("/sources/{source_id}/questions", response_model=QuestionList)
async def list_questions(source_id: int, db: AsyncSession = Depends(get_db)):
    questions = await question_service.list_questions(db, source_id)
    return QuestionList(data=[QuestionOut.model_validate(q) for q in questions])


@router.post("/sources/{source_id}/questions", status_code=201)
async def upload_questions(
    source_id: int,
    questions: list[QuestionCreate],
    _: str = Depends(verify_write_access),
    db: AsyncSession = Depends(get_db),
):
    db_questions = await question_service.upload_questions(db, source_id, questions)
    return {"count": len(db_questions)}


@router.put("/questions/{question_id}/answer")
async def update_answer(
    question_id: int,
    body: AnswerUpdate,
    _: str = Depends(verify_write_access),
    db: AsyncSession = Depends(get_db),
):
    question = await question_service.update_answer(db, question_id, body.answer)
    return {"id": question.id, "answer": question.answer}


@router.post("/questions/{question_id}/flag")
async def flag_question(
    question_id: int,
    _: str = Depends(verify_write_access),
    db: AsyncSession = Depends(get_db),
):
    question = await question_service.toggle_flag(db, question_id)
    return {"id": question.id, "flagged": question.flagged}
