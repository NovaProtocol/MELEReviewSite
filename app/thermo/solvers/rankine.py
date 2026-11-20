from __future__ import annotations

from dataclasses import dataclass

from CoolProp.CoolProp import PropsSI

from app.thermo.props import (
    StatePoint,
    from_ph,
    from_ps,
    from_pt,
    resolve,
    sat_state,
    validate,
)
from app.thermo.solvers.base import CycleResult, register_solver


@dataclass
class Event:
    """Something that happens at a pressure on the way down through the turbine."""

    pressure: float
    kind: str  # "reheat" | "extraction"
    temperature: float | None = None


@register_solver("rankine")
def solve_rankine(fluid_name: str, params: dict) -> CycleResult:
    """The Rankine cycle in the shapes an engineering board exam asks for.

    One machine described by the events on its expansion path, sorted by pressure:

        plain           nothing between the boiler and the condenser
        reheat          one or more reheats
        regeneration    one or more extraction points feeding open feedwater heaters
        both            any combination, and an extraction may sit at a reheat pressure

    Everything is per kilogram of steam through the boiler, in SI base units: Pa, K,
    J/kg. A regenerative cycle has no single-formula efficiency, because a fraction of
    the steam leaves the turbine early and the legs no longer carry the same mass, so
    the mass flow is carried through every total.

    `processes` and `descriptions` are indexed per leg: entry i is the path from
    states[i] to states[i+1], and the last closes the loop.
    """
    try:
        return _solve(fluid_name, params)
    except ValueError as problem:
        return CycleResult(cycle="rankine", states=[], solved=False, missing=[str(problem)])


def _solve(fluid_name: str, params: dict) -> CycleResult:
    fluid = resolve(fluid_name)

    P_boiler = _required(params, "P_boiler")
    P_cond = _required(params, "P_cond")
    eta_turbine = _efficiency(params.get("eta_turbine"), "eta_turbine")
    eta_pump = _efficiency(params.get("eta_pump"), "eta_pump")
    subcooling = float(params.get("subcooling", 0.0))
    mass_flow = _positive(params.get("mass_flow"), "mass_flow")
    power_output = _positive(params.get("power_output"), "power_output")

    if P_cond >= P_boiler:
        raise ValueError("condenser pressure must be below boiler pressure")
    if subcooling < 0:
        raise ValueError("subcooling must not be negative")
    validate(fluid, P=P_boiler, P_cond=P_cond)

    P_crit = PropsSI("pcrit", fluid)

    # ---- the turbine inlet ----------------------------------------------
    # Either a temperature or a dryness fraction. A supercritical boiler has no
    # saturation temperature, so T_sat cannot be read there; below it, live steam colder
    # than saturation is not steam.
    T_turbine = params.get("T_turbine")
    x_turbine = params.get("x_turbine")
    if T_turbine is None and x_turbine is None:
        raise ValueError("give T_turbine or x_turbine")
    if x_turbine is not None:
        x_turbine = float(x_turbine)
        if not 0.0 <= x_turbine <= 1.0:
            raise ValueError("x_turbine is a dryness fraction between 0 and 1")
        inlet = sat_state(fluid, P_boiler, x_turbine)
    else:
        T_turbine = float(T_turbine)
        validate(fluid, T=T_turbine)
        if P_boiler < P_crit:
            t_sat = PropsSI("T", "P", P_boiler, "Q", 1, fluid)
            if T_turbine <= t_sat:
                raise ValueError(
                    f"turbine inlet {T_turbine:.2f} K is below the saturation temperature "
                    f"at the boiler pressure ({t_sat:.2f} K), so the steam would be wet at "
                    "inlet. Go above saturation, or give x_turbine"
                )
        inlet = from_pt(fluid, P_boiler, T_turbine)

    events = _events(params, P_cond, P_boiler)

    # ---- the steam path, and the mass leaving it ------------------------
    states: list[StatePoint] = []
    processes: list[str] = []
    descriptions: list[str] = []

    extractions: dict[float, StatePoint] = {}
    heated: dict[float, StatePoint] = {}

    current = inlet
    # The mass in the turbine starts as the whole kilogram and loses an extraction's
    # fraction at each point, so it is not known until the heaters are balanced. The
    # geometry is collected first and the weighting applied after.
    for event in events:
        expanded = _expand(fluid, current, event.pressure, eta_turbine)
        if event.kind == "extraction":
            extractions[event.pressure] = expanded
            current = expanded
        else:
            reheated = from_pt(fluid, event.pressure, event.temperature)
            heated[event.pressure] = reheated
            current = reheated
    exhaust = _expand(fluid, current, P_cond, eta_turbine)

    # ---- the condensate path -------------------------------------------
    condensate = sat_state(fluid, P_cond, 0.0)
    if subcooling:
        condensate = from_pt(fluid, P_cond, condensate.T - subcooling)

    # Heaters ascend from the condenser: pump up to the extraction pressure, mix to
    # saturated liquid there, pump again. The last pump reaches the boiler.
    heater_out = {p: sat_state(fluid, p, 0.0) for p in extractions}
    pumps_in: dict[float, StatePoint] = {}
    previous = condensate
    for pressure in sorted(extractions):
        pump_out = _pump(fluid, previous, pressure, eta_pump)
        pumps_in[pressure] = pump_out
        previous = heater_out[pressure]
    boiler_pump = _pump(fluid, previous, P_boiler, eta_pump)

    # ---- the mass balance ----------------------------------------------
    # Every heater's hot and cold enthalpies are fixed points, so this walks down the
    # pressures once. y_j is the mass leaving heater j, which is one kilogram less every
    # fraction already bled above it.
    fractions: dict[float, float] = {}
    remaining = 1.0
    for pressure in sorted(extractions, reverse=True):
        cold = pumps_in[pressure]
        hot = extractions[pressure]
        out = heater_out[pressure]
        if hot.h - cold.h <= 0:
            raise ValueError("an extraction is not hot enough to heat the feedwater")
        fraction = remaining * (out.h - cold.h) / (hot.h - cold.h)
        if not 0.0 < fraction < 1.0:
            raise ValueError(
                f"the extraction at {pressure:.0f} Pa gives a bleed fraction of "
                f"{fraction:.3f}, outside 0 and 1, so the heater cannot balance"
            )
        fractions[pressure] = fraction
        remaining -= fraction

    # ---- work and heat, each weighted by the mass in its stage -----------
    turbine_work = 0.0
    heat_added = inlet.h - boiler_pump.h  # the boiler heats the whole kilogram
    mass = 1.0
    current = inlet
    for event in events:
        expanded = _expand(fluid, current, event.pressure, eta_turbine)
        turbine_work += mass * (current.h - expanded.h)
        if event.kind == "extraction":
            mass -= fractions[event.pressure]
            current = expanded
        else:
            reheated = heated[event.pressure]
            # The reheater heats from the exhaust of the stage just expanded, which is
            # `expanded`, not the state before it.
            heat_added += mass * (reheated.h - expanded.h)
            current = reheated
    turbine_work += mass * (current.h - exhaust.h)

    pump_work = remaining * (pumps_in[min(pumps_in)].h - condensate.h) if pumps_in else 0.0
    ascending = sorted(pumps_in)
    for index, pressure in enumerate(ascending[1:], start=1):
        carried = 1.0 - sum(fractions[p] for p in ascending[:index])
        pump_work += carried * (pumps_in[pressure].h - heater_out[ascending[index - 1]].h)
    pump_work += (boiler_pump.h - previous.h)

    net_work = turbine_work - pump_work
    heat_rejected = remaining * (exhaust.h - condensate.h)
    efficiency = net_work / heat_added if heat_added > 0 else None

    # ---- assemble the closed loop, in the order the diagram draws it -----
    # Entry i of `processes` is the leg from states[i] to states[i+1]. The label for a
    # state belongs on the leg that arrives at it, so the condenser outlet's name sits on
    # the closing leg at the end rather than on a leg of its own at the start.
    states.append(condensate)

    for pressure in ascending:
        states.append(pumps_in[pressure])
        processes.append("isentropic")
        descriptions.append(f"pump to {_mpa(pressure)}")
        states.append(heater_out[pressure])
        processes.append("isobaric")
        descriptions.append("open feedwater heater")
    states.append(boiler_pump)
    processes.append("isentropic")
    descriptions.append("boiler feed pump")
    states.append(inlet)
    processes.append("isobaric")
    descriptions.append("boiler outlet")

    # Walked in the same order the masses were accumulated in, from the same states, so
    # the drawn loop and the arithmetic cannot disagree.
    drawn = inlet
    for event in events:
        if event.kind == "extraction":
            drawn = extractions[event.pressure]
            states.append(drawn)
            processes.append("isentropic")
            descriptions.append(f"turbine, to extraction at {_mpa(event.pressure)}")
        else:
            drawn = _expand(fluid, drawn, event.pressure, eta_turbine)
            states.append(drawn)
            processes.append("isentropic")
            descriptions.append(f"turbine, to reheater at {_mpa(event.pressure)}")
            drawn = heated[event.pressure]
            states.append(drawn)
            processes.append("isobaric")
            descriptions.append("reheater")
    states.append(exhaust)
    processes.append("isentropic")
    descriptions.append("turbine, to condenser")

    processes.append("isobaric")
    descriptions.append("condenser")

    extras = _extras(fractions, remaining, mass_flow, power_output, net_work,
                      eta_turbine, eta_pump, heat_rejected)

    return CycleResult(
        cycle="rankine",
        states=states,
        solved=True,
        missing=[],
        processes=processes,
        descriptions=descriptions,
        fluid=fluid_name,
        ideal_gas=False,
        net_work=net_work,
        heat_added=heat_added,
        turbine_work=turbine_work,
        pump_work=pump_work,
        efficiency=efficiency,
        extras=extras,
        branches=[
            {
                "from": 0,
                "to": 0,
                "pressure": pressure,
                "process": "isobaric",
                "description": (
                    f"bled steam, {fractions[pressure] * 100:.1f}% to the feedwater "
                    f"heater at {_mpa(pressure)}"
                ),
                "points": _bleed_path(fluid, extractions[pressure], heater_out[pressure]),
            }
            for pressure in ascending
        ],
    )


# ---- helpers ---------------------------------------------------------------


def _required(params: dict, name: str) -> float:
    if name not in params:
        raise ValueError(name)
    return float(params[name])


def _positive(value, name: str) -> float | None:
    if value is None:
        return None
    number = float(value)
    if number <= 0:
        raise ValueError(f"{name} must be positive")
    return number


def _efficiency(value, name: str) -> float:
    if value is None:
        return 1.0
    number = float(value)
    if not 0.0 < number <= 1.0:
        raise ValueError(f"{name} is a fraction between 0 and 1")
    return number


def _mpa(pressure: float) -> str:
    return f"{pressure / 1e6:.4g} MPa"


def _events(params: dict, P_cond: float, P_boiler: float) -> list[Event]:
    """Reheats and extractions, gathered into one list sorted by descending pressure."""
    events: list[Event] = []

    for item in params.get("reheats") or []:
        if isinstance(item, dict):
            events.append(Event(float(item["P"]), "reheat", float(item["T"])))
        else:
            events.append(Event(float(item[0]), "reheat", float(item[1])))
    if params.get("T_reheat") is not None:
        pressure = params.get("P_reheat")
        if pressure is None:
            # Several reheats stack sensibly by fixed fractions of the boiler pressure.
            used = sum(1 for event in events if event.kind == "reheat")
            pressure = P_boiler / (4 * (1 + used))
        events.append(Event(float(pressure), "reheat", float(params["T_reheat"])))

    for pressure in params.get("extractions") or []:
        events.append(Event(float(pressure), "extraction"))
    if params.get("P_bleed") is not None:
        events.append(Event(float(params["P_bleed"]), "extraction"))
    elif params.get("regeneration"):
        events.append(Event(P_boiler / 5, "extraction"))

    # Grouped by pressure, because an extraction and a reheat may share one: cold reheat
    # is bled at the reheat pressure, and the steam that stays in the turbine is then
    # reheated there. At a shared pressure the extraction comes first.
    grouped: dict[float, list[Event]] = {}
    for event in events:
        if not P_cond < event.pressure < P_boiler:
            raise ValueError(
                f"{event.kind} pressure {event.pressure:.0f} Pa must sit between the "
                f"condenser ({P_cond:.0f}) and the boiler ({P_boiler:.0f})"
            )
        grouped.setdefault(event.pressure, []).append(event)

    ordered: list[Event] = []
    for pressure in sorted(grouped, reverse=True):
        group = grouped[pressure]
        # The same kind at the same pressure is one device, however it arrived: the
        # client sends the first extraction as P_bleed and again in the list, and those
        # are the same heater. Only a genuine conflict is worth refusing.
        extractions: dict[float, Event] = {}
        reheats: dict[float, Event] = {}
        for event in group:
            bucket = extractions if event.kind == "extraction" else reheats
            bucket[event.pressure] = event
        ordered.extend(extractions.values())
        ordered.extend(reheats.values())
    return ordered


def _expand(fluid: str, state: StatePoint, pressure: float, eta: float) -> StatePoint:
    """Isentropic expansion, derated by the turbine's efficiency."""
    ideal = from_ps(fluid, pressure, state.s)
    if eta >= 1.0:
        return ideal
    return _between(state, ideal, eta)


def _pump(fluid: str, state: StatePoint, pressure: float, eta: float) -> StatePoint:
    """Isentropic compression. A real pump needs more work than the ideal one."""
    ideal = from_ps(fluid, pressure, state.s)
    if eta >= 1.0:
        return ideal
    return _between(state, ideal, 1.0 / eta)


def _between(start: StatePoint, ideal: StatePoint, fraction: float) -> StatePoint:
    return StatePoint(
        P=ideal.P,
        T=ideal.T,
        h=start.h + (ideal.h - start.h) * fraction,
        s=start.s + (ideal.s - start.s) * fraction,
        v=ideal.v,
    )


def _extras(fractions, remaining, mass_flow, power_output, net_work,
            eta_turbine, eta_pump, heat_rejected) -> dict:
    extras: dict = {
        "extractions": len(fractions),
        # Rejected at the condenser, per kilogram through the boiler. A regenerative
        # cycle rejects less there because some heat was recovered in the heaters.
        "heat rejected": f"{heat_rejected / 1000:.1f} kJ/kg",
    }
    if fractions:
        extras["bleed fraction"] = round(sum(fractions.values()), 4)
        for pressure in sorted(fractions, reverse=True):
            extras[f"bled at {_mpa(pressure)}"] = round(fractions[pressure], 4)
        extras["mass to condenser"] = f"{round(remaining, 4)} kg"
    if eta_turbine < 1:
        extras["turbine efficiency"] = eta_turbine
    if eta_pump < 1:
        extras["pump efficiency"] = eta_pump
    if mass_flow:
        extras["mass flow"] = f"{mass_flow:.4g} kg/s"
        extras["net power"] = f"{mass_flow * net_work / 1e6:.4g} MW"
    if power_output:
        extras["power output"] = f"{power_output / 1e3:.4g} MW"
        extras["mass flow needed"] = f"{power_output / net_work:.4g} kg/s"
    return extras


def _bleed_path(
    fluid: str, extraction: StatePoint, heater_out: StatePoint, n: int = 32
) -> list[dict]:
    """The bleed, sampled at constant pressure.

    From the extraction state the steam gives up heat at the extraction pressure until it
    reaches saturation, then condenses to saturated liquid there. Interpolating in
    enthalpy covers both sides of the dome, which is why it is one loop and not two.
    """
    points = []
    for index in range(n + 1):
        enthalpy = extraction.h + (heater_out.h - extraction.h) * (index / n)
        try:
            state = from_ph(fluid, extraction.P, enthalpy)
        except (ValueError, RuntimeError):
            continue
        points.append({"P": state.P, "T": state.T, "h": state.h, "s": state.s, "v": state.v})
    return points
