from __future__ import annotations

import math

import numpy as np
from CoolProp.CoolProp import PropsSI

from api.thermo.props import resolve, from_ps, from_ph, from_pt, from_pv
from api.thermo.solvers.base import CycleResult
from api.thermo.solvers.ideal_gas import R, GAMMA, CP, T_REF, P_REF, air_state

SAMPLES = 48

PROPERTY_LABELS = {
    "T": "Temperature (K)",
    "P": "Pressure (Pa)",
    "v": "Specific Volume (m\u00b3/kg)",
    "h": "Enthalpy (J/kg)",
    "s": "Entropy (J/kg\u00b7K)",
}


def _finite(state) -> bool:
    return all(
        isinstance(getattr(state, k, None), (int, float)) and math.isfinite(getattr(state, k))
        for k in ("P", "T", "h", "s", "v")
    )


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def sample_ideal_gas(a, b, process: str, n: int = SAMPLES) -> list:
    pts = []
    for i in range(n + 1):
        t = i / n
        if process == "isothermal":
            T = a.T
            v = _lerp(a.v, b.v, t)
            P = R * T / v
        elif process == "isentropic":
            v = _lerp(a.v, b.v, t)
            P = a.P * (a.v / v) ** GAMMA
            T = P * v / R
        elif process == "isobaric":
            P = a.P
            T = _lerp(a.T, b.T, t)
            v = R * T / P
        elif process == "isochoric":
            v = a.v
            T = _lerp(a.T, b.T, t)
            P = R * T / v
        elif process == "isenthalpic":
            T = a.T
            v = _lerp(a.v, b.v, t)
            P = R * T / v
        else:
            P = _lerp(a.P, b.P, t)
            T = _lerp(a.T, b.T, t)
            v = R * T / P
        pts.append(air_state(P, T))
    return pts


def _try(fn):
    try:
        st = fn()
        return st if _finite(st) else None
    except (ValueError, RuntimeError):
        return None


def sample_fluid(fluid: str, a, b, process: str, n: int = SAMPLES) -> list:
    pts = []
    t_sat = PropsSI("T", "P", a.P, "Q", 0, fluid)
    for i in range(n + 1):
        t = i / n
        if process == "isentropic":
            st = _try(lambda: from_ps(fluid, _lerp(a.P, b.P, t), a.s))
        elif process == "isenthalpic":
            st = _try(lambda: from_ph(fluid, _lerp(a.P, b.P, t), a.h))
        elif process == "isobaric":
            if abs(b.T - a.T) > 1.0:
                T = _lerp(a.T, b.T, t)
                if abs(T - t_sat) < 0.5:
                    st = None  # skip two-phase boundary point
                else:
                    st = _try(lambda: from_pt(fluid, a.P, T))
            else:  # constant T (e.g. condenser two-phase): step entropy
                st = _try(lambda: from_ps(fluid, a.P, _lerp(a.s, b.s, t)))
        elif process == "isothermal":
            st = _try(lambda: from_pt(fluid, _lerp(a.P, b.P, t), a.T))
        elif process == "isochoric":
            st = _try(lambda: from_pv(fluid, _lerp(a.P, b.P, t), a.v))
        else:
            st = _try(lambda: from_pt(fluid, _lerp(a.P, b.P, t), _lerp(a.T, b.T, t)))
        if st is not None:
            pts.append(st)
    return pts


def _load_fluid(result: CycleResult):
    if result.fluid and not result.ideal_gas:
        return resolve(result.fluid)
    return None


def _sample_segments(result: CycleResult):
    states = result.states
    processes = result.processes or [""] * len(states)
    n = len(states)
    fluid = _load_fluid(result)

    segments = []
    for i in range(n):
        a = states[i]
        b = states[(i + 1) % n]
        proc = processes[i] if i < len(processes) else ""
        if result.ideal_gas:
            seg = sample_ideal_gas(a, b, proc)
        elif fluid is not None:
            seg = sample_fluid(fluid, a, b, proc)
        else:
            seg = [a, b]
        seg = [s for s in seg if _finite(s)]
        if len(seg) < 2:
            seg = [a, b]
        segments.append(seg)
    return segments


def segment_data(result: CycleResult) -> list[dict]:
    processes = result.processes or [""] * len(result.states)
    out = []
    for i, seg in enumerate(_sample_segments(result)):
        out.append(
            {
                "process": processes[i] if i < len(processes) else "",
                "points": [
                    {"P": s.P, "T": s.T, "h": s.h, "s": s.s, "v": s.v}
                    for s in seg
                ],
            }
        )
    return out


def _dome(fluid: str) -> dict:
    try:
        p_crit = PropsSI("pcrit", fluid)
        p_triple = max(PropsSI("ptriple", fluid), 1.0)
    except Exception:
        return None
    p_sat = np.logspace(np.log10(p_triple), np.log10(0.98 * p_crit), 200)
    liquid_x, liquid_y, vapor_x, vapor_y = [], [], [], []
    quality = {0.2: [], 0.4: [], 0.6: [], 0.8: []}
    for P in p_sat:
        T = PropsSI("T", "P", P, "Q", 0, fluid)
        sf = PropsSI("S", "P", P, "Q", 0, fluid)
        sg = PropsSI("S", "P", P, "Q", 1, fluid)
        liquid_x.append(sf)
        liquid_y.append(T)
        vapor_x.append(sg)
        vapor_y.append(T)
        for q in quality:
            quality[q].append(sf + q * (sg - sf))
    return {
        "liquid_x": liquid_x,
        "liquid_y": liquid_y,
        "vapor_x": vapor_x,
        "vapor_y": vapor_y,
        "quality": [{"q": q, "x": xs, "y": liquid_y[:]} for q, xs in quality.items()],
    }


def dome_data(result: CycleResult) -> dict | None:
    fluid = _load_fluid(result)
    return _dome(fluid) if fluid is not None else None


def plot_data(result: CycleResult, x_prop: str, y_prop: str) -> dict:
    processes = result.processes or [""] * len(result.states)
    segments = []
    for i, seg in enumerate(_sample_segments(result)):
        segments.append(
            {
                "process": processes[i] if i < len(processes) else "",
                "x": [getattr(s, x_prop) for s in seg],
                "y": [getattr(s, y_prop) for s in seg],
            }
        )
    states = [
        {"x": getattr(s, x_prop), "y": getattr(s, y_prop), "label": str(i + 1)}
        for i, s in enumerate(result.states)
        if _finite(s)
    ]
    dome = None
    if x_prop == "s" and y_prop == "T":
        fluid = _load_fluid(result)
        if fluid is not None:
            dome = _dome(fluid)
    return {"segments": segments, "states": states, "dome": dome}
