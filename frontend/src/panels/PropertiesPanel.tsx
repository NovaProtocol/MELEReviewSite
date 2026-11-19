import { useMemo, useState } from "react";
import { api, post } from "../api";
import { appendToSolution } from "../workspace/solutionBus";

/* Property tables, in the client rather than in a page.

   The numbers come from the tool API; nothing here is rendered by a template. Steam
   is read from the CoolProp-backed service that already answers for several fluids,
   and moist air from the psychrometric endpoint.

   Every row can go into a solution. A steam-table question is mostly transcription,
   and transcription is where marks are lost. */

type SteamTable = {
  basis: string;
  fluid: string;
  rows: Record<string, number | string>[];
};

type SteamState = Record<string, number | string | null>;

type MoistAir = {
  dry_bulb_c: number;
  relative_humidity_pct: number;
  humidity_ratio_g_per_kg: number;
  enthalpy_kj_per_kg: number;
  specific_volume_m3_per_kg: number;
  dew_point_c: number;
  wet_bulb_c: number;
  vapour_pressure_kpa: number;
  saturation_pressure_kpa: number;
};

const HEADING: Record<string, string> = {
  temperature: "T (°C)",
  pressure: "P",
  vf: "v_f",
  vg: "v_g",
  uf: "u_f",
  ug: "u_g",
  hf: "h_f",
  hg: "h_g",
  sf: "s_f",
  sg: "s_g",
  v: "v",
  u: "u",
  h: "h",
  s: "s",
  x: "x",
};

export function PropertiesPanel() {
  const [tab, setTab] = useState<"steam" | "air">("steam");

  return (
    <div className="props">
      <div className="props__tabs">
        <button
          type="button"
          className={`chip${tab === "steam" ? " is-on" : ""}`}
          onClick={() => setTab("steam")}
        >
          Steam
        </button>
        <button
          type="button"
          className={`chip${tab === "air" ? " is-on" : ""}`}
          onClick={() => setTab("air")}
        >
          Moist air
        </button>
      </div>
      {tab === "steam" ? <SteamTab /> : <AirTab />}
    </div>
  );
}

function SteamTab() {
  const [basis, setBasis] = useState<"temperature" | "pressure">("temperature");
  const [start, setStart] = useState("100");
  const [stop, setStop] = useState("180");
  const [fluid, setFluid] = useState("Water");
  const [table, setTable] = useState<SteamTable | null>(null);
  const [state, setState] = useState<SteamState | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadTable() {
    setBusy(true);
    setProblem("");
    try {
      setTable(
        await api<SteamTable>(
          `/api/tools/steam/table?basis=${basis}&start=${Number(start) || 0}&stop=${
            Number(stop) || 0
          }&count=12&fluid=${encodeURIComponent(fluid)}`
        )
      );
    } catch (error) {
      setProblem((error as Error).message);
      setTable(null);
    } finally {
      setBusy(false);
    }
  }

  async function loadState() {
    setBusy(true);
    setProblem("");
    try {
      const response = await post<{ state: SteamState }>("/api/tools/steam/state", {
        fluid,
        pressure: Number(start) || 0.1,
        temperature: Number(stop) || 100,
      });
      setState(response.state);
    } catch (error) {
      setProblem((error as Error).message);
      setState(null);
    } finally {
      setBusy(false);
    }
  }

  const columns = useMemo(() => {
    const rows = table?.rows ?? [];
    if (!rows.length) return [];
    return Object.keys(rows[0]).filter((key) => typeof rows[0][key] !== "string");
  }, [table]);

  return (
    <>
      <div className="props__row">
        <div className="props__seg">
          {(["temperature", "pressure"] as const).map((option) => (
            <button
              key={option}
              type="button"
              className={`chip${basis === option ? " is-on" : ""}`}
              onClick={() => setBasis(option)}
            >
              by {option}
            </button>
          ))}
        </div>
        <label className="props__field">
          <span>{basis === "temperature" ? "T from (°C)" : "P from (MPa)"}</span>
          <input value={start} inputMode="decimal" onChange={(event) => setStart(event.target.value)} />
        </label>
        <label className="props__field">
          <span>{basis === "temperature" ? "T to (°C)" : "P to (MPa)"}</span>
          <input value={stop} inputMode="decimal" onChange={(event) => setStop(event.target.value)} />
        </label>
        <label className="props__field">
          <span>fluid</span>
          <select value={fluid} onChange={(event) => setFluid(event.target.value)}>
            {["Water", "R134a", "R410A", "Ammonia"].map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="btn btn--primary" onClick={loadTable} disabled={busy}>
          {busy ? "Working..." : "Saturation table"}
        </button>
        <button type="button" className="btn" onClick={loadState} disabled={busy}>
          State at these two
        </button>
      </div>

      {problem && <p className="form-error">{problem}</p>}

      {table && (
        <div className="props__scroll">
          <table className="props__table">
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column}>{HEADING[column] ?? column}</th>
                ))}
                <th />
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, index) => (
                <tr key={index}>
                  {columns.map((column) => (
                    <td key={column}>{number(row[column])}</td>
                  ))}
                  <td>
                    <button
                      type="button"
                      className="link"
                      onClick={() =>
                        appendToSolution(
                          [
                            `**Saturated ${table.fluid}**`,
                            "",
                            ...columns.map(
                              (column) => `- $${HEADING[column] ?? column} = ${number(row[column])}$`
                            ),
                          ].join("\n")
                        )
                      }
                    >
                      add
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {state && (
        <div className="props__result">
          <span className="props__phase">{String(state.phase ?? "")}</span>
          <dl>
            {Object.entries(state)
              .filter(([key, value]) => key !== "phase" && value !== null && value !== undefined)
              .map(([key, value]) => (
                <div key={key}>
                  <dt>{HEADING[key] ?? key}</dt>
                  <dd>{number(value as number)}</dd>
                </div>
              ))}
          </dl>
          <button
            type="button"
            className="btn"
            onClick={() =>
              appendToSolution(
                [
                  `**${fluid} state** (${String(state.phase ?? "")})`,
                  "",
                  ...Object.entries(state)
                    .filter(([key, value]) => key !== "phase" && value)
                    .map(([key, value]) => `- $${HEADING[key] ?? key} = ${number(value as number)}$`),
                ].join("\n")
              )
            }
          >
            Add to solution
          </button>
        </div>
      )}
    </>
  );
}

function AirTab() {
  const [dryBulb, setDryBulb] = useState("30");
  const [rh, setRh] = useState("60");
  const [pressure, setPressure] = useState("101.325");
  const [result, setResult] = useState<MoistAir | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  async function compute() {
    setBusy(true);
    setProblem("");
    try {
      setResult(
        await api<MoistAir>(
          `/api/tools/psychrometric?dry_bulb=${Number(dryBulb) || 0}&rh=${
            (Number(rh) || 0) / 100
          }&pressure=${Number(pressure) || 101.325}`
        )
      );
    } catch (error) {
      setProblem((error as Error).message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="props__row">
        <label className="props__field">
          <span>dry bulb (°C)</span>
          <input value={dryBulb} inputMode="decimal" onChange={(event) => setDryBulb(event.target.value)} />
        </label>
        <label className="props__field">
          <span>RH (%)</span>
          <input value={rh} inputMode="decimal" onChange={(event) => setRh(event.target.value)} />
        </label>
        <label className="props__field">
          <span>P (kPa)</span>
          <input value={pressure} inputMode="decimal" onChange={(event) => setPressure(event.target.value)} />
        </label>
        <button type="button" className="btn btn--primary" onClick={compute} disabled={busy}>
          {busy ? "Working..." : "Work it out"}
        </button>
      </div>

      {problem && <p className="form-error">{problem}</p>}

      {result && (
        <div className="props__result">
          <dl>
            {(
              [
                ["humidity ratio", `${result.humidity_ratio_g_per_kg} g/kg dry air`],
                ["enthalpy", `${result.enthalpy_kj_per_kg} kJ/kg dry air`],
                ["specific volume", `${result.specific_volume_m3_per_kg} m³/kg`],
                ["dew point", `${result.dew_point_c} °C`],
                ["wet bulb", `${result.wet_bulb_c} °C`],
                ["vapour pressure", `${result.vapour_pressure_kpa} kPa`],
                ["saturation pressure", `${result.saturation_pressure_kpa} kPa`],
              ] as [string, string][]
            ).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          <button
            type="button"
            className="btn"
            onClick={() =>
              appendToSolution(
                [
                  `**Moist air** — ${result.dry_bulb_c} °C dry bulb, ${result.relative_humidity_pct}% RH`,
                  "",
                  `$$W = ${result.humidity_ratio_g_per_kg}\\ \\mathrm{g/kg_{dry\\ air}}$$`,
                  "",
                  `$$h = ${result.enthalpy_kj_per_kg}\\ \\mathrm{kJ/kg}$$`,
                  "",
                  `$$T_{dew} = ${result.dew_point_c}\\ ^\\circ\\mathrm{C},\\quad T_{wb} = ${result.wet_bulb_c}\\ ^\\circ\\mathrm{C}$$`,
                ].join("\n")
              )
            }
          >
            Add to solution
          </button>
        </div>
      )}
    </>
  );
}

function number(value: unknown): string {
  if (typeof value !== "number") return String(value ?? "");
  if (!Number.isFinite(value)) return "—";
  if (value !== 0 && (Math.abs(value) < 1e-4 || Math.abs(value) >= 1e5)) {
    return value.toExponential(3);
  }
  return String(Number(value.toPrecision(6)));
}
