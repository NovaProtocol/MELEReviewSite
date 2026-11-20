import { useEffect, useMemo, useState } from "react";
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

const FIELD_LABEL: Record<string, string> = {
  P_boiler: "boiler P (Pa)",
  P_cond: "condenser P (Pa)",
  T_turbine: "turbine inlet (K)",
  T_reheat: "reheat T (K)",
  P_reheat: "reheat P (Pa)",
  bleed: "bleed fraction",
};

const AXES = ["s", "T", "h", "P", "v"];

export function DiagramsPanel() {
  const solution = useSolution();
  const [cycle, setCycle] = useState("rankine");
  const [fluid, setFluid] = useState("water");
  const [axes, setAxes] = useState<Axes>({ x: "s", y: "T" });
  const [reheat, setReheat] = useState(false);
  const [regeneration, setRegeneration] = useState(false);
  const [params, setParams] = useState<Record<string, string>>({
    P_boiler: "10000000",
    P_cond: "10000",
    T_turbine: "773.15",
    T_reheat: "773.15",
    P_reheat: "3000000",
    bleed: "0.15",
  });
  const [diagramOnly, setDiagramOnly] = useState(false);
  const [data, setData] = useState<CycleData | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  const fluids = useApi<Record<string, string>>("/api/tools/fluids");

  /* Only the parameters switched on are sent, so a plain Rankine is not asking the
     solver for a bleed fraction nobody entered. */
  const sent = useMemo(() => {
    const out: Record<string, number> = {};
    for (const key of ["P_boiler", "P_cond", "T_turbine"]) {
      const value = Number(params[key]);
      if (Number.isFinite(value) && value > 0) out[key] = value;
    }
    if (reheat) {
      out.T_reheat = Number(params.T_reheat);
      out.P_reheat = Number(params.P_reheat);
    }
    if (regeneration) out.bleed = Number(params.bleed);
    return out;
  }, [params, reheat, regeneration]);

  useEffect(() => {
    void solve();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cycle, fluid, axes.x, axes.y, reheat, regeneration, JSON.stringify(sent)]);

  async function solve() {
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
      setData(result);
      if (!result.solved) setProblem(result.missing.join("; ") || "Those inputs do not solve.");
    } catch (error) {
      setProblem((error as Error).message);
      setData(null);
    } finally {
      setBusy(false);
    }
  }

  const states = data?.states ?? [];
  const analysis = useMemo(() => analyse(states), [states]);

  return (
    <div className="diagram">
      <div className="diagram__controls">
        <div className="diagram__row">
          {CYCLES.map((option) => (
            <button
              key={option.slug}
              type="button"
              className={`chip${cycle === option.slug ? " is-on" : ""}`}
              onClick={() => setCycle(option.slug)}
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
          {Object.keys(sent).map((key) => (
            <label key={key} className="props__field">
              <span>{FIELD_LABEL[key] ?? key}</span>
              <input
                value={params[key] ?? ""}
                inputMode="decimal"
                onChange={(event) => setParams({ ...params, [key]: event.target.value })}
              />
            </label>
          ))}
        </div>
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
                      {state.quality !== null && state.quality !== undefined && state.quality >= 0
                        ? `, x = ${round(state.quality)}`
                        : ""}
                    </td>
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
function analyse(states: Point[]) {
  const phases = states.map(phaseOf);
  const lines: [string, string][] = [];
  if (states.length < 4) return { phases, lines };

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
  lines.push(["efficiency", `${round(efficiency)} %`]);
  if (net > 0) lines.push(["specific steam rate", `${round((3600 / net) * 1000)} kg/kWh`]);

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
              {index + 1}→{index + 2 > data.states.length ? 1 : index + 2}
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
