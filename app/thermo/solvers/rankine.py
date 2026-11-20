from __future__ import annotations

from app.thermo.props import from_ps, from_pt, resolve, sat_state, validate
from app.thermo.solvers.base import CycleResult, register_solver


@register_solver("rankine")
def solve_rankine(fluid_name: str, params: dict) -> CycleResult:
    """The Rankine cycle, with the variation a board exam asks about.

    Plain Rankine is four states: saturated liquid out of the condenser, pumped to
    boiler pressure, superheated, expanded isentropically, condensed. Reheat adds two
    states rather than changing the shape.

    `processes` is indexed by leg, not by state: entry i is the path from states[i] to
    states[i+1], with the last entry closing the loop. Writing it per state shifted
    every leg by one, and the sampler then drew the condenser as an isentropic
    expansion, which collapsed the closing leg to a single point.
    """
    required = ["P_boiler", "P_cond", "T_turbine"]
    missing = [k for k in required if k not in params]
    if missing:
        return CycleResult(cycle="rankine", states=[], solved=False, missing=missing)

    P_boiler = params["P_boiler"]
    P_cond = params["P_cond"]
    T_turbine = params["T_turbine"]
    T_reheat = params.get("T_reheat")
    P_reheat = params.get("P_reheat", P_boiler / 4)

    try:
        fluid = resolve(fluid_name)
        validate(fluid, P=P_boiler, P_cond=P_cond, T=T_turbine)
        if P_cond >= P_boiler:
            raise ValueError("condenser pressure must be below boiler pressure")
        if T_reheat is not None and not (P_cond < P_reheat < P_boiler):
            raise ValueError("reheat pressure must sit between condenser and boiler")

        # 1: saturated liquid leaving the condenser
        state1 = sat_state(fluid, P_cond, 0.0)
        # 2: isentropic pump to boiler pressure
        state2 = from_ps(fluid, P_boiler, state1.s)
        # 3: superheated steam entering the turbine
        state3 = from_pt(fluid, P_boiler, T_turbine)

        states = [state1, state2, state3]
        processes = ["isentropic", "isobaric"]
        descriptions = ["pump, isentropic", "boiler, isobaric"]

        if T_reheat is not None:
            # 4: partial expansion to the reheat pressure
            states.append(from_ps(fluid, P_reheat, state3.s))
            # 5: reheated back to the live steam temperature
            states.append(from_pt(fluid, P_reheat, T_reheat))
            # 6: expansion to the condenser pressure
            states.append(from_ps(fluid, P_cond, states[-1].s))
            processes += ["isentropic", "isobaric", "isentropic"]
            descriptions += [
                "turbine, to reheat pressure",
                "reheater, isobaric",
                "turbine, to condenser",
            ]
        else:
            # 4: isentropic expansion to the condenser pressure
            states.append(from_ps(fluid, P_cond, state3.s))
            processes.append("isentropic")
            descriptions.append("turbine, isentropic")

        # The closing leg is the condenser in both shapes. It is one point on a T-s
        # diagram, because both ends sit at the same temperature: the working fluid
        # enters wet and leaves saturated. That is the cycle, not a drawing fault.
        processes.append("isobaric")
        descriptions.append("condenser, isobaric")

        return CycleResult(
            cycle="rankine",
            states=states,
            solved=True,
            missing=[],
            processes=processes,
            descriptions=descriptions,
            fluid=fluid_name,
            ideal_gas=False,
        )
    except ValueError as e:
        return CycleResult(cycle="rankine", states=[], solved=False, missing=[str(e)])
