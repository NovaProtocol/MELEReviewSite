"""Moist air, from the IAPWS formulation of water's saturation curve.

Steam properties live in app/thermo/steam.py. What is missing there, and what this
supplies, are the psychrometric quantities: given a dry-bulb temperature and a
relative humidity, the humidity ratio, enthalpy, dew point and wet bulb.

The saturation pressure comes from IAPWS-IF97 rather than a printed fit, so the
humidity ratio here agrees with the steam table a reader checks it against. Nothing
is cached: the properties of water do not change and the arithmetic is cheap.
"""

from __future__ import annotations

from iapws import IAPWS97


class PropertyError(ValueError):
    """A request outside the range the formulation covers."""


def saturation_pressure_pa(temperature_c: float) -> float:
    """Saturation pressure of water vapour."""
    kelvin = max(temperature_c + 273.15, 273.16)
    state = IAPWS97(T=kelvin, x=0)
    return state.P * 1e6


def psychrometric(
    dry_bulb_c: float,
    relative_humidity: float,
    pressure_kpa: float = 101.325,
) -> dict:
    """Moist air at a dry-bulb temperature and a relative humidity.

    ASHRAE formulations: humidity ratio from the vapour partial pressure, enthalpy
    from the dry air and the vapour it carries, and the dew point from inverting the
    saturation curve.
    """
    if not 0.0 <= relative_humidity <= 1.0:
        raise PropertyError("Relative humidity is a fraction between 0 and 1")
    if pressure_kpa <= 0:
        raise PropertyError("Pressure must be above zero")

    saturation = saturation_pressure_pa(dry_bulb_c)
    vapour_pa = relative_humidity * saturation
    total_pa = pressure_kpa * 1000.0
    if vapour_pa >= total_pa:
        raise PropertyError("That much vapour cannot be held at that pressure")

    ratio = 0.621945 * vapour_pa / (total_pa - vapour_pa)
    enthalpy = 1.006 * dry_bulb_c + ratio * (2501 + 1.86 * dry_bulb_c)
    dew_point = _dew_point(vapour_pa)
    wet_bulb = _wet_bulb(dry_bulb_c, ratio, pressure_kpa, dew_point)

    return {
        "dry_bulb_c": round(dry_bulb_c, 4),
        "relative_humidity_pct": round(relative_humidity * 100, 2),
        "pressure_kpa": round(pressure_kpa, 4),
        "saturation_pressure_kpa": round(saturation / 1000, 5),
        "vapour_pressure_kpa": round(vapour_pa / 1000, 5),
        "humidity_ratio": ratio,
        "humidity_ratio_g_per_kg": round(ratio * 1000, 3),
        "enthalpy_kj_per_kg": round(enthalpy, 3),
        "specific_volume_m3_per_kg": round(
            0.287042 * (dry_bulb_c + 273.15) * (1 + 1.607858 * ratio) / pressure_kpa, 5
        ),
        "dew_point_c": round(dew_point, 3),
        "wet_bulb_c": round(wet_bulb, 3),
    }


def _dew_point(vapour_pa: float) -> float:
    """Invert the saturation curve by bisection between -40 °C and the boiling point."""
    low, high = -40.0, 100.0
    for _ in range(80):
        middle = (low + high) / 2
        try:
            pressure = saturation_pressure_pa(middle)
        except (ValueError, NotImplementedError):
            high = middle
            continue
        if pressure < vapour_pa:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def _wet_bulb(dry_bulb_c: float, ratio: float, pressure_kpa: float, dew_point: float) -> float:
    """Adiabatic saturation temperature.

    ASHRAE's relation — the moisture in the air equals the moisture picked up by
    saturating it at the wet-bulb temperature:

        W = ((2501 - 2.326·Twb)·Ws(Twb) - 1.006·(Tdb - Twb))
            / (2501 + 1.86·Tdb - 4.186·Twb)

    Bounded by the dew point below and the dry bulb above, with the residual changing
    sign across that bracket, so bisection is enough.
    """
    low, high = dew_point, dry_bulb_c
    if high <= low:
        return dry_bulb_c

    def residual(wet_bulb_c: float) -> float:
        saturation = saturation_pressure_pa(wet_bulb_c)
        saturated_ratio = 0.621945 * saturation / (pressure_kpa * 1000 - saturation)
        numerator = (2501 - 2.326 * wet_bulb_c) * saturated_ratio - 1.006 * (
            dry_bulb_c - wet_bulb_c
        )
        denominator = 2501 + 1.86 * dry_bulb_c - 4.186 * wet_bulb_c
        return numerator - ratio * denominator

    for _ in range(80):
        middle = (low + high) / 2
        try:
            if residual(middle) < 0:
                low = middle
            else:
                high = middle
        except (ValueError, NotImplementedError):
            low = middle
    return (low + high) / 2
