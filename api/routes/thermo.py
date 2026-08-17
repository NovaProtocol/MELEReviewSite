from __future__ import annotations

import math

from fastapi import APIRouter
from pydantic import BaseModel

from api.thermo.plot import segment_data, plot_data, dome_data, PROPERTY_LABELS
from api.thermo.props import resolve, state_from_props, StatePoint
from api.thermo.solvers import solve
from api.thermo.solvers.base import CycleResult

router = APIRouter(prefix="/api", tags=["thermo"])


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
    format: str = "data"  # data | plot


@router.post("/cycle")
def cycle_endpoint(req: CycleRequest) -> dict:
    if req.input_mode == "manual":
        result = _solve_manual(req)
    else:
        result = _guard(solve(req.cycle, req.fluid, req.parameters))

    if req.format == "plot":
        pd = (
            plot_data(result, req.diagram.x, req.diagram.y)
            if result.solved
            else {"segments": [], "states": [], "dome": None}
        )
        return {
            "cycle": result.cycle,
            "fluid": req.fluid,
            "x": req.diagram.x,
            "y": req.diagram.y,
            "x_label": PROPERTY_LABELS.get(req.diagram.x, req.diagram.x),
            "y_label": PROPERTY_LABELS.get(req.diagram.y, req.diagram.y),
            "solved": result.solved,
            "missing": result.missing,
            **pd,
        }

    response = {
        "states": [
            {"point": i + 1, "P": s.P, "T": s.T, "h": s.h, "s": s.s, "v": s.v}
            for i, s in enumerate(result.states)
        ],
        "cycle": result.cycle,
        "fluid": req.fluid,
        "axes": {"x": req.diagram.x, "y": req.diagram.y},
        "solved": result.solved,
        "missing": result.missing,
    }
    if result.solved:
        response["segments"] = segment_data(result)
        if req.diagram.x == "s" and req.diagram.y == "T":
            response["dome"] = dome_data(result)
    return response


def _guard(result: CycleResult) -> CycleResult:
    if any(
        not all(isinstance(getattr(s, k, None), float) and math.isfinite(getattr(s, k)) for k in ("P", "T", "h", "s", "v"))
        for s in result.states
    ):
        return CycleResult(
            cycle=result.cycle,
            states=[],
            solved=False,
            missing=["inputs are outside the fluid property limits"],
        )
    return result


def _solve_manual(req: CycleRequest) -> CycleResult:
    fluid = resolve(req.fluid)
    solved_states: list[StatePoint] = []
    missing = []
    for i, state in enumerate(req.states):
        props = {k: v for k, v in state.model_dump().items() if v is not None}
        try:
            solved_states.append(state_from_props(fluid, props))
        except ValueError as e:
            missing.append(f"state {i + 1}: {e}")
    solved = len(solved_states) == len(req.states) and len(req.states) > 0
    return CycleResult(
        cycle=req.cycle,
        states=solved_states,
        solved=solved,
        missing=missing,
    )
