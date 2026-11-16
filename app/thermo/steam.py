"""Steam tables, read like a book.

Water properties from CoolProp, arranged the way an MELE candidate reads them:
saturation by temperature, saturation by pressure, and a state lookup for
whatever two inputs the problem gives. Units are the ones the tables use:
degrees Celsius, megapascals, kilojoules per kilogram.
"""

from __future__ import annotations

from CoolProp.CoolProp import PropsSI

FLUID = "Water"
# CoolProp returns joules; a printed steam table is in kilojoules.
_KJ = 1e-3
T_CRIT = PropsSI("Tcrit", FLUID)
P_CRIT = PropsSI("pcrit", FLUID)
P_TRIPLE = PropsSI("ptriple", FLUID)
T_TRIPLE = PropsSI("Ttriple", FLUID)

# What a table column is called and how to get it at a saturation point.
_COLUMNS = (
    ("v_f", "vf", "D", True),
    ("v_g", "vg", "D", False),
    ("u_f", "uf", "U", True),
    ("u_g", "ug", "U", False),
    ("h_f", "hf", "H", True),
    ("h_g", "hg", "H", False),
    ("s_f", "sf", "S", True),
    ("s_g", "sg", "S", False),
)


def _value(prop: str, key: str, value: float, liquid: bool) -> float:
    return float(PropsSI(prop, key, value, "Q", 0 if liquid else 1, FLUID))


def _saturated(key: str, value: float) -> dict:
    """A row of the saturation table, at a temperature (K) or a pressure (Pa).

    CoolProp works in SI; a steam table is printed in kJ, so the energy columns
    are converted on the way out and the units are what the page shows.
    """
    row: dict[str, float] = {}
    for name, _short, prop, liquid in _COLUMNS:
        raw = _value(prop, key, value, liquid)
        if prop == "D":
            row[name] = 1.0 / raw
        elif prop in {"U", "H", "S"}:
            row[name] = raw * _KJ
        else:
            row[name] = raw
    row["P_sat"] = float(PropsSI("P", key, value, "Q", 0, FLUID)) / 1e6
    row["T_sat"] = float(PropsSI("T", key, value, "Q", 0, FLUID)) - 273.15
    row["h_fg"] = row["h_g"] - row["h_f"]
    row["u_fg"] = row["u_g"] - row["u_f"]
    row["s_fg"] = row["s_g"] - row["s_f"]
    return row


def saturation_by_temperature(celsius: float) -> dict:
    kelvin = celsius + 273.15
    if not (T_TRIPLE - 0.01 <= kelvin < T_CRIT):
        raise ValueError(
            f"Temperature must be between {T_TRIPLE - 273.15:.2f} and {T_CRIT - 273.15:.2f} C"
        )
    return _saturated("T", kelvin)


def saturation_by_pressure(megapascal: float) -> dict:
    pascal = megapascal * 1e6
    if not (P_TRIPLE <= pascal < P_CRIT):
        raise ValueError(
            f"Pressure must be between {P_TRIPLE / 1000:.4g} kPa and {P_CRIT / 1e6:.3f} MPa"
        )
    return _saturated("P", pascal)


def saturation_table(basis: str, start: float, stop: float, count: int) -> tuple[list[dict], bool]:
    """Rows between two ends, inclusive, in the order a table is printed.

    The flags say whether the table was cut short, at the critical point above or
    the triple point below, so the page can say what it did.
    """
    count = max(2, min(int(count), 200))
    if basis not in {"temperature", "pressure"}:
        raise ValueError("Choose temperature or pressure")
    if start == stop:
        raise ValueError("The two ends must differ")
    low, high = sorted((start, stop))
    # A book table starts at the triple point; asking for 0 C is asking for the
    # start of the liquid range, not for an error.
    floor = T_TRIPLE - 273.15 + 1e-3 if basis == "temperature" else P_TRIPLE / 1e6
    clamped = low < floor
    if clamped:
        low = floor
    if low >= high:
        raise ValueError("That range has no saturated states below the critical point")
    step = (high - low) / (count - 1)
    rows = []
    truncated = False
    for index in range(count):
        value = low + step * index
        # The top of the table is the critical point, which has no liquid/vapour
        # split, so a row there would be meaningless.
        if basis == "temperature" and value + 273.15 >= T_CRIT - 0.05:
            truncated = index < count
            break
        if basis == "pressure" and value * 1e6 >= P_CRIT - 1:
            truncated = index < count
            break
        row = (
            saturation_by_temperature(value)
            if basis == "temperature"
            else saturation_by_pressure(value)
        )
        row["input"] = value
        rows.append(row)
    if not rows:
        raise ValueError("That range has no saturated states below the critical point")
    return rows, truncated and len(rows) < count, clamped


def _phase(pressure: float, temperature: float) -> tuple[str, float | None]:
    """What the substance is, judged against the saturation temperature."""
    if pressure >= P_CRIT or temperature >= T_CRIT:
        return "supercritical", None
    t_sat = float(PropsSI("T", "P", pressure, "Q", 0, FLUID))
    if temperature < t_sat - 0.05:
        return "compressed liquid", None
    if temperature > t_sat + 0.05:
        return "superheated vapour", None
    # P and T are the saturation pair, which fixes no quality on its own.
    return "at saturation (give quality for a mixture)", 0.0


def _point(pressure: float, temperature: float) -> dict:
    """A single-phase state from a pressure (Pa) and a temperature (K)."""
    return {
        "P": pressure / 1e6,
        "T": temperature - 273.15,
        "v": 1.0 / float(PropsSI("D", "P", pressure, "T", temperature, FLUID)),
        "u": float(PropsSI("U", "P", pressure, "T", temperature, FLUID)) * _KJ,
        "h": float(PropsSI("H", "P", pressure, "T", temperature, FLUID)) * _KJ,
        "s": float(PropsSI("S", "P", pressure, "T", temperature, FLUID)) * _KJ,
    }


def _mixture(key: str, value: float, quality: float) -> dict:
    """A saturated mixture, taken from the saturation line rather than from a
    (P, T) pair, which is ambiguous once the two sit exactly on that line."""
    return {
        "P": float(PropsSI("P", key, value, "Q", quality, FLUID)) / 1e6,
        "T": float(PropsSI("T", key, value, "Q", quality, FLUID)) - 273.15,
        "v": 1.0 / float(PropsSI("D", key, value, "Q", quality, FLUID)),
        "u": float(PropsSI("U", key, value, "Q", quality, FLUID)) * _KJ,
        "h": float(PropsSI("H", key, value, "Q", quality, FLUID)) * _KJ,
        "s": float(PropsSI("S", key, value, "Q", quality, FLUID)) * _KJ,
        "x": quality,
    }


def state(
    pressure: float | None = None,
    temperature: float | None = None,
    quality: float | None = None,
) -> dict:
    """A state from any two of pressure (MPa), temperature (C) and quality.

    Quality only means anything at saturation, so it is applied at the saturation
    pressure or temperature it was given with.
    """
    if quality is not None and not (0.0 <= quality <= 1.0):
        raise ValueError("Quality must be between 0 and 1")

    if pressure is not None and quality is not None:
        pascal = pressure * 1e6
        if not (P_TRIPLE <= pascal < P_CRIT):
            raise ValueError("Pressure is outside the saturated range")
        result = _mixture("P", pascal, quality)
        result["phase"] = (
            "saturated liquid"
            if quality == 0
            else ("saturated vapour" if quality == 1 else "saturated mixture")
        )
        return result

    if temperature is not None and quality is not None:
        kelvin = temperature + 273.15
        if not (T_TRIPLE <= kelvin < T_CRIT):
            raise ValueError("Temperature is outside the saturated range")
        result = _mixture("T", kelvin, quality)
        result["phase"] = (
            "saturated liquid"
            if quality == 0
            else ("saturated vapour" if quality == 1 else "saturated mixture")
        )
        return result

    if pressure is None or temperature is None:
        raise ValueError("Give pressure and temperature, or one of them with quality")

    pascal = pressure * 1e6
    kelvin = temperature + 273.15
    if pascal <= 0 or kelvin <= 0:
        raise ValueError("Pressure and temperature must be positive")
    if pascal > 1e9 or kelvin > 2273.15:
        raise ValueError("That is beyond the range of the tables")

    phase, _ = _phase(pascal, kelvin)
    result = _point(pascal, kelvin)
    result["phase"] = phase
    return result


# Pairs the chart can draw: what goes on each axis.
AXES = {
    "t-s": ("s", "T"),
    "h-s": ("s", "h"),
    "p-h": ("h", "P"),
}


def dome() -> dict[str, dict[str, list[float]]]:
    """The saturation dome, in every pair the chart offers.

    One pass over the saturation line; each pair picks its two coordinates out of
    the same numbers, so the three charts always agree.
    """
    import numpy as np

    pressures = np.logspace(np.log10(P_TRIPLE * 1.01), np.log10(0.999 * P_CRIT), 160)
    liquid = {name: [] for name in ("T", "P", "h", "s")}
    vapour = {name: [] for name in ("T", "P", "h", "s")}
    for pascal in pressures:
        for target, quality in ((liquid, 0), (vapour, 1)):
            # Same units as a state point, or the point would not land on the dome.
            target["T"].append(float(PropsSI("T", "P", pascal, "Q", quality, FLUID)) - 273.15)
            target["P"].append(float(pascal) / 1e6)
            target["h"].append(float(PropsSI("H", "P", pascal, "Q", quality, FLUID)) * _KJ)
            target["s"].append(float(PropsSI("S", "P", pascal, "Q", quality, FLUID)) * _KJ)

    out: dict[str, dict[str, list[float]]] = {}
    for name, (x_prop, y_prop) in AXES.items():
        out[name] = {
            "liquid_x": liquid[x_prop],
            "liquid_y": liquid[y_prop],
            "vapour_x": vapour[x_prop],
            "vapour_y": vapour[y_prop],
        }
    return out


def chart_point(result: dict) -> dict[str, dict[str, float]]:
    points: dict[str, dict[str, float]] = {}
    for name, (x_prop, y_prop) in AXES.items():
        points[name] = {"x": result[x_prop], "y": result[y_prop]}
    return points
