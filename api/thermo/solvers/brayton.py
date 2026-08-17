from __future__ import annotations

from api.thermo.solvers.base import CycleResult, register_solver
from api.thermo.solvers.ideal_gas import air_state, GAMMA


@register_solver("brayton")
def solve_brayton(fluid_name: str, params: dict) -> CycleResult:
    required = ["rp", "T1", "P1"]
    missing = [k for k in required if k not in params]
    if missing:
        return CycleResult(cycle="brayton", states=[], solved=False, missing=missing)

    rp = params["rp"]
    T1 = params["T1"]
    P1 = params["P1"]

    state1 = air_state(P1, T1)

    P2 = rp * P1
    T2 = T1 * (rp ** ((GAMMA - 1) / GAMMA))
    state2 = air_state(P2, T2)

    P3 = P2
    T3 = params.get("T3", T2 * 2.0)
    state3 = air_state(P3, T3)

    P4 = P1
    T4 = T3 / (rp ** ((GAMMA - 1) / GAMMA))
    state4 = air_state(P4, T4)

    return CycleResult(
        cycle="brayton",
        states=[state1, state2, state3, state4],
        solved=True,
        missing=[],
        processes=["isentropic", "isobaric", "isentropic", "isobaric"],
        fluid=fluid_name,
        ideal_gas=True,
    )
