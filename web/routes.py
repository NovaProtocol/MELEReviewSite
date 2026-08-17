from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))


@router.get("/", response_class=HTMLResponse)
async def login(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@router.get("/questions", response_class=HTMLResponse)
async def questions(request: Request):
    return templates.TemplateResponse(request, "questions.html", {})


@router.get("/questions/new", response_class=HTMLResponse)
async def question_new(request: Request):
    return templates.TemplateResponse(request, "question_form.html", {"question_id": None})


@router.get("/questions/{question_id}/edit", response_class=HTMLResponse)
async def question_edit(request: Request, question_id: int):
    return templates.TemplateResponse(request, "question_form.html", {"question_id": question_id})


@router.get("/calculators", response_class=HTMLResponse)
async def calculators(request: Request):
    return templates.TemplateResponse(request, "calculators.html", {})


@router.get("/calculators/thermo", response_class=HTMLResponse)
async def calculator_thermo(request: Request, cycle: str = "rankine"):
    allowed = {"carnot", "otto", "diesel", "dual", "rankine", "brayton", "vapor-compression"}
    if cycle not in allowed:
        cycle = "rankine"
    return templates.TemplateResponse(request, "calculators/thermo.html", {"cycle": cycle})


@router.get("/calculators/unit", response_class=HTMLResponse)
async def calculator_unit(request: Request):
    return templates.TemplateResponse(request, "calculators/unit.html", {})


@router.get("/calculators/fluids", response_class=HTMLResponse)
async def calculator_fluids(request: Request):
    return templates.TemplateResponse(request, "calculators/fluids.html", {})


@router.get("/calculators/strength", response_class=HTMLResponse)
async def calculator_strength(request: Request):
    return templates.TemplateResponse(request, "calculators/strength.html", {})


@router.get("/calculators/heat", response_class=HTMLResponse)
async def calculator_heat(request: Request):
    return templates.TemplateResponse(request, "calculators/heat.html", {})


@router.get("/calculators/psychro", response_class=HTMLResponse)
async def calculator_psychro(request: Request):
    return templates.TemplateResponse(request, "calculators/psychro.html", {})


@router.get("/calculators/machine", response_class=HTMLResponse)
async def calculator_machine(request: Request):
    return templates.TemplateResponse(request, "calculators/machine.html", {})


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
