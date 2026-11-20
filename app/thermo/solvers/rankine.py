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
    weighted accordingly.

    With reheat, the order is the one a plant actually has: the steam is expanded to
    the reheat pressure, returned to the boiler, and only then bled. Putting the bleed
    first and reheating afterwards would have the steam gaining pressure in the
    turbine, which is why the earlier version drew a leg going back up.
    """
    # Condensate side: condenser outlet, pumped to the extraction pressure, then
    # heated to saturation in the open heater.
    state1 = sat_state(fluid, P_cond, 0.0)
    state2 = from_ps(fluid, P_bleed, state1.s)
    heater_out = sat_state(fluid, P_bleed, 0.0)
    state3 = heater_out
    # Pump 2 raises the saturated liquid to boiler pressure.
    state4 = from_ps(fluid, P_boiler, state3.s)

    # Steam side.
    state5 = from_pt(fluid, P_boiler, T_turbine)
    states = [state1, state2, state3, state4, state5]
    processes = ["isentropic", "isobaric", "isentropic", "isobaric"]
    descriptions = [
        "pump 1, isentropic",
        "open feedwater heater, isobaric",
        "pump 2, isentropic",
        "boiler, isobaric",
    ]

    if T_reheat is not None:
        if P_reheat <= P_bleed:
            raise ValueError(
                "reheat pressure must be above the extraction pressure, or the bleed "
                "happens before the steam has been reheated"
            )
        # 6: high-pressure turbine exhaust, at the reheat pressure
        state6 = from_ps(fluid, P_reheat, state5.s)
        # 7: reheated back to live steam temperature
        state7 = from_pt(fluid, P_reheat, T_reheat)
        # 8: intermediate-pressure turbine down to the extraction point
        state8 = from_ps(fluid, P_bleed, state7.s)
        # 9: the rest of the expansion
        state9 = from_ps(fluid, P_cond, state8.s)
        states += [state6, state7, state8, state9]
        processes += ["isentropic", "isobaric", "isentropic", "isentropic"]
        descriptions += [
            "HP turbine, isentropic",
            "reheater, isobaric",
            "IP turbine, to extraction",
            "LP turbine, to condenser",
        ]
        extraction = state8
        bleed_from = 8
        heat = (state5.h - state4.h) + (state7.h - state6.h)
    else:
        # 6: expansion to the extraction point, 7: the rest of it
        state6 = from_ps(fluid, P_bleed, state5.s)
        extraction = state6
        state7 = from_ps(fluid, P_cond, state6.s)
        states += [state6, state7]
        processes += ["isentropic", "isentropic"]
        descriptions += ["turbine, to extraction", "turbine, to condenser"]
        heat = state5.h - state4.h
        bleed_from = 6

    # Mass balance at the open heater: y kg of bled steam plus (1 - y) kg of
    # condensate make 1 kg of saturated liquid at the extraction pressure.
    y = y_of(heater_out, state2, extraction)
    if not 0.0 < y < 1.0:
        raise ValueError(
            "those pressures give a bleed fraction outside 0 and 1, so the heater "
            "cannot be balanced"
        )

    # The turbine work, weighted by the mass flowing through each stage: everything
    # goes through the high-pressure stages, and only (1 - y) carries on past the
    # extraction.
    last = states[-1]
    hot_work = sum(
        states[i].h - states[i + 1].h
        for i in range(4, len(states) - 1)
        if states[i].P > states[i + 1].P
    ) - y * (extraction.h - last.h)

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
            "mass to condenser": f"{round(1 - y, 4)} kg",
        },
        # The bled steam is a real line on the drawing: it leaves the turbine at the
        # extraction point and arrives at the feedwater heater. Without it the boiler
        # appears to be fed by liquid that came from nowhere.
        branches=[
            {
                "from": bleed_from,
                "to": 3,
                "process": "isobaric",
                "description": f"bled steam, {y * 100:.1f}% to the feedwater heater",
            }
        ],
    )


def y_of(heater_out, pump_out, extraction) -> float:
    """The bled fraction from the open heater's energy balance.

    y kg at the extraction state plus (1 - y) kg of condensate become 1 kg of saturated
    liquid, so y = (h_out - h_cold) / (h_hot - h_cold). Entered by hand it would be a
    guess; derived, it is the only value the heater can balance with.
    """
    if extraction.h - pump_out.h <= 0:
        raise ValueError("the extraction state is not hot enough to heat the feedwater")
    return (heater_out.h - pump_out.h) / (extraction.h - pump_out.h)
