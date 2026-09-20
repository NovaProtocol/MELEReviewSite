from __future__ import annotations

from CoolProp.CoolProp import PropsSI

from api.thermo.props import from_ph, from_ps, from_pt, resolve, sat_state, validate
from api.thermo.solvers.base import CycleResult, register_solver


@register_solver("vapor_compression")
@register_solver("vapor-compression")
def solve_vapor_compression(fluid_name: str, params: dict) -> CycleResult:
    required = ["P_evap", "P_cond", "T_comp"]
    missing = [k for k in required if k not in params]
    if missing:
        return CycleResult(cycle="vapor-compression", states=[], solved=False, missing=missing)

    P_evap = params["P_evap"]
    P_cond = params["P_cond"]
    T_comp = params["T_comp"]

    try:
        fluid = resolve(fluid_name)
        validate(fluid, P=P_evap, P_cond=P_cond, T=T_comp)
        if P_evap >= P_cond:
            raise ValueError("evaporator pressure must be below condenser pressure")

        t_sat_evap = PropsSI("T", "P", P_evap, "Q", 0, fluid)

        # 1: compressor inlet, superheated above T_sat, else saturated vapor
        if T_comp > t_sat_evap:
            state1 = from_pt(fluid, P_evap, T_comp)
        else:
            state1 = sat_state(fluid, P_evap, 1.0)

        # 2: isentropic compression to condenser pressure
        state2 = from_ps(fluid, P_cond, state1.s)
        # 3: saturated liquid leaving condenser
        state3 = sat_state(fluid, P_cond, 0.0)
        # 4: isenthalpic throttling back to evaporator pressure
        state4 = from_ph(fluid, P_evap, state3.h)
    except ValueError as e:
        return CycleResult(cycle="vapor-compression", states=[], solved=False, missing=[str(e)])

    return CycleResult(
        cycle="vapor-compression",
        states=[state1, state2, state3, state4],
        solved=True,
        missing=[],
        processes=["isentropic", "isobaric", "isenthalpic", "isobaric"],
        fluid=fluid_name,
        ideal_gas=False,
    )
