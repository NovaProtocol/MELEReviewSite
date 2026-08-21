# Task 10: Thermo Solver Test Coverage — Report

## What was done
Created `tests/test_thermo_solvers.py` with parametrized coverage for all thermo cycles (`otto`, `diesel`, `dual`, `brayton`, `rankine`, `vapor_compression`/`vapor-compression`, `carnot`, `ideal_gas`) via `api.thermo.solvers.solve(cycle, fluid, params)`.

## Tests (33 new)

### Finite guard (parametrized)
- `test_solver_returns_finite` — parametrized over `["otto","diesel","dual","brayton","rankine","vapor-compression","carnot"]` (brief spec) asserts `solved==True` and every `P,T,h,s,v` is finite.
- `test_all_solvers_return_finite_extended` — same for both alias forms including `vapor_compression`.
- `test_solver_returns_finite_via_api` — repeats via `POST /api/cycle` HTTP layer (`TestClient`), validates `_guard()` path in `api/routes/thermo.py:82`.
- `test_solver_missing_params_returns_unsolved` — empty dict → `solved=False`, `missing` non-empty, no states (parametrized 8 cycles).
- `test_solver_missing_params_via_api` + `test_solver_unknown_cycle_raises` — API guard and `ValueError` for unknown cycle.

### Known-value efficiency / COP
- `test_otto_known_efficiency` — `r=8` → `η=1-1/r^(γ-1) ≈0.5647` via `T` states.
- `test_diesel_known_efficiency` — `r=18, rc=2` → `η=1-1/r^(γ-1)*(rc^γ-1)/(γ(rc-1)) ≈0.631` (CP/CV-correct `1-(T4-T1)/(γ(T3-T2))`).
- `test_dual_known_efficiency` — 5-state dual, `0.4<η<0.75`.
- `test_brayton_known_efficiency` — `rp=8` → `η=1-1/rp^((γ-1)/γ) ≈0.448` via `T`.
- `test_carnot_known_efficiency` — `T_high=600,T_low=300` → `η=0.5`, verifies `processes` order.
- `test_rankine_known_efficiency` — `P_boiler=3MPa,P_cond=10kPa,T=873K` → `η≈0.372±5%` (`w_net/q_in` via enthalpies), pump work <5% turbine work.
- `test_vapor_compression_cop_finite` — R134a `COP≈3.7`, checks `h3==h4` (isenthalpic) and `s1==s2` (isentropic), `1<COP<10`.
- `test_vapor_compression_alias_consistency` — hyphen vs underscore alias identical.

### ideal_gas module
- `test_ideal_gas_air_state_finite` — `air_state(101325,300)` finite, `v=R*T/P`, `h=CP*T`, `s=0`.
- `test_ideal_gas_constants_consistency` — `CP-CV==R`, `CP=Rγ/(γ-1)`.
- `test_ideal_gas_entropy_increases_with_temperature` + `test_ideal_gas_state_via_solve_otto_is_ideal` — ideal_gas flag.

### Edge guards
- `test_rankine_invalid_pressures_unsolved` — `P_cond >= P_boiler` → unsolved.
- `test_vapor_compression_invalid_pressures_unsolved` — `P_evap >= P_cond` → unsolved.

## Solver APIs verified
- `api.thermo.solvers.base.solve` registry (`_REGISTRY` keys: `carnot,otto,diesel,dual,brayton,rankine,vapor-compression,vapor_compression`)
- `api.thermo.solvers.ideal_gas.air_state`, `GAMMA, CP, CV, R`
- `api.routes.thermo._guard` finite check

## Test results
- `pytest tests/test_thermo_solvers.py` → **33 passed**
- `pytest` full suite → **87 passed** (54 existing + 33 new), 0 failed

## Commits
- `test: add thermo solver coverage for all cycles` — adds `tests/test_thermo_solvers.py`

## Concerns
- `ideal_gas` is not a registered cycle (only a prop helper); tested via `ideal_gas.py` directly. No missing type hints — all solvers already typed (`fluid_name: str, params: dict -> CycleResult`).
