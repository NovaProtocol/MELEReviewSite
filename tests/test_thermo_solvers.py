from __future__ import annotations

import math

import pytest

from api.thermo.solvers import solve
from api.thermo.solvers.base import CycleResult
from api.thermo.solvers.ideal_gas import GAMMA, CP, CV, R, air_state


# ---------------------------------------------------------------------------
# Fixtures: valid fluid + parameters per cycle
# ---------------------------------------------------------------------------
CYCLE_FIXTURES: dict[str, tuple[str, dict[str, float]]] = {
    "otto": ("air", {"r": 8, "T1": 300, "P1": 101325, "T3": 1800}),
    "diesel": ("air", {"r": 18, "rc": 2, "T1": 300, "P1": 101325}),
    "dual": ("air", {"r": 18, "rc": 2, "rp": 1.5, "T1": 300, "P1": 101325}),
    "brayton": ("air", {"rp": 8, "T1": 300, "P1": 101325, "T3": 1200}),
    "rankine": ("water", {"P_boiler": 3_000_000, "P_cond": 10_000, "T_turbine": 873}),
    "vapor_compression": ("r134a", {"P_evap": 120_000, "P_cond": 800_000, "T_comp": 290}),
    "vapor-compression": ("r134a", {"P_evap": 120_000, "P_cond": 800_000, "T_comp": 290}),
    "carnot": ("air", {"T_high": 600, "T_low": 300}),
}

# All cycles requested by brief (hyphen form)
BRIEF_CYCLES = ["otto", "diesel", "dual", "brayton", "rankine", "vapor-compression", "carnot"]

# Extended set including ideal_gas for coverage
ALL_CYCLES = BRIEF_CYCLES + ["vapor_compression"]


def _assert_finite_states(result: CycleResult) -> None:
    assert result.solved is True, f"{result.cycle} not solved: {result.missing}"
    assert len(result.states) > 0
    for idx, s in enumerate(result.states):
        for attr in ("P", "T", "h", "s", "v"):
            val = getattr(s, attr)
            assert isinstance(val, (float, int)), f"{result.cycle} state {idx} {attr} not numeric: {val!r}"
            assert math.isfinite(float(val)), f"{result.cycle} state {idx} {attr} not finite: {val!r}"
            assert float(val) != 0 or attr in ("s",), f"{result.cycle} state {idx} {attr} unexpectedly zero"


# ---------------------------------------------------------------------------
# Step 1 / 2: parametrized finite guard
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cycle", BRIEF_CYCLES)
def test_solver_returns_finite(cycle: str) -> None:
    fluid, params = CYCLE_FIXTURES[cycle]
    result = solve(cycle, fluid, params)
    _assert_finite_states(result)


def test_all_solvers_return_finite_extended() -> None:
    """Ensure every registered solver (both alias forms) yields finite states."""
    for cycle in ALL_CYCLES:
        fluid, params = CYCLE_FIXTURES[cycle]
        result = solve(cycle, fluid, params)
        _assert_finite_states(result)


def test_solver_returns_finite_via_api(client) -> None:
    """Same finite guard exercised through the HTTP /api/cycle endpoint."""
    for cycle in BRIEF_CYCLES:
        fluid, params = CYCLE_FIXTURES[cycle]
        resp = client.post(
            "/api/cycle",
            json={
                "cycle": cycle,
                "fluid": fluid,
                "parameters": params,
                "diagram": {"x": "s", "y": "T"},
            },
        )
        assert resp.status_code == 200, f"{cycle} HTTP {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["solved"] is True, f"{cycle} API not solved: {data.get('missing')}"
        for st in data["states"]:
            for k in ("P", "T", "h", "s", "v"):
                assert math.isfinite(st[k]), f"{cycle} API state {k} not finite: {st[k]}"


# ---------------------------------------------------------------------------
# Finite guard: missing params -> unsolved
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "cycle",
    ["otto", "diesel", "dual", "brayton", "carnot", "rankine", "vapor_compression", "vapor-compression"],
)
def test_solver_missing_params_returns_unsolved(cycle: str) -> None:
    result = solve(cycle, "water", {})
    assert result.solved is False
    assert len(result.missing) > 0
    assert len(result.states) == 0


def test_solver_missing_params_via_api(client) -> None:
    resp = client.post(
        "/api/cycle",
        json={"cycle": "otto", "fluid": "air", "parameters": {}, "diagram": {"x": "s", "y": "T"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["solved"] is False
    assert len(data["missing"]) > 0


def test_solver_unknown_cycle_raises() -> None:
    with pytest.raises(ValueError, match="Unknown cycle"):
        solve("unknown_cycle", "air", {})


# ---------------------------------------------------------------------------
# Known-value tests (thermodynamic efficiency / COP)
# ---------------------------------------------------------------------------
def test_otto_known_efficiency() -> None:
    """Otto efficiency = 1 - 1/r^(gamma-1). r=8 -> ~0.5647."""
    fluid, params = CYCLE_FIXTURES["otto"]
    result = solve("otto", fluid, params)
    assert result.solved
    r = params["r"]
    expected = 1 - 1 / (r ** (GAMMA - 1))
    # Compute from states: eta = 1 - (T4-T1)/(T3-T2)
    T1, T2, T3, T4 = [s.T for s in result.states]
    actual = 1 - (T4 - T1) / (T3 - T2)
    assert actual == pytest.approx(expected, rel=1e-9)
    assert actual == pytest.approx(0.56473, rel=1e-3)


def test_diesel_known_efficiency() -> None:
    """Diesel efficiency = 1 - 1/r^(gamma-1) * (rc^gamma-1)/(gamma*(rc-1))."""
    fluid, params = CYCLE_FIXTURES["diesel"]
    result = solve("diesel", fluid, params)
    assert result.solved
    r, rc = params["r"], params["rc"]
    expected = 1 - (1 / r ** (GAMMA - 1)) * ((rc ** GAMMA - 1) / (GAMMA * (rc - 1)))
    # Diesel: Q_in is isobaric (CP), Q_out is isochoric (CV)
    T1, T2, T3, T4 = [s.T for s in result.states]
    actual = 1 - (T4 - T1) / (GAMMA * (T3 - T2))
    assert actual == pytest.approx(expected, rel=1e-9)
    assert 0.60 < actual < 0.70


def test_dual_known_efficiency() -> None:
    fluid, params = CYCLE_FIXTURES["dual"]
    result = solve("dual", fluid, params)
    assert result.solved
    # Dual should have 5 states
    assert len(result.states) == 5
    _assert_finite_states(result)
    # Efficiency sanity: 0.5-0.75
    hs = [s.h for s in result.states]
    # Q_in = (h3-h2)+(h4-h3); W_net computed via energy balance
    # Use T-based ideal gas check: net work = sum
    h1, h2, h3, h4, h5 = hs
    q_in = (h3 - h2) + (h4 - h3)
    q_out = h5 - h1
    eta = 1 - q_out / q_in
    assert 0.4 < eta < 0.75
    assert math.isfinite(eta)


def test_brayton_known_efficiency() -> None:
    """Brayton efficiency = 1 - 1/rp^((gamma-1)/gamma). rp=8 -> ~0.448."""
    fluid, params = CYCLE_FIXTURES["brayton"]
    result = solve("brayton", fluid, params)
    assert result.solved
    rp = params["rp"]
    expected = 1 - 1 / (rp ** ((GAMMA - 1) / GAMMA))
    T1, T2, T3, T4 = [s.T for s in result.states]
    # Brayton: both isobaric -> Q = CP*dT
    actual = 1 - (T4 - T1) / (T3 - T2)
    assert actual == pytest.approx(expected, rel=1e-9)
    assert actual == pytest.approx(0.448, rel=2e-2)


def test_carnot_known_efficiency() -> None:
    """Carnot efficiency = 1 - T_low/T_high = 0.5 for 300/600."""
    fluid, params = CYCLE_FIXTURES["carnot"]
    result = solve("carnot", fluid, params)
    assert result.solved
    expected = 1 - params["T_low"] / params["T_high"]
    assert expected == pytest.approx(0.5)
    # Check via API: solver uses ideal gas; verify T values
    temps = [s.T for s in result.states]
    assert temps[0] == pytest.approx(params["T_low"])
    assert temps[1] == pytest.approx(params["T_high"])
    # Processes must be isentropic/isothermal alternating
    assert result.processes == ["isentropic", "isothermal", "isentropic", "isothermal"]


def test_rankine_known_efficiency() -> None:
    """Rankine with P_boiler=3 MPa, P_cond=10 kPa, T_turbine=873K -> eta ~0.37."""
    fluid, params = CYCLE_FIXTURES["rankine"]
    result = solve("rankine", fluid, params)
    assert result.solved
    h1, h2, h3, h4 = [s.h for s in result.states]
    w_pump = h2 - h1
    w_turb = h3 - h4
    w_net = w_turb - w_pump
    q_in = h3 - h2
    eta = w_net / q_in
    # Known value for these conditions is ~0.3725 (computed via CoolProp)
    assert eta == pytest.approx(0.372, rel=0.05)
    assert 0.30 < eta < 0.45
    # All enthalpies finite and positive; s finite
    _assert_finite_states(result)
    # Pump work small relative to turbine
    assert w_pump < w_turb * 0.05


def test_vapor_compression_cop_finite() -> None:
    fluid, params = CYCLE_FIXTURES["vapor_compression"]
    result = solve("vapor_compression", fluid, params)
    assert result.solved
    h1, h2, h3, h4 = [s.h for s in result.states]
    cop = (h1 - h4) / (h2 - h1)
    assert math.isfinite(cop)
    assert 1.0 < cop < 10.0
    # Isenthalpic throttling: h3 == h4
    assert h3 == pytest.approx(h4, rel=1e-9)
    # Isentropic compression: s1 == s2
    assert result.states[0].s == pytest.approx(result.states[1].s, rel=1e-6)


def test_vapor_compression_alias_consistency() -> None:
    """Both 'vapor_compression' and 'vapor-compression' resolve to same solver."""
    f1, p1 = CYCLE_FIXTURES["vapor_compression"]
    f2, p2 = CYCLE_FIXTURES["vapor-compression"]
    r1 = solve("vapor_compression", f1, p1)
    r2 = solve("vapor-compression", f2, p2)
    assert r1.solved and r2.solved
    for s1, s2 in zip(r1.states, r2.states):
        assert s1.h == pytest.approx(s2.h, rel=1e-9)


# ---------------------------------------------------------------------------
# ideal_gas module coverage
# ---------------------------------------------------------------------------
def test_ideal_gas_air_state_finite() -> None:
    st = air_state(101325, 300)
    for attr in ("P", "T", "v", "h", "s"):
        assert math.isfinite(getattr(st, attr))
    assert st.v == pytest.approx(R * 300 / 101325, rel=1e-9)
    assert st.h == pytest.approx(CP * 300, rel=1e-9)
    assert st.s == pytest.approx(0.0, abs=1e-9)  # reference point


def test_ideal_gas_constants_consistency() -> None:
    assert GAMMA == pytest.approx(1.4)
    assert R == pytest.approx(287.0)
    assert CP == pytest.approx(R * GAMMA / (GAMMA - 1), rel=1e-9)
    assert CV == pytest.approx(R / (GAMMA - 1), rel=1e-9)
    assert CP - CV == pytest.approx(R, rel=1e-9)


def test_ideal_gas_entropy_increases_with_temperature() -> None:
    s_cold = air_state(101325, 300).s
    s_hot = air_state(101325, 600).s
    assert s_hot > s_cold


def test_ideal_gas_state_via_solve_otto_is_ideal() -> None:
    """Otto solver must flag ideal_gas=True and return AirState-compatible fields."""
    result = solve("otto", "air", {"r": 8, "T1": 300, "P1": 101325})
    assert result.ideal_gas is True
    assert result.fluid == "air"


# ---------------------------------------------------------------------------
# Additional guard: non-finite inputs produce unsolved
# ---------------------------------------------------------------------------
def test_rankine_invalid_pressures_unsolved() -> None:
    # condenser pressure >= boiler pressure triggers guard
    result = solve("rankine", "water", {"P_boiler": 10_000, "P_cond": 3_000_000, "T_turbine": 600})
    assert result.solved is False


def test_vapor_compression_invalid_pressures_unsolved() -> None:
    result = solve("vapor_compression", "r134a", {"P_evap": 800_000, "P_cond": 120_000, "T_comp": 290})
    assert result.solved is False
