"""Turn a small plot spec into a figure, the way a notebook cell does.

A fenced `plot` block in the prose carries JSON, not code:

    ```plot
    {"type": "line", "title": "Isentropic efficiency", "x": [1, 2, 3],
     "series": [{"name": "n = 1.4", "y": [0.9, 0.82, 0.7]}],
     "xlabel": "pressure ratio", "ylabel": "efficiency"}
    ```

It is a spec rather than Python because the prose is written by members, and
running their code to draw a chart is not a trade worth making. The spec covers the
charts a reviewer needs: line, bars, scatter.

Bars take categorical x ("Mathematics", "Power"); a line or scatter needs numbers.
The figure comes back as inline SVG, so it scales with the page and prints properly,
and one cached render serves every view of the same spec.
"""

from __future__ import annotations

import json
from functools import lru_cache
from io import StringIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

INK = "#1b2430"
MUTED = "#6b7a8a"
PALETTE = ["#2f9e8f", "#3d6ea8", "#c2703d", "#8b5c9e", "#4d8b5a"]
KINDS = {"line", "bar", "scatter"}


@lru_cache(maxsize=128)
def _render_cached(payload: str) -> tuple[str, str]:
    """(svg, error). Cached on the spec, so a page view costs nothing."""
    try:
        spec = json.loads(payload)
    except ValueError:
        return "", "plot: the spec is not valid JSON"
    if not isinstance(spec, dict) or spec.get("type") not in KINDS:
        return "", "plot: type must be line, bar or scatter"

    series = spec.get("series") or []
    if not isinstance(series, list) or not series:
        return "", "plot: needs at least one series"

    # A null is a gap: a dome has two branches, and a cycle does not exist at every
    # x of the dome, so a series is allowed to be absent at a point.
    numbers: list[list[float]] = []
    for item in series:
        try:
            numbers.append(
                [float("nan") if value is None else float(value) for value in item.get("y") or []]
            )
        except TypeError, ValueError:
            return "", "plot: y values must be numbers"
    if not numbers or not numbers[0]:
        return "", "plot: a series needs at least one point"
    # Bars are usually categorical, so a non-numeric x is read as labels rather
    # than refused. A line or scatter needs real numbers.
    raw_x = spec.get("x")
    xs: list[float] | None = None
    labels: list[str] = []
    if raw_x:
        try:
            xs = [float(value) for value in raw_x]
        except TypeError, ValueError:
            if spec["type"] != "bar":
                return "", "plot: x values must be numbers for a line or scatter"
            labels = [str(value) for value in raw_x]

    default_positions = xs

    fig, ax = plt.subplots(figsize=(6.4, 3.6), dpi=110)
    kind = spec["type"]
    for index, (item, values) in enumerate(zip(series, numbers, strict=False)):
        colour = PALETTE[index % len(PALETTE)]
        name = str(item.get("name") or f"series {index + 1}")

        # A series may bring its own x: a saturation dome and a cycle loop do not
        # share a grid, and a loop is not a function of x at all.
        own_x = item.get("x")
        if own_x:
            try:
                positions = [float(value) for value in own_x]
            except TypeError, ValueError:
                return "", "plot: series x values must be numbers"
            if len(positions) != len(values):
                return "", "plot: a series x and y must be the same length"
        elif default_positions is not None:
            if len(default_positions) != len(values):
                return "", "plot: every series must be the same length as x"
            positions = default_positions
        else:
            positions = list(range(len(values)))

        if kind == "bar":
            width = 0.8 / max(len(numbers), 1)
            offset = (index - (len(numbers) - 1) / 2) * width
            ax.bar(
                [position + offset for position in positions],
                values,
                width=width,
                label=name,
                color=colour,
            )
        elif kind == "scatter":
            ax.scatter(positions, values, label=name, color=colour, s=22)
        else:
            ax.plot(positions, values, label=name, color=colour, linewidth=1.8)

    if labels:
        ax.set_xticks(positions)
        ax.set_xticklabels(labels)
    if spec.get("title"):
        ax.set_title(str(spec["title"]), fontsize=10.5, color=INK)
    if spec.get("xlabel"):
        ax.set_xlabel(str(spec["xlabel"]), fontsize=9, color=MUTED)
    if spec.get("ylabel"):
        ax.set_ylabel(str(spec["ylabel"]), fontsize=9, color=MUTED)
    if len(series) > 1:
        ax.legend(fontsize=8, frameon=False)
    ax.grid(True, color="#e6ebef", linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#cdd6dd")
    ax.tick_params(colors=MUTED, labelsize=8)
    fig.tight_layout()

    buffer = StringIO()
    fig.savefig(buffer, format="svg", transparent=True)
    plt.close(fig)
    svg = buffer.getvalue()
    # Strip the XML prologue so it can sit inside a document.
    svg = svg[svg.index("<svg") :] if "<svg" in svg else svg
    return svg, ""


def render(spec_text: str) -> tuple[str, str]:
    return _render_cached(spec_text.strip())
