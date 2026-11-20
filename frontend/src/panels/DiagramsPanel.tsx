import { useEffect, useMemo, useRef, useState } from "react";
import { post, useApi } from "../api";
import { useSolution } from "../workspace/useSolution";

/* Cycle diagrams, drawn from the actual properties.

   The first version of this panel drew a sketch: a dome and four legs, recognisable
   as a Rankine cycle and wrong in every number. A T-s diagram whose states are not
   where the steam table puts them teaches the wrong thing, so this asks the cycle
   solver for the states and draws those, on the real saturation dome.

   The options are there because a board exam does not ask for "the Rankine cycle". It
   asks whether the steam is wet or superheated at turbine exhaust, what reheat does to
   the quality, whether the cycle with regeneration is more efficient. So the controls
   take the parameters and the panel reports what a candidate would be asked to state:
   the state of each point, the work and heat of each leg, the efficiency, and the
   specific steam rate. */

type Axes = { x: string; y: string };

type Point = {
  point?: number;
  P: number;
  T: number;
  h: number;
  s: number;
  v: number;
  /** From the property library, not guessed from the enthalpy. */
  phase?: string;
  quality?: number | null;
};

type CycleData = {
  cycle: string;
  fluid: string;
  /* The property keys actually plotted. `x_label` is the human name; using it as a
     key looked up `point["Entropy (J/kg·K)"]` and produced NaN coordinates. */
  axes: { x: string; y: string };
  x_label: string;
  y_label: string;
  solved: boolean;
  missing: string[];
  states: Point[];
  segments?: { process: string; points: Point[] }[];
  processes?: string[];
  descriptions?: string[];
  net_work?: number;
  heat_added?: number;
  turbine_work?: number;
  pump_work?: number;
  efficiency?: number;
  extras?: Record<string, number | string | boolean>;
  branches?: { from: number; to: number; process: string; description: string }[];
  dome?: { liquid_x: number[]; liquid_y: number[]; vapor_x: number[]; vapor_y: number[] };
};

const CYCLES = [
  { slug: "rankine", name: "Rankine", hint: "steam turbine plant" },
  { slug: "brayton", name: "Brayton", hint: "gas turbine" },
  { slug: "otto", name: "Otto", hint: "spark ignition" },
  { slug: "diesel", name: "Diesel", hint: "compression ignition" },
  { slug: "dual", name: "Dual", hint: "mixed diesel" },
  { slug: "carnot", name: "Carnot", hint: "reversible ideal" },
  { slug: "vapor-compression", name: "Vapour compression", hint: "refrigeration" },
];

/* What each cycle takes, with the name a person would use and a sane starting value.

   These were the solver's raw keys, which is why the panel showed "rp; T1; P1" in red:
   it was echoing the missing-parameter list without saying what any of them were. Each
   cycle has its own inputs, so sending Rankine's to Brayton left Brayton with nothing
   it could use. */
type Field = { key: string; label: string; value: string; hint?: string };

const FIELDS: Record<string, Field[]> = {
  rankine: [
    { key: "P_boiler", label: "boiler pressure", value: "10000000", hint: "Pa" },
    { key: "P_cond", label: "condenser pressure", value: "10000", hint: "Pa" },
    { key: "T_turbine", label: "turbine inlet", value: "773.15", hint: "K" },
  ],
  brayton: [
    { key: "rp", label: "pressure ratio", value: "12" },
    { key: "T1", label: "compressor inlet", value: "288.15", hint: "K" },
    { key: "P1", label: "compressor inlet", value: "101325", hint: "Pa" },
    { key: "T3", label: "turbine inlet", value: "1500", hint: "K" },
  ],
  otto: [
    { key: "r", label: "compression ratio", value: "8" },
    { key: "T1", label: "inlet", value: "300", hint: "K" },
    { key: "P1", label: "inlet", value: "100000", hint: "Pa" },
    { key: "T3", label: "peak temperature", value: "1800", hint: "K" },
  ],
  diesel: [
    { key: "r", label: "compression ratio", value: "16" },
    { key: "rc", label: "cut-off ratio", value: "2.5" },
    { key: "T1", label: "inlet", value: "300", hint: "K" },
    { key: "P1", label: "inlet", value: "100000", hint: "Pa" },
  ],
  dual: [
    { key: "r", label: "compression ratio", value: "14" },
    { key: "rc", label: "cut-off ratio", value: "1.6" },
    { key: "rp", label: "pressure ratio", value: "1.4" },
    { key: "T1", label: "inlet", value: "300", hint: "K" },
    { key: "P1", label: "inlet", value: "100000", hint: "Pa" },
  ],
  carnot: [
    { key: "T_high", label: "hot reservoir", value: "600", hint: "K" },
    { key: "T_low", label: "cold reservoir", value: "300", hint: "K" },
  ],
  "vapor-compression": [
    { key: "P_evap", label: "evaporator pressure", value: "200000", hint: "Pa" },
    { key: "P_cond", label: "condenser pressure", value: "1000000", hint: "Pa" },
    { key: "T_comp", label: "compressor inlet", value: "263.15", hint: "K" },
  ],
};

const AXES = ["s", "T", "h", "P", "v"];

export function DiagramsPanel() {
  const solution = useSolution();
  const [cycle, setCycle] = useState("rankine");
  const [fluid, setFluid] = useState("Water");
  const [axes, setAxes] = useState<Axes>({ x: "s", y: "T" });
  const [reheat, setReheat] = useState(false);
  const [regeneration, setRegeneration] = useState(false);
  const [params, setParams] = useState<Record<string, string>>(defaultsFor("rankine"));
  const [extras, setExtras] = useState<Record<string, string>>({
    T_reheat: "773.15",
    P_reheat: "3000000",
    P_bleed: "2000000",
  });
  const [diagramOnly, setDiagramOnly] = useState(false);
  const [data, setData] = useState<CycleData | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  const fluids = useApi<Record<string, string>>("/api/tools/fluids");

  /* A vapour compression cycle runs on a refrigerant. Water freezes before the
     evaporator gets cold, so switching to that cycle switches the fluid with it. */
  useEffect(() => {
    if (cycle === "vapor-compression" && fluid === "Water") setFluid("R134a");
    if (cycle !== "vapor-compression" && (fluid === "R134a" || fluid === "R410A")) {
      setFluid("Water");
    }
  }, [cycle, fluid]);

  /* Only the parameters switched on are sent, so a plain Rankine is not asking the
     solver for a bleed fraction nobody entered. */
  const sent = useMemo(() => {
    const out: Record<string, number> = {};
    for (const [key, raw] of Object.entries(params)) {
      const value = Number(raw);
      if (Number.isFinite(value)) out[key] = value;
    }
    if (cycle === "rankine" && reheat) {
      out.T_reheat = Number(extras.T_reheat);
      out.P_reheat = Number(extras.P_reheat);
    }
    if (cycle === "rankine" && regeneration) {
      out.regeneration = 1;
      out.P_bleed = Number(extras.P_bleed);
      // Reheat happens after the extraction, so it cannot sit below it.
      if (reheat) out.P_reheat = Math.max(Number(extras.P_reheat), Number(extras.P_bleed));
    }
    return out;
  }, [params, extras, cycle, reheat, regeneration]);

  useEffect(() => {
    void solve();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cycle, fluid, axes.x, axes.y, reheat, regeneration, JSON.stringify(sent)]);

  /* One solve at a time, and only the newest one may report.

     Switching cycle changes the fluid in the same breath, so two requests were in the
     air: the old one failed and set its complaint after the new one had succeeded, and
     the panel showed a working diagram under an error about the fluid it was no longer
     using. */
  const ticket = useRef(0);

  async function solve() {
    const mine = (ticket.current += 1);
    setBusy(true);
    setProblem("");
    try {
      const result = await post<CycleData>("/api/tools/cycle", {
        cycle,
        fluid,
        parameters: sent,
        diagram: axes,
        format: "data",
      });
      if (mine !== ticket.current) return;
      setData(result);
      if (result.solved) setProblem("");
      if (!result.solved) {
        const names = result.missing
          .map((key) => FIELDS[cycle]?.find((field) => field.key === key)?.label ?? key)
          .join(", ");
        setProblem(
          result.missing.length
            ? `Needs ${names || result.missing.join(", ")}.`
            : "Those inputs do not solve."
        );
      }
    } catch (error) {
      if (mine !== ticket.current) return;
      setProblem((error as Error).message);
      setData(null);
    } finally {
      if (mine === ticket.current) setBusy(false);
    }
  }

  const states = data?.states ?? [];
  const analysis = useMemo(() => analyse(states, cycle, data), [states, cycle, data]);

  return (
    <div className="diagram">
      <div className="diagram__controls">
        <div className="diagram__row">
          {CYCLES.map((option) => (
            <button
              key={option.slug}
              type="button"
              className={`chip${cycle === option.slug ? " is-on" : ""}`}
              onClick={() => {
                setCycle(option.slug);
                setParams(defaultsFor(option.slug));
                setReheat(false);
                setRegeneration(false);
              }}
              title={option.hint}
            >
              {option.name}
            </button>
          ))}
        </div>

        <div className="diagram__row">
          <label className="props__field">
            <span>fluid</span>
            <select value={fluid} onChange={(event) => setFluid(event.target.value)}>
              {Object.keys(fluids.data ?? { water: "Water" }).map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className="props__field">
            <span>x axis</span>
            <select value={axes.x} onChange={(event) => setAxes({ ...axes, x: event.target.value })}>
              {AXES.map((key) => (
                <option key={key} value={key}>
                  {key}
                </option>
              ))}
            </select>
          </label>
          <label className="props__field">
            <span>y axis</span>
            <select value={axes.y} onChange={(event) => setAxes({ ...axes, y: event.target.value })}>
              {AXES.map((key) => (
                <option key={key} value={key}>
                  {key}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="diagram__row diagram__mode">
          <label className="switch switch--small">
            <input
              type="checkbox"
              checked={diagramOnly}
              onChange={() => setDiagramOnly(!diagramOnly)}
            />
            <span className="switch__track">
              <span className="switch__dot" />
            </span>
            <span className="switch__label">diagram only</span>
          </label>
          <button type="button" className="btn" onClick={solve} disabled={busy}>
            {busy ? "Solving..." : "Solve"}
          </button>
        </div>

        {cycle === "rankine" && (
          <div className="diagram__row">
            <label className="switch switch--small">
              <input type="checkbox" checked={reheat} onChange={() => setReheat(!reheat)} />
              <span className="switch__track">
                <span className="switch__dot" />
              </span>
              <span className="switch__label">reheat</span>
            </label>
            <label className="switch switch--small">
              <input
                type="checkbox"
                checked={regeneration}
                onChange={() => setRegeneration(!regeneration)}
              />
              <span className="switch__track">
                <span className="switch__dot" />
              </span>
              <span className="switch__label">regeneration</span>
            </label>
          </div>
        )}

        <div className="diagram__row diagram__params">
          {(FIELDS[cycle] ?? []).map((field) => (
            <label key={field.key} className="props__field">
              <span>
                {field.label}
                {field.hint ? ` (${field.hint})` : ""}
              </span>
              <input
                value={params[field.key] ?? ""}
                inputMode="decimal"
                onChange={(event) => setParams({ ...params, [field.key]: event.target.value })}
              />
            </label>
          ))}
        </div>

        {cycle === "rankine" && regeneration && (
          <div className="diagram__row diagram__params">
            <label className="props__field">
              <span>extraction pressure (Pa)</span>
              <input
                value={extras.P_bleed}
                inputMode="decimal"
                onChange={(event) => setExtras({ ...extras, P_bleed: event.target.value })}
              />
            </label>
          </div>
        )}
        {cycle === "rankine" && reheat && (
          <div className="diagram__row diagram__params">
            <label className="props__field">
              <span>reheat temperature (K)</span>
              <input
                value={extras.T_reheat}
                inputMode="decimal"
                onChange={(event) => setExtras({ ...extras, T_reheat: event.target.value })}
              />
            </label>
            <label className="props__field">
              <span>reheat pressure (Pa)</span>
              <input
                value={extras.P_reheat}
                inputMode="decimal"
                onChange={(event) => setExtras({ ...extras, P_reheat: event.target.value })}
              />
            </label>
          </div>
        )}
      </div>

      {busy && <p className="muted pad">Solving...</p>}
      {problem && <p className="form-error pad">{problem}</p>}

      {data?.solved && (
        <div className={`diagram__body${diagramOnly ? " is-diagram-only" : ""}`}>
          <CycleChart data={data} />

          {!diagramOnly && (
            <>
              <table className="props__table diagram__states">
                <thead>
                  <tr>
                    <th>point</th>
                    <th>P (MPa)</th>
                    <th>T (K)</th>
                    <th>T (°C)</th>
                    <th>h (kJ/kg)</th>
                    <th>s (kJ/kg·K)</th>
                    <th>state</th>
                    <th>leg</th>
                  </tr>
                </thead>
                <tbody>
                  {states.map((state, index) => (
                    <tr key={index}>
                      <td>{index + 1}</td>
                      <td>{round(state.P / 1e6)}</td>
                      <td>{round(state.T)}</td>
                      <td>{round(state.T - 273.15)}</td>
                      <td>{round(state.h / 1000)}</td>
                      <td>{round(state.s / 1000)}</td>
                      <td>
                        {state.phase ?? analysis.phases[index]}
                        {state.quality !== null &&
                        state.quality !== undefined &&
                        state.quality >= 0
                          ? `, x = ${round(state.quality)}`
                          : ""}
                      </td>
                      <td className="muted">{(data.descriptions ?? [])[index] ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <dl className="diagram__analysis">
                {analysis.lines.map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
            </>
          )}

          <div className="diagram__actions">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => solution.add(markdown(data, analysis, axes, sent, diagramOnly))}
            >
              {diagramOnly ? "Add diagram to solution" : "Add to solution"}
            </button>
            {solution.notice && (
              <span className={solution.failed ? "form-error" : "muted"}>{solution.notice}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* What a candidate is asked to state, worked out from the states.

   The numbers come from the solver rather than a remembered efficiency formula: the
   work of each leg is the enthalpy change along it. Doing it from the states means the
   answer is right for reheat too, where there is no single formula to quote. */
function analyse(states: Point[], cycle: string, data: CycleData | null) {
  const phases = states.map(phaseOf);
  const lines: [string, string][] = [];
  if (states.length < 4) return { phases, lines };

  /* A power cycle and a refrigerator have the same four legs but different jobs, and
     guessing which leg is which from the pressures alone called the evaporator a
     boiler. The refrigeration legs are fixed by the cycle, so they are named rather
     than inferred: compressor, condenser, expansion valve, evaporator. */
  const refrigeration = cycle === "vapor-compression";

  if (refrigeration) {
    const [evaporatorOut, compressorOut, condenserOut, valveOut] = states;
    const work = (compressorOut.h - evaporatorOut.h) / 1000;
    const rejected = (compressorOut.h - condenserOut.h) / 1000;
    const cooling = (evaporatorOut.h - valveOut.h) / 1000;
    const cop = work > 0 ? cooling / work : 0;
    lines.push(["cooling", `${round(cooling)} kJ/kg`]);
    lines.push(["work in", `${round(work)} kJ/kg`]);
    lines.push(["heat rejected", `${round(rejected)} kJ/kg`]);
    lines.push(["COP", `${round(cop)}`]);
    lines.push([
      "as a heat pump",
      `${round(work > 0 ? (cooling + work) / work : 0)}`,
    ]);
    const valveQuality = states[3]?.quality;
    if (valveQuality !== null && valveQuality !== undefined && valveQuality >= 0) {
      lines.push(["quality after the valve", `x = ${round(valveQuality)}`]);
    } else {
      lines.push(["quality after the valve", "superheated vapour"]);
    }
    return { phases, lines };
  }

  let workOut = 0;
  let workIn = 0;
  let heatIn = 0;

  for (let index = 0; index < states.length - 1; index += 1) {
    const from = states[index];
    const to = states[index + 1];
    const delta = (to.h - from.h) / 1000;
    if (to.P < from.P * 0.999) workOut += -delta;
    else if (to.P > from.P * 1.001) workIn += delta;
    else heatIn += delta;
  }
  const heatOut = (states[states.length - 1].h - states[0].h) / 1000;

  const net = workOut - workIn;
  const efficiency = heatIn > 0 ? (net / heatIn) * 100 : 0;

  lines.push(["work out", `${round(workOut)} kJ/kg`]);
  lines.push(["work in", `${round(workIn)} kJ/kg`]);
  lines.push(["net work", `${round(net)} kJ/kg`]);
  lines.push(["heat added", `${round(heatIn)} kJ/kg`]);
  lines.push(["heat rejected", `${round(heatOut)} kJ/kg`]);
  /* The solver's totals, when it has them. Summing the state enthalpies cannot see
     that a fraction of the steam left the turbine early: past a bleed, one kilogram of
     state change no longer stands for one kilogram of steam. */
  const solvedNet = data?.net_work;
  const solvedHeat = data?.heat_added;
  if (solvedNet !== null && solvedNet !== undefined) {
    lines.length = 0;
    if (data?.turbine_work) lines.push(["turbine work", `${round(data.turbine_work / 1000)} kJ/kg`]);
    if (data?.pump_work) lines.push(["pump work", `${round(data.pump_work / 1000)} kJ/kg`]);
    lines.push(["net work", `${round(solvedNet / 1000)} kJ/kg`]);
    if (solvedHeat) lines.push(["heat added", `${round(solvedHeat / 1000)} kJ/kg`]);
    if (data?.efficiency) lines.push(["efficiency", `${round(data.efficiency * 100)} %`]);
    if (solvedHeat && solvedNet > 0) {
      lines.push(["specific steam rate", `${round((3600 / (solvedNet / 1000)) * 1000)} kg/kWh`]);
    }
    for (const [key, value] of Object.entries(data?.extras ?? {})) {
      if (typeof value === "boolean") {
        if (value) lines.push([key, "yes"]);
      } else {
        lines.push([key, String(value)]);
      }
    }
  } else {
    lines.push(["efficiency", `${round(efficiency)} %`]);
    if (net > 0) lines.push(["specific steam rate", `${round((3600 / net) * 1000)} kg/kWh`]);
  }

  const exhaust = states[states.length - 1];
  const quality = exhaust.quality ?? null;
  if (quality !== null && quality >= 0) {
    lines.push([
      "turbine exhaust",
      quality < 1 ? `wet, x = ${round(quality)}` : "superheated",
    ]);
    if (quality < 0.88) {
      lines.push(["warning", "below the 88% usually wanted, so reheat is warranted"]);
    }
  }
  return { phases, lines };
}

/* Only a fallback for a payload without a phase: the real answer comes from the
   property library with the states. */
function phaseOf(state: Point): string {
  if (state.P > 22.064e6) return "supercritical";
  if (state.h > 2_400_000) return "superheated";
  if (state.h < 1_000_000) return "liquid";
  return "mixture";
}

function CycleChart({ data }: { data: CycleData }) {
  const width = 480;
  const height = 300;
  const pad = { left: 46, right: 12, top: 12, bottom: 30 };

  const bounds = useMemo(() => {
    const xs: number[] = [];
    const ys: number[] = [];
    for (const segment of data.segments ?? []) {
      for (const point of segment.points) {
        xs.push(point[data.axes.x as keyof Point] as number);
        ys.push(point[data.axes.y as keyof Point] as number);
      }
    }
    if (data.dome) {
      xs.push(...data.dome.liquid_x, ...data.dome.vapor_x);
      ys.push(...data.dome.liquid_y, ...data.dome.vapor_y);
    }
    for (const branch of data.branches ?? []) {
      const from = data.states[branch.from - 1];
      const to = data.states[branch.to - 1];
      if (!from || !to) continue;
      xs.push(from[data.axes.x as keyof Point] as number, to[data.axes.x as keyof Point] as number);
      ys.push(from[data.axes.y as keyof Point] as number, to[data.axes.y as keyof Point] as number);
    }
    if (!xs.length) return null;
    return {
      xMin: Math.min(...xs),
      xMax: Math.max(...xs),
      yMin: Math.min(...ys),
      yMax: Math.max(...ys),
    };
  }, [data]);

  if (!bounds) return null;
  const { xMin, xMax, yMin, yMax } = bounds;
  const sx = (value: number) =>
    pad.left + ((value - xMin) / (xMax - xMin || 1)) * (width - pad.left - pad.right);
  const sy = (value: number) =>
    height - pad.bottom - ((value - yMin) / (yMax - yMin || 1)) * (height - pad.top - pad.bottom);
  const path = (xs: number[], ys: number[]) =>
    xs.map((x, index) => `${index ? "L" : "M"}${sx(x).toFixed(1)},${sy(ys[index]).toFixed(1)}`).join(" ");

  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${width} ${height}`} className="chart__svg" role="img">
        <rect
          x={pad.left}
          y={pad.top}
          width={width - pad.left - pad.right}
          height={height - pad.top - pad.bottom}
          className="chart__plot"
        />
        {marks(yMin, yMax, 4).map((value) => (
          <g key={`y${value}`}>
            <line x1={pad.left} x2={width - pad.right} y1={sy(value)} y2={sy(value)} className="chart__grid" />
            <text
              x={pad.left - 6}
              y={sy(value)}
              className="chart__tick"
              textAnchor="end"
              dominantBaseline="middle"
            >
              {round(value)}
            </text>
          </g>
        ))}
        {marks(xMin, xMax, 4).map((value) => (
          <g key={`x${value}`}>
            <line y1={pad.top} y2={height - pad.bottom} x1={sx(value)} x2={sx(value)} className="chart__grid" />
            <text x={sx(value)} y={height - pad.bottom + 13} className="chart__tick" textAnchor="middle">
              {round(value)}
            </text>
          </g>
        ))}

        {data.dome && (
          <path
            d={path(
              [...data.dome.liquid_x, ...data.dome.vapor_x.slice().reverse()],
              [...data.dome.liquid_y, ...data.dome.vapor_y.slice().reverse()]
            )}
            className="chart__dome"
          />
        )}

        {/* Steam that leaves the loop: the bleed to the feedwater heater. Drawn
            dashed, because it is not part of the cycle the turbine sees. */}
        {(data.branches ?? []).map((branch, index) => {
          const from = data.states[branch.from - 1];
          const to = data.states[branch.to - 1];
          if (!from || !to) return null;
          const x1 = sx(from[data.axes.x as keyof Point] as number);
          const y1 = sy(from[data.axes.y as keyof Point] as number);
          const x2 = sx(to[data.axes.x as keyof Point] as number);
          const y2 = sy(to[data.axes.y as keyof Point] as number);
          return (
            <g key={`branch${index}`}>
              <line x1={x1} y1={y1} x2={x2} y2={y2} className="chart__branch" />
              <text
                x={(x1 + x2) / 2}
                y={(y1 + y2) / 2 - 4}
                className="chart__branch-label"
                textAnchor="middle"
              >
                bleed
              </text>
            </g>
          );
        })}

        {(data.segments ?? []).map((segment, index) => (
          <path
            key={index}
            d={path(
              segment.points.map((point) => point[data.axes.x as keyof Point] as number),
              segment.points.map((point) => point[data.axes.y as keyof Point] as number)
            )}
            className="chart__process"
          />
        ))}

        {(data.segments ?? []).map((segment, index) => {
          if (segment.points.length < 2) return null;
          const middle = Math.floor(segment.points.length / 2);
          return (
            <text
              key={`label${index}`}
              x={sx(segment.points[middle][data.axes.x as keyof Point] as number)}
              y={sy(segment.points[middle][data.axes.y as keyof Point] as number) - 5}
              className="chart__process-label"
              textAnchor="middle"
            >
              {index + 1}→{(index + 1) % data.states.length + 1}
            </text>
          );
        })}

        {data.states.map((state, index) => {
          const value = state[data.axes.x as keyof Point] as number;
          const other = state[data.axes.y as keyof Point] as number;
          return (
            <g key={index}>
              <circle cx={sx(value)} cy={sy(other)} r={3.4} className="chart__point" />
              <text x={sx(value) + 6} y={sy(other) - 5} className="chart__state-label">
                {index + 1}
              </text>
            </g>
          );
        })}

        <text
          x={(pad.left + width - pad.right) / 2}
          y={height - 3}
          className="chart__axis"
          textAnchor="middle"
        >
          {data.x_label}
        </text>
      </svg>
    </figure>
  );
}

function defaultsFor(cycle: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const field of FIELDS[cycle] ?? []) out[field.key] = field.value;
  return out;
}

function marks(min: number, max: number, count: number): number[] {
  const step = (max - min) / count || 1;
  return Array.from({ length: count + 1 }, (_, index) => min + step * index);
}

function round(value: number): string {
  if (!Number.isFinite(value)) return "-";
  const magnitude = Math.abs(value);
  if (magnitude !== 0 && (magnitude < 0.01 || magnitude >= 1e6)) return value.toExponential(3);
  return String(Number(value.toPrecision(magnitude > 100 ? 5 : 4)));
}

function markdown(
  data: CycleData,
  analysis: { lines: [string, string][] },
  axes: Axes,
  sent: Record<string, number>,
  diagramOnly: boolean
): string {
  const heading = `**${data.cycle.replace("-", " ")} cycle, ${data.fluid}**`;
  const image = `![${data.cycle} ${axes.x}-${axes.y}](${chartUrl(data, axes, sent)})`;
  if (diagramOnly) {
    return [
      heading,
      "",
      image,
      "",
      ...analysis.lines
        .filter(([label]) => ["efficiency", "net work", "turbine exhaust"].includes(label))
        .map(([label, value]) => `- ${label}: ${value}`),
    ].join("\n");
  }
  return [
    heading,
    "",
    "| point | P (MPa) | T (K) | h (kJ/kg) | s (kJ/kg·K) |",
    "| --- | --- | --- | --- | --- |",
    ...data.states.map(
      (state, index) =>
        `| ${index + 1} | ${round(state.P / 1e6)} | ${round(state.T)} | ${round(state.h / 1000)} | ${round(state.s / 1000)} |`
    ),
    "",
    ...analysis.lines.map(([label, value]) => `- ${label}: ${value}`),
    "",
    image,
  ].join("\n");
}

/* The diagram is a URL so it can be redrawn later without this panel: everything
   needed to reproduce it travels in the link. The endpoint re-solves the cycle and
   draws it, so a link made today still draws tomorrow. */
function chartUrl(data: CycleData, axes: Axes, sent: Record<string, number>): string {
  const settings = { x: axes.x, y: axes.y, fluid: data.fluid, parameters: sent };
  return `/api/charts/cycle/${data.cycle}?override_data=${encodeURIComponent(btoa(JSON.stringify(settings)))}`;
}
