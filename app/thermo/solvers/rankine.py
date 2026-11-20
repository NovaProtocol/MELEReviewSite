from __future__ import annotations

from app.thermo.props import from_ps, from_pt, resolve, sat_state, validate
from app.thermo.solvers.base import CycleResult, register_solver


@register_solver("rankine")
def solve_rankine(fluid_name: str, params: dict) -> CycleResult:
    """The Rankine cycle, with the variations a board exam asks about.

    Plain Rankine is four states: saturated liquid out of the condenser, pumped to
    boiler pressure, superheated, expanded isentropically. Two variations add states
    rather than changing the shape:

        reheat      the steam is expanded part way, returned to the boiler and
                    reheated, then expanded again. Six states.
        regeneration  a fraction of the steam is bled from the turbine to heat the
                    feedwater. Drawn as the bleed point and the feedwater heater.

    Both can be on at once. What each state is gets named in `processes`, because a
    diagram with six unlabelled dots teaches nothing.
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
    bleed = params.get("bleed", 0.0)

    try:
        fluid = resolve(fluid_name)
        validate(fluid, P=P_boiler, P_cond=P_cond, T=T_turbine)
        if P_cond >= P_boiler:
            raise ValueError("condenser pressure must be below boiler pressure")
        if T_reheat is not None and not (P_cond < P_reheat < P_boiler):
            raise ValueError("reheat pressure must sit between condenser and boiler")

        states = []
        processes = []

        # 1: saturated liquid leaving the condenser
        state1 = sat_state(fluid, P_cond, 0.0)
        states.append(state1)
        processes.append("condenser outlet, saturated liquid")

        # 2: isentropic pump to boiler pressure
        state2 = from_ps(fluid, P_boiler, state1.s)
        states.append(state2)
        processes.append("pump, isentropic")

        # 3: superheated steam entering the turbine
        state3 = from_pt(fluid, P_boiler, T_turbine)
        states.append(state3)
        processes.append("boiler outlet, superheated")

        if T_reheat is not None:
            # 4: partial expansion to the reheat pressure
            state4 = from_ps(fluid, P_reheat, state3.s)
            states.append(state4)
            processes.append("turbine, isentropic to reheat pressure")

            # 5: reheated back to the live steam temperature
            state5 = from_pt(fluid, P_reheat, T_reheat)
            states.append(state5)
            processes.append("reheater, isobaric")

            # 6: expansion to the condenser pressure
            state6 = from_ps(fluid, P_cond, state5.s)
            states.append(state6)
            processes.append("turbine, isentropic to condenser")
        else:
            state4 = from_ps(fluid, P_cond, state3.s)
            states.append(state4)
            processes.append("turbine, isentropic to condenser")

        if bleed:
            # The bled fraction leaves part way through the expansion and heats the
            # feedwater; the remainder carries on. Marked so the diagram can show it.
            state_bleed = from_ps(fluid, P_reheat if T_reheat else P_boiler / 4, state3.s)
            states.append(state_bleed)
            processes.append(f"bleed, {bleed * 100:.0f}% to feedwater heater")

        result = CycleResult(
            cycle="rankine",
            states=states,
            solved=True,
            missing=[],
            processes=processes,
            fluid=fluid_name,
            ideal_gas=False,
        )
    except ValueError as e:
        return CycleResult(cycle="rankine", states=[], solved=False, missing=[str(e)])

    return result
