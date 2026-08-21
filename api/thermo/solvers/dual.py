from __future__ import annotations

from api.thermo.solvers.base import CycleResult, register_solver
from api.thermo.solvers.ideal_gas import GAMMA, air_state


@register_solver("dual")
def solve_dual(fluid_name: str, params: dict) -> CycleResult:
    required = ["r", "rc", "rp", "T1", "P1"]
    missing = [k for k in required if k not in params]
    if missing:
        return CycleResult(cycle="dual", states=[], solved=False, missing=missing)

    r = params["r"]
    rc = params["rc"]
    rp = params["rp"]
    T1 = params["T1"]
    P1 = params["P1"]

    state1 = air_state(P1, T1)

    T2 = T1 * (r ** (GAMMA - 1))
    P2 = P1 * (r**GAMMA)
    state2 = air_state(P2, T2)

    P3 = rp * P2
    T3 = T2 * rp
    state3 = air_state(P3, T3)

    P4 = P3
    T4 = T3 * rc
    state4 = air_state(P4, T4)

    T5 = T4 * (rc / r) ** (GAMMA - 1)
    P5 = P4 * (rc / r) ** GAMMA
    state5 = air_state(P5, T5)

    return CycleResult(
        cycle="dual",
        states=[state1, state2, state3, state4, state5],
        solved=True,
        missing=[],
        processes=["isentropic", "isochoric", "isobaric", "isentropic", "isochoric"],
        fluid=fluid_name,
        ideal_gas=True,
    )
