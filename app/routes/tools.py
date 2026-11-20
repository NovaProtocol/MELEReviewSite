"""The tool rail: calculators and the cycle solver, served for an embedded frame.

Each tool page is its own document with no app chrome, because the rail loads it
in an iframe. They are behind the session like every other page.
"""

from __future__ import annotations

import asyncio
import math

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
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


class SolveRequest(BaseModel):
    equation: str = Field(min_length=1, max_length=500)
    known: dict[str, float] = Field(default_factory=dict)
    unknown: str = Field(min_length=1, max_length=40)


@router.get("/api/tools/psychrometric")
async def psychrometric(
    dry_bulb: float = 30.0,
    rh: float = 0.6,
    pressure: float = 101.325,
    user: User = Depends(require_user),
):
    """Moist air from a dry-bulb temperature and a relative humidity.

    Part of the tool API rather than of a page: the client draws this, so the numbers
    have to be reachable without a template.
    """
    from app.services import properties

    try:
        return properties.psychrometric(dry_bulb, rh, pressure)
    except properties.PropertyError as problem:
        raise HTTPException(status_code=422, detail=str(problem)) from problem


@router.get("/api/tools/fluids")
async def fluids(user: User = Depends(require_user)) -> dict:
    """The fluids every tool accepts, so a client does not keep its own copy."""
    return steam.FLUIDS


@router.get("/api/charts/cycle/{cycle}")
async def cycle_chart(
    cycle: str,
    override_data: str = "",
    user: User = Depends(require_user),
):
    """A cycle diagram as SVG, redrawn from the link.

    The link carries the cycle, the axes, the fluid and the parameters, so a diagram
    embedded in a solution reproduces itself later with no stored image. It is drawn by
    the cycle solver, so the states sit where the properties say they do.
    """
    import json
    from base64 import b64decode

    from fastapi.responses import Response

    from app.thermo import plot
    from app.thermo.solvers import solve as solve_cycle

    if cycle not in CYCLES:
        raise HTTPException(status_code=404, detail="No such cycle")

    settings: dict = {}
    if override_data:
        try:
            settings = json.loads(b64decode(override_data + "=" * (-len(override_data) % 4)))
        except ValueError:
            settings = {}
    if not isinstance(settings, dict):
        settings = {}

    fluid = str(settings.get("fluid", "water"))
    axes = settings.get("x"), settings.get("y")
    if not all(axes):
        axes = ("s", "T")
    parameters = settings.get("parameters") or {}

    try:
        result = solve_cycle(cycle, fluid, parameters)
    except ValueError as problem:
        raise HTTPException(status_code=422, detail=str(problem)) from problem
    if not result.solved:
        raise HTTPException(status_code=422, detail="; ".join(result.missing))

    svg = await asyncio.to_thread(plot.svg, result, axes[0], axes[1])
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/api/formulas/list")
async def formula_list(
    q: str = "",
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """The solver's catalogue, filtered by a word.

    Separate from the search index over the topic notes: those are formulas as
    written in the book, and these are formulas with variables a solver can use.
    """
    from sqlalchemy import select

    from app.models import Formula

    rows = (await db.execute(select(Formula).order_by(Formula.section, Formula.name))).scalars()
    needle = q.strip().lower()
    out = []
    for row in rows:
        haystack = f"{row.name} {row.section} {row.equation} {' '.join(row.variables)}".lower()
        if needle and needle not in haystack:
            continue
        out.append(
            {
                "id": row.id,
                "slug": row.slug,
                "name": row.name,
                "section": row.section,
                "equation": row.equation,
                "variables": row.variables,
                "notes": row.notes,
            }
        )
    return {"results": out}


@router.post("/api/formulas/solve")
async def formula_solve(body: SolveRequest, user: User = Depends(require_user)):
    """Answer an unknown from the values given for the rest."""
    from app.services import formula_solver

    if body.unknown in body.known:
        raise HTTPException(status_code=422, detail="Give values for everything except the unknown")
    try:
        value = formula_solver.solve(body.equation, body.known, body.unknown)
    except ValueError as problem:
        raise HTTPException(status_code=422, detail=str(problem)) from problem
    return {"unknown": body.unknown, "value": value}


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
            {
                "point": i + 1,
                "P": s.P,
                "T": s.T,
                "h": s.h,
                "s": s.s,
                "v": s.v,
                # The phase, from the property library rather than a guess from the
                # enthalpy: a threshold cannot tell saturated vapour from a superheated
                # state that happens to share its enthalpy.
                "phase": _phase_of(body.fluid, s.P, s.T),
                "quality": _quality_of(body.fluid, s.P, s.T),
            }
            for i, s in enumerate(result.states)
        ],
        "cycle": result.cycle,
        "fluid": body.fluid,
        "processes": result.processes,
        "descriptions": result.descriptions,
        # The cycle totals, weighted by mass where steam leaves early. The client
        # shows these instead of re-deriving them from the state enthalpies, which
        # cannot account for a bleed.
        "net_work": result.net_work,
        "heat_added": result.heat_added,
        "turbine_work": result.turbine_work,
        "pump_work": result.pump_work,
        "efficiency": result.efficiency,
        "extras": result.extras,
        "axes": {"x": body.diagram.x, "y": body.diagram.y},
        "solved": result.solved,
        "missing": result.missing,
    }
    if result.solved:
        response["segments"] = segment_data(result)
        if body.diagram.x == "s" and body.diagram.y == "T":
            response["dome"] = dome_data(result)
    return response


def _phase_of(fluid: str, pressure: float, temperature: float) -> str:
    """What the fluid is at this point: liquid, mixture, vapour, supercritical."""
    from CoolProp.CoolProp import PropsSI

    from app.thermo.props import resolve

    try:
        actual = resolve(fluid)
        critical_p = PropsSI("pcrit", actual)
        if pressure >= critical_p:
            return "supercritical"
        saturation = PropsSI("T", "P", pressure, "Q", 0, actual)
        if temperature < saturation - 0.05:
            return "liquid"
        if abs(temperature - saturation) <= 0.5:
            # On the line: saturated. Which side comes from what the solver gave, and
            # a state on the dome is a saturated one either way.
            return "saturated"
        return "superheated"
    except (ValueError, RuntimeError):
        return ""


def _quality_of(fluid: str, pressure: float, temperature: float) -> float | None:
    """The dryness fraction, for a state inside the dome."""
    from CoolProp.CoolProp import PropsSI

    from app.thermo.props import resolve

    try:
        return float(PropsSI("Q", "P", pressure, "T", temperature, resolve(fluid)))
    except (ValueError, RuntimeError):
        return None


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
