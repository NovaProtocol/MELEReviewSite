"""The thermo solver and the calculators, ported from the previous build.

The solver is pure Python over CoolProp, so it is tested directly. The calculator
JS is checked for the element ids its pages provide, which is the contract between
the two, and exhaustively enough that a renamed input fails here rather than in a
browser.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.thermo.solvers import solve

CASES = [
    ("carnot", "water", {"T_high": 600, "T_low": 300, "P1": 101325, "r_exp": 2}, 4),
    ("otto", "air", {"r": 8, "T1": 300, "P1": 101325}, 4),
    ("diesel", "air", {"r": 18, "rc": 2.5, "T1": 300, "P1": 101325}, 4),
    ("dual", "air", {"r": 14, "rc": 2.0, "rp": 2.5, "T1": 300, "P1": 101325}, 5),
    ("rankine", "water", {"P_boiler": 3000000, "P_cond": 10000, "T_turbine": 600}, 4),
    ("brayton", "air", {"rp": 10, "T1": 300, "P1": 101325, "T3": 1200}, 4),
    (
        "vapor-compression",
        "r134a",
        {"P_evap": 200000, "P_cond": 1000000, "T_comp": 280},
        4,
    ),
]


@pytest.mark.parametrize(("cycle", "fluid", "parameters", "states"), CASES)
def test_every_cycle_solves(cycle, fluid, parameters, states):
    result = solve(cycle, fluid, parameters)
    assert result.solved, f"{cycle} did not solve: {result.missing}"
    assert len(result.states) == states
    for state in result.states:
        assert state.P > 0
        assert state.T > 0


@pytest.mark.parametrize(("cycle", "fluid", "parameters", "states"), CASES)
def test_cycle_values_are_finite(cycle, fluid, parameters, states):
    """Entropy is referenced to zero for the ideal-gas cycles, so the check is
    finiteness and a positive pressure/temperature rather than s > 0."""
    import math

    result = solve(cycle, fluid, parameters)
    for state in result.states:
        assert math.isfinite(state.s)
        assert math.isfinite(state.h)
        assert math.isfinite(state.v)
        assert state.v > 0


def test_missing_inputs_are_reported_not_guessed():
    result = solve("rankine", "water", {"P_boiler": 3000000})
    assert not result.solved
    assert result.missing


def test_cycle_endpoint_requires_a_session(client):
    response = client.post(
        "/api/tools/cycle",
        json={
            "cycle": "rankine",
            "input_mode": "fluid",
            "fluid": "water",
            "parameters": {"P_boiler": 3000000, "P_cond": 10000, "T_turbine": 600},
            "diagram": {"x": "s", "y": "T"},
        },
    )
    assert response.status_code == 401


def test_cycle_endpoint_returns_states(admin_client):
    response = admin_client.post(
        "/api/tools/cycle",
        json={
            "cycle": "rankine",
            "input_mode": "fluid",
            "fluid": "water",
            "parameters": {"P_boiler": 3000000, "P_cond": 10000, "T_turbine": 600},
            "diagram": {"x": "s", "y": "T"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["solved"] is True
    assert len(body["states"]) == 4
    assert len(body["segments"]) == 4
    assert body["dome"] is not None


def test_cycle_endpoint_plot_format(admin_client):
    response = admin_client.post(
        "/api/tools/cycle",
        json={
            "cycle": "carnot",
            "input_mode": "fluid",
            "fluid": "water",
            "parameters": {"T_high": 600, "T_low": 300},
            "diagram": {"x": "s", "y": "T"},
            "format": "plot",
        },
    )
    body = response.json()
    assert body["solved"] is True
    assert body["x"] == "s"
    assert len(body["segments"]) == 4


CALCULATOR_IDS = {
    "unit.js": ["u-cat", "u-value", "u-from", "u-to", "u-convert", "u-result"],
    "fluids.js": ["f-q", "f-d", "f-rho", "f-mu", "f-l", "f-eps", "f-eff", "f-calc", "f-result"],
    "heat.js": ["h-k", "h-a", "h-l", "h-dt", "h-conduc", "cv-h", "cv-a", "cv-dt", "cv-conv"],
    "strength.js": ["s-f", "s-a", "s-l", "s-e", "b-l", "b-p", "t-t", "t-d"],
    "psychro.js": ["p-t", "p-rh", "p-p", "p-calc", "m1", "m2", "p-mix"],
    "machine.js": ["g-driver", "g-driven", "g-rpm", "bt-d1", "bt-d2", "pw-t", "pw-rpm"],
}

TEMPLATES = {
    "unit.js": "tools/unit.html",
    "fluids.js": "tools/fluids.html",
    "heat.js": "tools/heat.html",
    "strength.js": "tools/strength.html",
    "psychro.js": "tools/psychro.html",
    "machine.js": "tools/machine.html",
}


@pytest.mark.parametrize(("script", "ids"), CALCULATOR_IDS.items())
def test_calculator_ids_exist_in_its_page(script, ids):
    page = Path("app/templates") / TEMPLATES[script]
    source = page.read_text(encoding="utf-8")
    for element_id in ids:
        assert f'id="{element_id}"' in source, f"{TEMPLATES[script]} is missing #{element_id}"


def test_tool_pages_are_standalone_documents():
    for template in TEMPLATES.values():
        source = (Path("app/templates") / template).read_text(encoding="utf-8")
        assert source.lstrip().startswith('{% extends "tools/_embed.html" %}')
    embed = Path("app/templates/tools/_embed.html").read_text(encoding="utf-8")
    assert "<!doctype html>" in embed
    assert "_shell/base.html" not in embed


def test_every_tool_in_the_catalogue_has_a_page_and_a_slug():
    from app.routes.tools import TOOLS

    for tool in TOOLS:
        assert (Path("app/templates") / f"tools/{tool['slug']}.html").exists(), tool["slug"]
        assert tool["keywords"].strip()
        assert tool["group"].strip()


def test_thermo_js_calls_the_tool_endpoint():
    source = Path("app/static/js/thermo_cycle.js").read_text(encoding="utf-8")
    assert "/api/tools/cycle" in source
    assert '"/api/cycle"' not in source
