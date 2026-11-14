# Study Tools

The calculators are no longer their own section of the site. They live in a rail on the right of
every signed-in page, and the rail is searchable.

## The rail

`_shell/base.html` provides the page chrome; `base.html` adds the rail:

```html
<aside class="tools-rail" id="tools-rail">
  <div class="rail-search"><input type="search" id="rail-search"></div>
  <ul class="rail-list" id="rail-list"></ul>
  <div class="rail-frame-wrap" id="rail-frame-wrap" hidden>
    <iframe id="rail-frame"></iframe>
  </div>
</aside>
```

The catalogue is rendered into a `<meta>` tag on every page and read by `app.js`, so the rail is
complete without a round trip. Search matches the name, the group and a keyword list.

| Query | Opens |
|---|---|
| `convert` | Unit converter |
| `carnot` | Thermo cycle solver, and its Carnot inputs |
| `pump` | Pipe flow |
| `psychro` | Psychrometrics |
| `belt` | Machine elements |

Picking a tool loads `/tools/<slug>` into the iframe. Each tool page is a standalone document that
extends `tools/_embed.html`: no navbar, no footer, `min-height: 100dvh`, its own stylesheet. That
keeps the calculator JS, its element ids and Plotly isolated from the app shell. Rewriting six
calculators to be inline widgets would have changed nothing a member can see.

On a viewport narrower than 1100px the rail becomes a drawer, opened by the **Tools** button in the
navbar and dismissed with Escape, the backdrop or the close button. Above that width it sits open as
a column and the main content gives way to it.

## The catalogue

| Slug | Name | What it does |
|---|---|---|
| `unit` | Unit converter | Quantity, value, from, to |
| `thermo` | Thermo cycle solver | Seven cycles, T-s and P-v diagrams, state table |
| `fluids` | Pipe flow | Velocity, Reynolds number, friction factor, head loss, pump power |
| `heat` | Heat transfer | Conduction through a plane wall, convection |
| `strength` | Strength of materials | Axial stress and strain, centre-loaded beam, shaft torsion |
| `psychro` | Psychrometrics | Dry-bulb and relative humidity, plus mixing two streams |
| `machine` | Machine elements | Gear ratio, belt drive, power transmission |

The catalogue is `TOOLS` in `app/routes/tools.py`: slug, name, group and keywords. Adding a tool is a
template at `app/templates/tools/<slug>.html` extending `tools/_embed.html`, a script if it needs
one, and one entry in that tuple.

## The cycle solver

`POST /api/tools/cycle` requires a session. It solves with CoolProp rather than steam tables, so a
fluid is a parameter (`water`, `r134a`, `r410a`, `air`) and the state points come back with `P`,
`T`, `h`, `s` and `v`.

| Cycle | Parameters |
|---|---|
| Carnot | `T_high`, `T_low`, `P1`, `r_exp` |
| Otto | `r`, `T1`, `P1`, `T3` |
| Diesel | `r`, `rc`, `T1`, `P1` |
| Dual | `r`, `rc`, `rp`, `T1`, `P1` |
| Rankine | `P_boiler`, `P_cond`, `T_turbine` |
| Brayton | `rp`, `T1`, `P1`, `T3` |
| Vapor compression | `P_evap`, `P_cond`, `T_comp` |

`format: "plot"` returns segments and a saturation dome for the chosen axes; the default returns
states and segments. `_guard` rejects a result containing a non-finite value and reports it as
"inputs are outside the fluid property limits" instead of plotting nonsense.

The solver itself is `app/thermo/`: `props.py` for state resolution, `solvers/` for one module per
cycle, `plot.py` for the geometry. It is pure Python over CoolProp, which is why the tests exercise
it directly rather than through the page.

## Tests

`tests/test_tools.py` solves every cycle and checks it converges with finite states, asserts the
endpoint refuses an anonymous caller, and checks that every element id the calculator scripts touch
exists in the template that hosts them. That last one is the contract between the two, and it fails
here rather than in a browser.
