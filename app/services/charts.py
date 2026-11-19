"""Cycle diagrams, drawn when they are asked for.

Every diagram is a URL, never a stored image:

    /api/charts/rankine/TS?override_data=<base64 json>

so the server holds no gallery of pictures nobody opened, and an embedded diagram
carries its own settings: renaming a state or adding a note travels in the link, and
opening somebody else's link gives you a diagram you can edit rather than a flat
picture.

The shapes are schematic rather than measured. A T-s diagram of a Rankine cycle is
recognisable by its dome and its four legs; drawing it from a real steam table would
require the operating pressures, and a reader who has those is better served by the
steam tool. This is the sketch you would draw on the margin of your working.
"""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from io import StringIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

INK = "#1b2430"
MUTED = "#6b7a8a"
ACCENT = "#2f9e8f"
COOL = "#3d6ea8"
HOT = "#c2703d"

KINDS = {
    "rankine": ("TS", "PV", "schematic"),
    "brayton": ("TS", "PV"),
    "otto": ("TS", "PV"),
    "diesel": ("TS", "PV"),
    "carnot": ("TS", "PV"),
    "vapor-compression": ("TS", "PH"),
    "psychrometric": ("chart",),
}


def decode_override(raw: str | None) -> dict:
    """The settings in the link, or nothing.

    A malformed payload is ignored rather than refused: a broken link should still
    draw the diagram it names, just without the customisation.
    """
    if not raw:
        return {}
    try:
        padded = raw + "=" * (-len(raw) % 4)
        parsed = json.loads(base64.b64decode(padded).decode("utf-8"))
        if not isinstance(parsed, dict):
            return {}
        return parsed
    except (ValueError, UnicodeDecodeError):
        return {}


def _dome(ax):
    """The saturated dome every T-s and P-v diagram shares."""
    ax.plot([0.25, 0.45, 0.7, 1.0, 1.3, 1.5], [0.9, 1.7, 2.4, 3.0, 3.4, 3.55], color=ACCENT, lw=1.8)
    ax.plot([1.5, 1.8, 2.1, 2.4, 2.8, 3.3], [3.55, 3.3, 2.9, 2.4, 1.75, 0.95], color=ACCENT, lw=1.8)


def _leg(ax, points, colour, label, offset=(0.06, 0.08)):
    """One leg of the cycle, labelled at the middle of the line.

    The number names the state at the end of the leg, so it goes offset from the
    midpoint: putting it on the vertex makes two labels land on each other wherever
    two legs meet, which is every corner of the cycle.
    """
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    ax.plot(xs, ys, color=colour, lw=1.9)
    middle = len(points) // 2
    x = (xs[middle - 1] + xs[middle]) / 2
    y = (ys[middle - 1] + ys[middle]) / 2
    ax.annotate(
        label,
        (x, y),
        textcoords="offset points",
        xytext=(offset[0] * 14, offset[1] * 14),
        fontsize=10,
        color=colour,
        fontweight="bold",
    )


def _labels(override: dict, defaults: list[str]) -> list[str]:
    custom = override.get("labels") or {}
    return [custom.get(name, name) for name in defaults]


def _finish(ax, override: dict, title: str, xlabel: str, ylabel: str):
    ax.set_xlabel(xlabel, fontsize=9, color=MUTED)
    ax.set_ylabel(ylabel, fontsize=9, color=MUTED)
    ax.set_title(str(override.get("title") or title), fontsize=11, color=INK, pad=10)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#cdd6dd")
    for note in override.get("notes") or []:
        if note:
            ax.text(
                0.98,
                0.03,
                str(note),
                transform=ax.transAxes,
                ha="right",
                fontsize=8,
                color=MUTED,
            )


def _rankine_ts(ax, override):
    _dome(ax)
    names = _labels(override, ["1", "2", "3", "4"])
    # 1 pump -> 2 boiler -> 3 turbine -> 4 condenser
    _leg(ax, [(0.45, 1.0), (0.45, 2.9)], HOT, names[1])
    _leg(ax, [(0.45, 2.9), (2.6, 2.9)], HOT, names[2], (0.05, 0.12))
    _leg(ax, [(2.6, 2.9), (2.6, 1.0)], COOL, names[3])
    _leg(ax, [(2.6, 1.0), (0.45, 1.0)], COOL, names[0], (0.05, -0.22))
    _finish(ax, override, "Rankine cycle", "Entropy, s", "Temperature, T")


def _rankine_pv(ax, override):
    _dome(ax)
    names = _labels(override, ["1", "2", "3", "4"])
    _leg(ax, [(0.5, 1.0), (0.5, 3.2)], HOT, names[1])
    _leg(ax, [(0.5, 3.2), (3.0, 3.2)], HOT, names[2], (0.05, 0.12))
    _leg(ax, [(3.0, 3.2), (3.0, 1.0)], COOL, names[3])
    _leg(ax, [(3.0, 1.0), (0.5, 1.0)], COOL, names[0], (0.05, -0.22))
    _finish(ax, override, "Rankine cycle", "Specific volume, v", "Pressure, P")


def _brayton_ts(ax, override):
    names = _labels(override, ["1", "2", "3", "4"])
    _leg(ax, [(0.4, 1.0), (1.0, 2.2)], COOL, names[1])
    _leg(ax, [(1.0, 2.2), (2.4, 3.4)], HOT, names[2], (0.05, 0.1))
    _leg(ax, [(2.4, 3.4), (2.9, 1.6)], HOT, names[3])
    _leg(ax, [(2.9, 1.6), (0.4, 1.0)], COOL, names[0], (0.05, -0.2))
    _finish(ax, override, "Brayton cycle", "Entropy, s", "Temperature, T")


def _brayton_pv(ax, override):
    names = _labels(override, ["1", "2", "3", "4"])
    _leg(ax, [(0.5, 1.0), (1.2, 3.0)], COOL, names[1])
    _leg(ax, [(1.2, 3.0), (3.0, 3.0)], HOT, names[2], (0.05, 0.12))
    _leg(ax, [(3.0, 3.0), (3.4, 1.0)], HOT, names[3])
    _leg(ax, [(3.4, 1.0), (0.5, 1.0)], COOL, names[0], (0.05, -0.2))
    _finish(ax, override, "Brayton cycle", "Specific volume, v", "Pressure, P")


def _otto_ts(ax, override):
    names = _labels(override, ["1", "2", "3", "4"])
    _leg(ax, [(0.5, 1.0), (1.1, 2.6)], COOL, names[1])
    _leg(ax, [(1.1, 2.6), (1.6, 3.4)], HOT, names[2], (0.05, 0.08))
    _leg(ax, [(1.6, 3.4), (2.6, 1.0)], HOT, names[3])
    _leg(ax, [(2.6, 1.0), (0.5, 1.0)], COOL, names[0], (0.05, -0.2))
    _finish(ax, override, "Otto cycle", "Entropy, s", "Temperature, T")


def _otto_pv(ax, override):
    names = _labels(override, ["1", "2", "3", "4"])
    _leg(ax, [(0.6, 1.0), (0.9, 3.2)], COOL, names[1])
    _leg(ax, [(0.9, 3.2), (1.4, 3.2)], HOT, names[2], (0.05, 0.12))
    _leg(ax, [(1.4, 3.2), (3.2, 1.0)], HOT, names[3])
    _leg(ax, [(3.2, 1.0), (0.6, 1.0)], COOL, names[0], (0.05, -0.2))
    _finish(ax, override, "Otto cycle", "Specific volume, v", "Pressure, P")


def _diesel_ts(ax, override):
    names = _labels(override, ["1", "2", "3", "4"])
    _leg(ax, [(0.5, 1.0), (1.1, 2.7)], COOL, names[1])
    _leg(ax, [(1.1, 2.7), (2.0, 2.7)], HOT, names[2], (0.05, 0.1))
    _leg(ax, [(2.0, 2.7), (2.8, 1.0)], HOT, names[3])
    _leg(ax, [(2.8, 1.0), (0.5, 1.0)], COOL, names[0], (0.05, -0.2))
    _finish(ax, override, "Diesel cycle", "Entropy, s", "Temperature, T")


def _diesel_pv(ax, override):
    names = _labels(override, ["1", "2", "3", "4"])
    _leg(ax, [(0.6, 1.0), (0.9, 3.2)], COOL, names[1])
    _leg(ax, [(0.9, 3.2), (1.9, 3.2)], HOT, names[2], (0.05, 0.12))
    _leg(ax, [(1.9, 3.2), (3.2, 1.0)], HOT, names[3])
    _leg(ax, [(3.2, 1.0), (0.6, 1.0)], COOL, names[0], (0.05, -0.2))
    _finish(ax, override, "Diesel cycle", "Specific volume, v", "Pressure, P")


def _carnot_ts(ax, override):
    names = _labels(override, ["1", "2", "3", "4"])
    _leg(ax, [(0.6, 3.2), (2.4, 3.2)], HOT, names[1], (0.05, 0.12))
    _leg(ax, [(2.4, 3.2), (2.9, 1.0)], HOT, names[2])
    _leg(ax, [(2.9, 1.0), (1.1, 1.0)], COOL, names[3], (0.05, -0.22))
    _leg(ax, [(1.1, 1.0), (0.6, 3.2)], COOL, names[0])
    _finish(ax, override, "Carnot cycle", "Entropy, s", "Temperature, T")


def _carnot_pv(ax, override):
    names = _labels(override, ["1", "2", "3", "4"])
    _leg(ax, [(0.7, 3.1), (2.4, 3.1)], HOT, names[1], (0.05, 0.12))
    _leg(ax, [(2.4, 3.1), (3.0, 1.0)], HOT, names[2])
    _leg(ax, [(3.0, 1.0), (1.1, 1.0)], COOL, names[3], (0.05, -0.22))
    _leg(ax, [(1.1, 1.0), (0.7, 3.1)], COOL, names[0])
    _finish(ax, override, "Carnot cycle", "Specific volume, v", "Pressure, P")


def _vapor_ts(ax, override):
    _dome(ax)
    names = _labels(override, ["1", "2", "3", "4"])
    _leg(ax, [(0.45, 1.9), (2.62, 1.9)], COOL, names[0], (0.05, -0.22))
    _leg(ax, [(2.62, 1.9), (2.9, 2.95)], COOL, names[1])
    _leg(ax, [(2.9, 2.95), (0.45, 2.95)], HOT, names[2], (0.05, 0.12))
    _leg(ax, [(0.45, 2.95), (0.45, 1.9)], HOT, names[3])
    _finish(ax, override, "Vapour compression cycle", "Entropy, s", "Temperature, T")


def _vapor_ph(ax, override):
    _dome(ax)
    names = _labels(override, ["1", "2", "3", "4"])
    _leg(ax, [(0.45, 1.9), (2.62, 1.9)], COOL, names[0], (0.05, -0.22))
    _leg(ax, [(2.62, 1.9), (2.9, 3.0)], COOL, names[1])
    _leg(ax, [(2.9, 3.0), (0.45, 3.0)], HOT, names[2], (0.05, 0.12))
    _leg(ax, [(0.45, 3.0), (0.45, 1.9)], HOT, names[3])
    _finish(ax, override, "Vapour compression cycle", "Enthalpy, h", "Pressure, P")


def _psychrometric(ax, override):
    """A sketch of the chart's shape: saturation curve and dry-bulb lines."""
    xs = [i / 20 for i in range(21)]
    ax.plot(xs, [0.5 + 0.85 * (x ** 0.8) for x in xs], color=ACCENT, lw=1.8)
    for relative in (0.2, 0.4, 0.6, 0.8):
        ax.plot(xs, [relative * (0.5 + 0.85 * (x ** 0.8)) for x in xs], color=COOL, lw=1.1)
    ax.set_xlim(0, 1.05)
    ax.set_ylim(0, 1.5)
    _finish(ax, override, "Psychrometric chart", "Dry-bulb temperature", "Humidity ratio")


def _schematic(ax, override):
    """A plant layout: four boxes and the working fluid going round them."""
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7)
    ax.axis("off")
    boxes = [
        ("Boiler", 2.2, 4.6),
        ("Turbine", 6.4, 4.6),
        ("Condenser", 6.4, 1.2),
        ("Pump", 2.2, 1.2),
    ]
    for label, x, y in boxes:
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                1.9,
                1.0,
                boxstyle="round,pad=0.06,rounding_size=0.08",
                linewidth=1.2,
                edgecolor=ACCENT,
                facecolor="#eef7f5",
            )
        )
        ax.text(x + 0.95, y + 0.5, label, ha="center", va="center", fontsize=10, color=INK)

    arrows = [((4.1, 5.1), (6.4, 5.1)), ((7.35, 4.6), (7.35, 2.2)),
              ((6.4, 1.7), (4.1, 1.7)), ((3.15, 2.2), (3.15, 4.6))]
    for start, end in arrows:
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=14, color=COOL))
    ax.set_title(str(override.get("title") or "Rankine plant"), fontsize=11, color=INK)
    for note in override.get("notes") or []:
        if note:
            ax.text(
                0.98, 0.02, str(note), transform=ax.transAxes,
                ha="right", fontsize=8, color=MUTED,
            )


DRAW = {
    ("rankine", "TS"): _rankine_ts,
    ("rankine", "PV"): _rankine_pv,
    ("rankine", "schematic"): _schematic,
    ("brayton", "TS"): _brayton_ts,
    ("brayton", "PV"): _brayton_pv,
    ("otto", "TS"): _otto_ts,
    ("otto", "PV"): _otto_pv,
    ("diesel", "TS"): _diesel_ts,
    ("diesel", "PV"): _diesel_pv,
    ("carnot", "TS"): _carnot_ts,
    ("carnot", "PV"): _carnot_pv,
    ("vapor-compression", "TS"): _vapor_ts,
    ("vapor-compression", "PH"): _vapor_ph,
    ("psychrometric", "chart"): _psychrometric,
}


@lru_cache(maxsize=64)
def render(cycle: str, kind: str, payload: str) -> str:
    """The diagram as inline SVG. Cached on the exact request, so a page that embeds
    one costs one draw per distinct setting."""
    draw = DRAW.get((cycle, kind))
    if draw is None:
        raise KeyError(f"{cycle}/{kind}")

    override = decode_override(payload or None)
    fig, ax = plt.subplots(figsize=(6.0, 4.0), dpi=110)
    fig.patch.set_alpha(0)
    draw(ax, override)
    fig.tight_layout()

    buffer = StringIO()
    fig.savefig(buffer, format="svg", transparent=True)
    plt.close(fig)
    svg = buffer.getvalue()
    return svg[svg.index("<svg") :] if "<svg" in svg else svg


def catalogue() -> dict:
    return {cycle: list(kinds) for cycle, kinds in KINDS.items()}
