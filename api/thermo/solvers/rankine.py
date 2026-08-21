from __future__ import annotations

from api.thermo.props import from_ps, from_pt, resolve, sat_state, validate
from api.thermo.solvers.base import CycleResult, register_solver


@register_solver("rankine")
def solve_rankine(fluid_name: str, params: dict) -> CycleResult:
    required = ["P_boiler", "P_cond", "T_turbine"]
    missing = [k for k in required if k not in params]
    if missing:
        return CycleResult(cycle="rankine", states=[], solved=False, missing=missing)

    P_boiler = params["P_boiler"]
    P_cond = params["P_cond"]
    T_turbine = params["T_turbine"]

    try:
        fluid = resolve(fluid_name)
        validate(fluid, P=P_boiler, P_cond=P_cond, T=T_turbine)
        if P_cond >= P_boiler:
            raise ValueError("condenser pressure must be below boiler pressure")

        # 1: saturated liquid at condenser pressure (after condenser)
        state1 = sat_state(fluid, P_cond, 0.0)
        # 2: isentropic pump to boiler pressure (s2 = s1; tiny T rise)
        state2 = from_ps(fluid, P_boiler, state1.s)
        # 3: superheated steam entering turbine
        state3 = from_pt(fluid, P_boiler, T_turbine)
        # 4: isentropic turbine expansion to condenser pressure
        state4 = from_ps(fluid, P_cond, state3.s)
    except ValueError as e:
        return CycleResult(cycle="rankine", states=[], solved=False, missing=[str(e)])

    return CycleResult(
        cycle="rankine",
        states=[state1, state2, state3, state4],
        solved=True,
        missing=[],
        processes=["isentropic", "isobaric", "isentropic", "isobaric"],
        fluid=fluid_name,
        ideal_gas=False,
    )
