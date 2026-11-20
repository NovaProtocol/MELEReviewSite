from __future__ import annotations

from app.thermo.props import from_ps, from_pt, resolve, sat_state, validate
from app.thermo.solvers.base import CycleResult, register_solver


@register_solver("rankine")
def solve_rankine(fluid_name: str, params: dict) -> CycleResult:
    """The Rankine cycle, with what a board exam varies.

    Plain Rankine is four states: saturated liquid out of the condenser, pumped to
    boiler pressure, superheated, expanded isentropically, condensed.

    Two variations change the machine rather than drawing extra lines:

        reheat          the steam is expanded part way, returned to the boiler and
                        reheated. Two more states.
        regeneration    steam is bled from the turbine to an open feedwater heater,
                        where it mixes with the condensate and raises the temperature of
                        what enters the boiler. The bled fraction is a mass balance:
                        only (1 - y) kg of every kilogram reaches the condenser, so the
                        work and heat of each stage are weighted by the mass flowing.

    An open heater at the extraction pressure mixes bled steam and condensate into
    saturated liquid at that pressure, which is the standard treatment and needs no
    separate heater model.

    `processes` is indexed by leg: entry i is the path from states[i] to states[i+1],
    and the last closes the loop.
    """
    required = ["P_boiler", "P_cond", "T_turbine"]
    missing = [k for k in required if k not in params]
    if missing:
        return CycleResult(cycle="rankine", states=[], solved=False, missing=missing)

    P_boiler = float(params["P_boiler"])
    P_cond = float(params["P_cond"])
    T_turbine = float(params["T_turbine"])
    T_reheat = params.get("T_reheat")
    P_reheat = float(params.get("P_reheat", P_boiler / 4))
    regeneration = bool(params.get("regeneration") or params.get("P_bleed"))
    P_bleed = float(params.get("P_bleed", P_reheat if T_reheat else P_boiler / 5))

    try:
        fluid = resolve(fluid_name)
        validate(fluid, P=P_boiler, P_cond=P_cond, T=T_turbine)
        if P_cond >= P_boiler:
            raise ValueError("condenser pressure must be below boiler pressure")
        if T_reheat is not None and not (P_cond < P_reheat < P_boiler):
            raise ValueError("reheat pressure must sit between condenser and boiler")
        if regeneration and not (P_cond < P_bleed < P_boiler):
            raise ValueError("extraction pressure must sit between condenser and boiler")

        # Heat rejected and heat added are per kilogram of steam through the boiler,
        # which is the denominator a candidate reports efficiency against.
        if regeneration:
            return _regenerative(fluid, fluid_name, P_boiler, P_cond, T_turbine,
                                 T_reheat, P_reheat, P_bleed)
        return _simple(fluid, fluid_name, P_boiler, P_cond, T_turbine, T_reheat, P_reheat)
    except ValueError as e:
        return CycleResult(cycle="rankine", states=[], solved=False, missing=[str(e)])


def _simple(fluid: str, fluid_name: str, P_boiler: float, P_cond: float,
            T_turbine: float, T_reheat, P_reheat: float) -> CycleResult:
    """Rankine, with or without reheat, without extraction."""
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
        states.append(from_ps(fluid, P_reheat, state3.s))
        states.append(from_pt(fluid, P_reheat, T_reheat))
        states.append(from_ps(fluid, P_cond, states[-1].s))
        processes += ["isentropic", "isobaric", "isentropic"]
        descriptions += [
            "turbine, to reheat pressure",
            "reheater, isobaric",
            "turbine, to condenser",
        ]
        turbine = (state3.h - states[3].h) + (states[4].h - states[5].h)
    else:
        states.append(from_ps(fluid, P_cond, state3.s))
        processes.append("isentropic")
        descriptions.append("turbine, isentropic")
        turbine = state3.h - states[3].h

    processes.append("isobaric")
    descriptions.append("condenser, isobaric")

    pump = state2.h - state1.h
    heat = state3.h - state2.h
    if T_reheat is not None:
        heat += states[4].h - states[3].h
    net = turbine - pump

    return CycleResult(
        cycle="rankine",
        states=states,
        solved=True,
        missing=[],
        processes=processes,
        descriptions=descriptions,
        fluid=fluid_name,
        ideal_gas=False,
        net_work=net,
        heat_added=heat,
        turbine_work=turbine,
        pump_work=pump,
        efficiency=(net / heat) if heat > 0 else None,
        extras={"reheat": T_reheat is not None},
    )


def _regenerative(fluid: str, fluid_name: str, P_boiler: float, P_cond: float,
                  T_turbine: float, T_reheat, P_reheat: float,
                  P_bleed: float) -> CycleResult:
    """Rankine with one open feedwater heater.

    The numbers are per kilogram through the boiler. A fraction y of it leaves the
    turbine at the extraction pressure and heats the feedwater, so downstream of the
    heater only (1 - y) is being pumped and boiled, and the work of those stages is
    weighted accordingly. Without the weighting the efficiency comes out too high,
    which is the whole reason to draw the cycle at all.
    """
    # Condensate side: condenser outlet, pumped to the extraction pressure, then
    # heated to saturation in the open heater.
    state1 = sat_state(fluid, P_cond, 0.0)
    state2 = from_ps(fluid, P_bleed, state1.s)
    heater_out = sat_state(fluid, P_bleed, 0.0)
    state3 = heater_out
    # Pump 2 raises the saturated liquid to boiler pressure.
    state4 = from_ps(fluid, P_boiler, state3.s)

    # Steam side: boiler outlet, expansion to the extraction point, and the rest of the
    # expansion to the condenser.
    state5 = from_pt(fluid, P_boiler, T_turbine)
    state6 = from_ps(fluid, P_bleed, state5.s)

    # Mass balance at the open heater: y kg of bled steam plus (1 - y) kg of
    # condensate make 1 kg of saturated liquid at the extraction pressure.
    if state6.h - state2.h <= 0:
        raise ValueError("the extraction state is not hot enough to heat the feedwater")
    y = (heater_out.h - state2.h) / (state6.h - state2.h)
    if not 0.0 < y < 1.0:
        raise ValueError(
            "those pressures give a bleed fraction outside 0 and 1, so the heater "
            "cannot be balanced"
        )

    states = [state1, state2, state3, state4, state5, state6]
    processes = ["isentropic", "isobaric", "isentropic", "isobaric", "isentropic"]
    descriptions = [
        "pump 1, isentropic",
        "open feedwater heater, isobaric",
        "pump 2, isentropic",
        "boiler, isobaric",
        "turbine, to extraction",
    ]

    if T_reheat is not None:
        # Reheat after the extraction, at or above the extraction pressure, so the
        # bled steam has already left.
        reheat_p = max(P_reheat, P_bleed)
        state7 = from_pt(fluid, reheat_p, T_reheat)
        state8 = from_ps(fluid, P_cond, state7.s)
        states += [state7, state8]
        processes += ["isobaric", "isentropic"]
        descriptions += ["reheater, isobaric", "turbine, to condenser"]
        # Only the steam still in the turbine after the extraction is reheated.
        hot_work = (state5.h - state6.h) + (1 - y) * (state7.h - state8.h)
        heat = (state5.h - state4.h) + (1 - y) * (state7.h - state6.h)
    else:
        state7 = from_ps(fluid, P_cond, state6.s)
        states.append(state7)
        processes.append("isentropic")
        descriptions.append("turbine, to condenser")
        hot_work = (state5.h - state6.h) + (1 - y) * (state6.h - state7.h)
        heat = state5.h - state4.h

    processes.append("isobaric")
    descriptions.append("condenser, isobaric")

    # Pump 1 moves the whole kilogram; pump 2 moves only what the heater passed on.
    pump = (state2.h - state1.h) + (state4.h - state3.h)
    net = hot_work - pump

    return CycleResult(
        cycle="rankine",
        states=states,
        solved=True,
        missing=[],
        processes=processes,
        descriptions=descriptions,
        fluid=fluid_name,
        ideal_gas=False,
        net_work=net,
        heat_added=heat,
        turbine_work=hot_work,
        pump_work=pump,
        efficiency=(net / heat) if heat > 0 else None,
        extras={
            "bleed fraction": round(y, 4),
            "extraction pressure": round(P_bleed, 1),
            "reheat": T_reheat is not None,
            "mass to boiler": "1 kg",
            "mass to condenser": f"{round(1 - y, 4)} kg",
        },
    )
