# Solver and Calculators

The ME calculator suite lives under `api/thermo/`, a thermodynamic cycle solver on CoolProp, plus small pure-Python calculators exposed as pages.

## Thermodynamic Cycle Solver

Supported cycles: **Carnot, Otto, Diesel, Dual, Brayton, Rankine, vapor-compression**. Solved with **CoolProp** (no steam tables) via `api/thermo/solver.py` + plotting in `api/thermo/plot.py`.

Endpoint:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/cycle` | Solve + return data; `?format=data\|plot` |
| `POST` | `/api/cycle?format=plot` | Same solver, returns plotting payload for frontends that want server-side plot data |

Request body:

```json
{
 "cycle": "rankine",
 "fluid": "Water",
 "params": {"p_high": 8000, "p_low": 10, "t_high": 500},
 "options": {"unit": "metric"}
}
```

Response (data format):

```json
{
 "states": [{"p": 8000, "t": 500, "h": 3399, "s": 6.72, ...}],
 "performance": {"thermal_efficiency": 0.38, "net_work": 1200, ...},
 "plot": {"ts": [[...], [...]], "pv": [[...], [...]], "dome": [[...]]}
}
```

Plots: live T-s / P-v / any-axis with saturation dome. Data returned; rendered client-side with Plotly.

Frontend:

- `web/templates/calculators/thermo.html`, cycle picker, param form, Plotly charts.
- `web/static/js/thermo_cycle.js`, `fetch("/api/cycle", {method:"POST"})`, renders `data` vs `plot` payloads.

Mypy note: `api/thermo/*` is `ignore_errors = true` in `pyproject.toml` (CoolProp stubs missing), solver logic is tested via `tests/test_thermo_solvers.py`.

## Other Calculators

Static per-cycle pages (no backend math beyond unit conversion):

| Route | Template | Purpose |
|-------|----------|---------|
| `/calculators` | `calculators.html` | Hub |
| `/calculators/unit` | `calculators/unit.html` | Unit converter |
| `/calculators/fluids` | `calculators/fluids.html` | Pipe flow / Bernoulli |
| `/calculators/strength` | `calculators/strength.html` | Strength of materials |
| `/calculators/heat` | `calculators/heat.html` | Heat transfer |
| `/calculators/psychro` | `calculators/psychro.html` | Psychrometrics |
| `/calculators/machine` | `calculators/machine.html` + `machine.js` | Machine design |
| `/calculators/thermo` | `calculators/thermo.html` + `thermo_cycle.js` | Thermo cycles |

Each page mounts page-specific JS under `web/static/js/calculators/`. No server-side gRPC needed, thermo `POST /api/cycle` is browser → Caddy → api via HTTP. gRPC could wrap bulk/sync solver calls if a future `worker` needs batch solves (`api:50051` `SolveCycle` RPC).

## gRPC Sketch (optional, not yet wired for solver)

If a server-side worker needs solver access without HTTP:

```protobuf
service ThermoService {
 rpc SolveCycle(SolveCycleRequest) returns (SolveCycleResponse);
}
```

Servicer would call the same `api.thermo.solver.solve_cycle` as the HTTP route; Caddy would keep `handle /api/cycle` as the public surface, while `melereview_api:50051` serves internal batch calls.
