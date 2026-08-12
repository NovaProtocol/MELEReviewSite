from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from itsdangerous import URLSafeSerializer, BadSignature, SignatureExpired

from apps.config import get_config
from apps.db import get_db
from apps.services import question_service, source_service

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def create_access_cookie(secret: str, password: str) -> str:
    serializer = URLSafeSerializer(secret)
    return serializer.dumps({"password": password})


def verify_access_cookie(secret: str, cookie_value: str) -> bool:
    serializer = URLSafeSerializer(secret)
    try:
        data = serializer.loads(cookie_value)
        return data.get("password") == get_config().ACCESS_PASSWORD
    except (BadSignature, SignatureExpired):
        return False


def get_write_mode(request: Request) -> bool:
    config = get_config()
    cookie_value = request.cookies.get("access_token")
    if not cookie_value:
        return False
    return verify_access_cookie(config.SECRET_KEY, cookie_value)


def require_write_mode(request: Request) -> None:
    if not get_write_mode(request):
        raise HTTPException(status_code=401, detail="Write access required")


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse(request, "landing.html", {"write_mode": get_write_mode(request)})


@router.get("/sources", response_class=HTMLResponse)
async def sources_list(request: Request, db: AsyncSession = Depends(get_db)):
    sources = await source_service.list_sources(db)
    return templates.TemplateResponse(
        request,
        "sources.html",
        {"sources": sources, "write_mode": get_write_mode(request)},
    )


@router.get("/sources/new", response_class=HTMLResponse)
async def source_upload_form(request: Request, _: None = Depends(require_write_mode)):
    return templates.TemplateResponse(request, "source_form.html", {"write_mode": True})


@router.post("/sources/new")
async def source_upload_submit(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(""),
    _: None = Depends(require_write_mode),
    db: AsyncSession = Depends(get_db),
):
    pdf_bytes = await file.read()
    try:
        source = await source_service.upload_source(db, title, pdf_bytes)
    except HTTPException as exc:
        return templates.TemplateResponse(
            request,
            "source_form.html",
            {"write_mode": True, "error": exc.detail, "title": title},
            status_code=exc.status_code,
        )
    return RedirectResponse(f"/sources/{source.id}", status_code=303)


@router.get("/sources/{source_id}", response_class=HTMLResponse)
async def source_questions(request: Request, source_id: int, db: AsyncSession = Depends(get_db)):
    source = await source_service.get_source(db, source_id)
    questions = await question_service.list_questions(db, source_id)
    return templates.TemplateResponse(
        request,
        "questions.html",
        {
            "source": source,
            "questions": questions,
            "write_mode": get_write_mode(request),
        },
    )


@router.get("/sources/{source_id}/questions/new", response_class=HTMLResponse)
async def question_upload_form(
    request: Request,
    source_id: int,
    _: None = Depends(require_write_mode),
    db: AsyncSession = Depends(get_db),
):
    source = await source_service.get_source(db, source_id)
    return templates.TemplateResponse(
        request,
        "question_form.html",
        {"source": source, "write_mode": True},
    )


@router.post("/sources/{source_id}/questions/new")
async def question_upload_submit(
    request: Request,
    source_id: int,
    question_text: str = Form(...),
    choice_a: str = Form(...),
    choice_b: str = Form(...),
    choice_c: str = Form(...),
    choice_d: str = Form(...),
    choice_e: str = Form(""),
    answer: str = Form(""),
    _: None = Depends(require_write_mode),
    db: AsyncSession = Depends(get_db),
):
    source = await source_service.get_source(db, source_id)
    answer_idx = None
    if answer:
        try:
            answer_idx = int(answer) - 1
        except ValueError:
            answer_idx = None

    question = question_service.make_question(
        question_text=question_text,
        choice_a=choice_a,
        choice_b=choice_b,
        choice_c=choice_c,
        choice_d=choice_d,
        choice_e=choice_e or None,
        answer=answer_idx,
    )
    await question_service.add_question(db, source_id, question)
    return RedirectResponse(f"/sources/{source_id}", status_code=303)


@router.post("/auth/login")
async def login(
    response: Response,
    access_password: str = Form(...),
):
    config = get_config()
    if access_password != config.ACCESS_PASSWORD:
        return RedirectResponse("/?error=invalid_password", status_code=303)
    
    cookie_value = create_access_cookie(config.SECRET_KEY, access_password)
    response = RedirectResponse("/sources", status_code=303)
    response.set_cookie("access_token", cookie_value, httponly=True, samesite="lax")
    return response


@router.get("/auth/logout")
async def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("access_token")
    return response



