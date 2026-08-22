from __future__ import annotations

from api.thermo.solvers.base import CycleResult, register_solver
from api.thermo.solvers.ideal_gas import GAMMA, air_state


@register_solver("carnot")
def solve_carnot(fluid_name: str, params: dict) -> CycleResult:
    required = ["T_high", "T_low"]
    missing = [k for k in required if k not in params]
    if missing:
        return CycleResult(cycle="carnot", states=[], solved=False, missing=missing)

    T_high = params["T_high"]
    T_low = params["T_low"]
    P1 = params.get("P1", 101325.0)
    # Isothermal expansion ratio (diagram width)
    r_exp = params.get("r_exp", 2.0)

    exp = GAMMA / (GAMMA - 1)
    P2 = P1 * (T_high / T_low) ** exp
    P3 = P2 / r_exp
    P4 = P1 / r_exp

    states = [
        air_state(P1, T_low),
        air_state(P2, T_high),
        air_state(P3, T_high),
        air_state(P4, T_low),
    ]
    return CycleResult(
        cycle="carnot",
        states=states,
        solved=True,
        missing=[],
        processes=["isentropic", "isothermal", "isentropic", "isothermal"],
        fluid=fluid_name,
        ideal_gas=True,
    )
