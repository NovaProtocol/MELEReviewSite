"""The tool rail: calculators and the cycle solver, served for an embedded frame.

Each tool page is its own document with no app chrome, because the rail loads it
in an iframe. They are behind the session like every other page.
"""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.db import get_db
from app.models import User
from app.templating import render
from app.thermo import steam
from app.thermo.plot import PROPERTY_LABELS, dome_data, plot_data, segment_data
from app.thermo.props import StatePoint, resolve, state_from_props
from app.thermo.solvers import solve
from app.thermo.solvers.base import CycleResult

router = APIRouter(tags=["tools"])

TOOLS: tuple[dict, ...] = (
    {
        "slug": "unit",
        "name": "Unit converter",
        "group": "General",
        "keywords": "convert conversion unit metric english si length mass pressure temperature",
    },
    {
        "slug": "thermo",
        "name": "Thermo cycle solver",
        "group": "Thermodynamics",
        "keywords": (
            "carnot otto diesel dual rankine brayton vapor compression "
            "cycle entropy enthalpy turbine"
        ),
    },
    {
        "slug": "fluids",
        "name": "Pipe flow",
        "group": "Fluids",
        "keywords": "pump flow velocity reynolds friction head loss darcy pipe",
    },
    {
        "slug": "heat",
        "name": "Heat transfer",
        "group": "Thermodynamics",
        "keywords": "conduction convection radiation overall coefficient exchanger film",
    },
    {
        "slug": "strength",
        "name": "Strength of materials",
        "group": "Machine design",
        "keywords": "stress strain bending beam deflection torsion shaft moment",
    },
    {
        "slug": "steam",
        "name": "Steam and refrigerant tables",
        "group": "Thermodynamics",
        "keywords": (
            "steam table water saturated liquid vapour vapor superheated quality "
            "refrigerant r134a r410a ammonia enthalpy entropy specific volume "
            "pressure temperature wet dry dome"
        ),
    },
    {
        "slug": "psychro",
        "name": "Psychrometrics",
        "group": "HVAC",
        "keywords": (
            "air humidity wet bulb dry bulb enthalpy moisture air conditioning psychrometric"
        ),
    },
    {
        "slug": "machine",
        "name": "Machine elements",
        "group": "Machine design",
        "keywords": "belt gear chain bearing spring key coupling flywheel brake clutch",
    },
)

TOOL_BY_SLUG = {tool["slug"]: tool for tool in TOOLS}

CYCLES = ("carnot", "otto", "diesel", "dual", "rankine", "brayton", "vapor-compression")


class DiagramRequest(BaseModel):
    x: str = "s"
    y: str = "T"


class StateProps(BaseModel):
    P: float | None = None
    T: float | None = None
    h: float | None = None
    s: float | None = None
    v: float | None = None


class CycleRequest(BaseModel):
    cycle: str
    input_mode: str = "fluid"
    fluid: str = "water"
    parameters: dict[str, float] = {}
    states: list[StateProps] = []
    diagram: DiagramRequest = DiagramRequest()
    format: str = "data"


@router.get("/api/formulas")
async def formulas(
    q: str = "",
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Search the formulas inside the topic notes, by word or by symbol name."""
    from app.services import formulas as formula_service

    return {"results": await formula_service.search(db, q)}


@router.get("/tools/{slug}")
async def tool_page(
    request: Request,
    slug: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    tool = TOOL_BY_SLUG.get(slug)
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    cycle = request.query_params.get("cycle", "rankine")
    if cycle not in CYCLES:
        cycle = "rankine"
    return render(
        request,
        f"tools/{slug}.html",
        {
            "viewer": user,
            "tool": tool,
            "tools": TOOLS,
            "cycle": cycle,
            "cycles": CYCLES,
            "fluids": steam.FLUIDS,
        },
    )


def _guard(result: CycleResult) -> CycleResult:
    if any(
        not all(
            isinstance(getattr(state, key, None), float) and math.isfinite(getattr(state, key))
            for key in ("P", "T", "h", "s", "v")
        )
        for state in result.states
    ):
        return CycleResult(
            cycle=result.cycle,
            states=[],
            solved=False,
            missing=["inputs are outside the fluid property limits"],
        )
    return result


def _solve_manual(body: CycleRequest) -> CycleResult:
    fluid = resolve(body.fluid)
    solved_states: list[StatePoint] = []
    missing = []
    for index, state in enumerate(body.states):
        props = {k: v for k, v in state.model_dump().items() if v is not None}
        try:
            solved_states.append(state_from_props(fluid, props))
        except ValueError as exc:
            missing.append(f"state {index + 1}: {exc}")
    solved = len(solved_states) == len(body.states) and len(body.states) > 0
    return CycleResult(cycle=body.cycle, states=solved_states, solved=solved, missing=missing)


@router.post("/api/tools/cycle")
async def cycle_endpoint(body: CycleRequest, user: User = Depends(require_user)) -> dict:
    if body.input_mode == "manual":
        result = _solve_manual(body)
    else:
        result = _guard(solve(body.cycle, body.fluid, body.parameters))

    if body.format == "plot":
        payload = (
            plot_data(result, body.diagram.x, body.diagram.y)
            if result.solved
            else {"segments": [], "states": [], "dome": None}
        )
        return {
            "cycle": result.cycle,
            "fluid": body.fluid,
            "x": body.diagram.x,
            "y": body.diagram.y,
            "x_label": PROPERTY_LABELS.get(body.diagram.x, body.diagram.x),
            "y_label": PROPERTY_LABELS.get(body.diagram.y, body.diagram.y),
            "solved": result.solved,
            "missing": result.missing,
            **payload,
        }

    response = {
        "states": [
            {"point": i + 1, "P": s.P, "T": s.T, "h": s.h, "s": s.s, "v": s.v}
            for i, s in enumerate(result.states)
        ],
        "cycle": result.cycle,
        "fluid": body.fluid,
        "axes": {"x": body.diagram.x, "y": body.diagram.y},
        "solved": result.solved,
        "missing": result.missing,
    }
    if result.solved:
        response["segments"] = segment_data(result)
        if body.diagram.x == "s" and body.diagram.y == "T":
            response["dome"] = dome_data(result)
    return response


class SteamStateRequest(BaseModel):
    fluid: str = steam.DEFAULT_FLUID
    pressure: float | None = None
    temperature: float | None = None
    quality: float | None = None


def _fluid_or_fail(name: str) -> str:
    if name not in steam.FLUIDS:
        raise HTTPException(status_code=422, detail="Unknown fluid")
    return name


@router.get("/api/tools/steam/table")
async def steam_table(
    basis: str = "temperature",
    start: float = 0.0,
    stop: float = 100.0,
    count: int = 12,
    fluid: str = steam.DEFAULT_FLUID,
    user: User = Depends(require_user),
) -> dict:
    fluid = _fluid_or_fail(fluid)
    try:
        rows, truncated, clamped = steam.saturation_table(basis, start, stop, count, fluid)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "basis": basis,
        "fluid": fluid,
        "rows": rows,
        "truncated": truncated,
        "clamped": clamped,
    }


@router.get("/api/tools/steam/dome")
async def steam_dome(fluid: str = steam.DEFAULT_FLUID, user: User = Depends(require_user)) -> dict:
    fluid = _fluid_or_fail(fluid)
    return {"fluid": fluid, "dome": steam.dome(fluid)}


@router.post("/api/tools/steam/state")
async def steam_state(body: SteamStateRequest, user: User = Depends(require_user)) -> dict:
    fluid = _fluid_or_fail(body.fluid)
    try:
        result = steam.state(body.pressure, body.temperature, body.quality, fluid)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"fluid": fluid, "state": result, "charts": steam.chart_point(result)}
