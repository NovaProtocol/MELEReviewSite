from __future__ import annotations

from dataclasses import dataclass

from CoolProp.CoolProp import PropsSI

FLUIDS = {
    "water": "Water",
    "r134a": "R134a",
    "r410a": "R410a",
    "air": "Air",
}


@dataclass(frozen=True)
class StatePoint:
    P: float
    T: float
    h: float
    s: float
    v: float


def resolve(name: str) -> str:
    if name not in FLUIDS:
        raise ValueError(f"unknown fluid: {name}")
    return FLUIDS[name]


def validate(fluid: str, **kwargs) -> None:
    """Raise ValueError if a P/T input is outside the fluid's valid range."""
    bounds = {"P": ("pmin", "pmax"), "T": ("Tmin", "Tmax")}
    for prop, value in kwargs.items():
        if value is None or prop not in bounds:
            continue
        lo = PropsSI(bounds[prop][0], fluid)
        hi = PropsSI(bounds[prop][1], fluid)
        if not (lo <= value <= hi):
            raise ValueError(
                f"{prop}={value} is outside the {fluid} valid range [{lo:.2f}, {hi:.2f}]"
            )


def from_pt(fluid: str, P: float, T: float) -> StatePoint:
    h = PropsSI("H", "P", P, "T", T, fluid)
    s = PropsSI("S", "P", P, "T", T, fluid)
    v = 1.0 / PropsSI("D", "P", P, "T", T, fluid)
    return StatePoint(P=P, T=T, h=h, s=s, v=v)


def from_ps(fluid: str, P: float, s: float) -> StatePoint:
    """State at (P, s), handles two-phase and superheated automatically."""
    T = PropsSI("T", "P", P, "S", s, fluid)
    h = PropsSI("H", "P", P, "S", s, fluid)
    v = 1.0 / PropsSI("D", "P", P, "S", s, fluid)
    return StatePoint(P=P, T=T, h=h, s=s, v=v)


def from_ph(fluid: str, P: float, h: float) -> StatePoint:
    T = PropsSI("T", "P", P, "H", h, fluid)
    s = PropsSI("S", "P", P, "H", h, fluid)
    v = 1.0 / PropsSI("D", "P", P, "H", h, fluid)
    return StatePoint(P=P, T=T, h=h, s=s, v=v)


def from_pv(fluid: str, P: float, v: float) -> StatePoint:
    rho = 1.0 / v
    T = PropsSI("T", "P", P, "D", rho, fluid)
    h = PropsSI("H", "P", P, "D", rho, fluid)
    s = PropsSI("S", "P", P, "D", rho, fluid)
    return StatePoint(P=P, T=T, h=h, s=s, v=v)


def from_ts(fluid: str, T: float, s: float) -> StatePoint:
    P = PropsSI("P", "T", T, "S", s, fluid)
    h = PropsSI("H", "T", T, "S", s, fluid)
    v = 1.0 / PropsSI("D", "T", T, "S", s, fluid)
    return StatePoint(P=P, T=T, h=h, s=s, v=v)


def from_th(fluid: str, T: float, h: float) -> StatePoint:
    P = PropsSI("P", "T", T, "H", h, fluid)
    s = PropsSI("S", "T", T, "H", h, fluid)
    v = 1.0 / PropsSI("D", "T", T, "H", h, fluid)
    return StatePoint(P=P, T=T, h=h, s=s, v=v)


def from_tv(fluid: str, T: float, v: float) -> StatePoint:
    rho = 1.0 / v
    P = PropsSI("P", "T", T, "D", rho, fluid)
    h = PropsSI("H", "T", T, "D", rho, fluid)
    s = PropsSI("S", "T", T, "D", rho, fluid)
    return StatePoint(P=P, T=T, h=h, s=s, v=v)


def sat_state(fluid: str, P: float, quality: float) -> StatePoint:
    """Saturated liquid (q=0) or vapor (q=1) state at pressure P."""
    T = PropsSI("T", "P", P, "Q", quality, fluid)
    h = PropsSI("H", "P", P, "Q", quality, fluid)
    s = PropsSI("S", "P", P, "Q", quality, fluid)
    v = 1.0 / PropsSI("D", "P", P, "Q", quality, fluid)
    return StatePoint(P=P, T=T, h=h, s=s, v=v)


def sat_props(fluid: str, P: float) -> dict:
    """Saturated liquid/vapor properties at pressure P."""
    return {
        "T": PropsSI("T", "P", P, "Q", 0, fluid),
        "h_f": PropsSI("H", "P", P, "Q", 0, fluid),
        "h_g": PropsSI("H", "P", P, "Q", 1, fluid),
        "s_f": PropsSI("S", "P", P, "Q", 0, fluid),
        "s_g": PropsSI("S", "P", P, "Q", 1, fluid),
        "v_f": 1.0 / PropsSI("D", "P", P, "Q", 0, fluid),
        "v_g": 1.0 / PropsSI("D", "P", P, "Q", 1, fluid),
    }


def state_from_props(fluid: str, props: dict) -> StatePoint:
    """Compute a full state from any two of P, T, h, s, v."""
    present = {k for k in ("P", "T", "h", "s", "v") if props.get(k) is not None}
    if len(present) < 2:
        raise ValueError(f"need at least 2 of P, T, h, s, v; have {sorted(present)}")

    solvers = {
        frozenset({"P", "T"}): lambda: from_pt(fluid, props["P"], props["T"]),
        frozenset({"P", "s"}): lambda: from_ps(fluid, props["P"], props["s"]),
        frozenset({"P", "h"}): lambda: from_ph(fluid, props["P"], props["h"]),
        frozenset({"P", "v"}): lambda: from_pv(fluid, props["P"], props["v"]),
        frozenset({"T", "s"}): lambda: from_ts(fluid, props["T"], props["s"]),
        frozenset({"T", "h"}): lambda: from_th(fluid, props["T"], props["h"]),
        frozenset({"T", "v"}): lambda: from_tv(fluid, props["T"], props["v"]),
    }
    for pair, solver in solvers.items():
        if pair <= present:
            return solver()
    raise ValueError(f"unsupported property combination {sorted(present)}")
