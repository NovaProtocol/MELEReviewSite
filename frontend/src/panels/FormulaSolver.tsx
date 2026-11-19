import { useMemo, useState } from "react";
import { post, useApi } from "../api";
import { useSolution } from "../workspace/useSolution";

/* Formulas you can put numbers into.

   The catalogue is a list of equations with named variables, not pictures: enter the
   ones you know and the solver finds the one you do not. "Add to solution" writes the
   three lines a reader would otherwise type by hand — the formula, the same formula
   with the numbers in, and the answer — because retyping LaTeX is the part nobody
   wants to do while working a problem. */

type Variable = { label: string; unit: string; value?: string };

type Formula = {
  id: number;
  slug: string;
  name: string;
  section: string;
  equation: string;
  variables: Record<string, Variable>;
  notes: string;
};

export function FormulaSolverPanel() {
  const { data, loading, error } = useApi<{ results: Formula[] }>("/api/formulas/list");
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<Formula | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [unknown, setUnknown] = useState<string>("");
  const [answer, setAnswer] = useState<number | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const solution = useSolution();

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const all = data?.results ?? [];
    if (!needle) return all;
    return all.filter((formula) =>
      `${formula.name} ${formula.section} ${formula.equation}`.toLowerCase().includes(needle)
    );
  }, [data, query]);

  function pick(formula: Formula) {
    setChosen(formula);
    setProblem("");
    setAnswer(null);
    // Constants carry a default; everything else starts blank.
    const next: Record<string, string> = {};
    for (const [symbol, variable] of Object.entries(formula.variables)) {
      if (variable.value) next[symbol] = variable.value;
    }
    setValues(next);
    setUnknown(Object.keys(formula.variables)[0]);
  }

  async function solve() {
    if (!chosen) return;
    setBusy(true);
    setProblem("");
    setAnswer(null);
    try {
      const known: Record<string, number> = {};
      for (const [symbol, raw] of Object.entries(values)) {
        if (symbol === unknown || raw.trim() === "") continue;
        const value = Number(raw);
        if (!Number.isFinite(value)) throw new Error(`${symbol} is not a number`);
        known[symbol] = value;
      }
      const result = await post<{ value: number }>("/api/formulas/solve", {
        equation: chosen.equation,
        known,
        unknown,
      });
      setAnswer(result.value);
    } catch (error) {
      setProblem((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const markdown = useMemo(() => {
    if (!chosen || answer === null) return "";
    /* Only the knowns are replaced. The unknown keeps its symbol, because it is the
       thing being found: substituting an answer back into the left-hand side printed
       a bold 1 where the reader needs to see that P is what is being solved for. */
    const substituted = chosen.equation.replace(
      /([A-Za-z_][A-Za-z0-9_]*)/g,
      (symbol) =>
        symbol === unknown
          ? symbol
          : values[symbol] !== undefined && values[symbol] !== ""
            ? values[symbol]
            : symbol
    );
    const unit = chosen.variables[unknown]?.unit;
    return [
      `**${chosen.name}**`,
      "",
      `$$${tex(chosen.equation)}$$`,
      "",
      `$$${tex(substituted)}$$`,
      "",
      `$$${unknown} = ${round(answer)}${unit ? "\\ \\mathrm{" + unit.replace(/([%#&_])/g, "\\$1") + "}" : ""}$$`,
      chosen.notes ? `\n*${chosen.notes}*` : "",
    ]
      .filter(Boolean)
      .join("\n");
  }, [chosen, answer, values, unknown]);

  return (
    <div className="solver">
      <div className="solver__list">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search formulas"
          aria-label="Search formulas"
        />
        {loading && <p className="muted pad">Loading...</p>}
        {error && <p className="form-error pad">{error}</p>}
        <div className="solver__groups">
          {groupBySection(results).map(([section, formulas]) => (
            <div key={section} className="solver__group">
              <span className="solver__section">{section}</span>
              {formulas.map((formula) => (
                <button
                  key={formula.slug}
                  type="button"
                  className={`solver__item${chosen?.slug === formula.slug ? " is-on" : ""}`}
                  onClick={() => pick(formula)}
                >
                  <span className="solver__name">{formula.name}</span>
                  <span className="solver__equation">{formula.equation}</span>
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="solver__work">
        {!chosen ? (
          <p className="muted pad">Pick a formula on the left.</p>
        ) : (
          <>
            <header className="solver__head">
              <span className="solver__title">{chosen.name}</span>
              <span className="muted">{chosen.section}</span>
            </header>

            <p className="solver__formula">{chosen.equation}</p>

            <div className="solver__vars">
              {Object.entries(chosen.variables).map(([symbol, variable]) => (
                <label key={symbol} className="solver__var">
                  <span className="solver__symbol">{symbol}</span>
                  <span className="solver__label">
                    {variable.label}
                    {variable.unit ? ` (${variable.unit})` : ""}
                  </span>
                  <input
                    value={values[symbol] ?? ""}
                    placeholder={symbol === unknown ? "solve" : ""}
                    inputMode="decimal"
                    disabled={symbol === unknown}
                    onChange={(event) =>
                      setValues((current) => ({ ...current, [symbol]: event.target.value }))
                    }
                  />
                  <button
                    type="button"
                    className={`solver__unknown${symbol === unknown ? " is-on" : ""}`}
                    title="Solve for this one instead"
                    onClick={() => setUnknown(symbol)}
                  >
                    {symbol === unknown ? "solving" : "solve for"}
                  </button>
                </label>
              ))}
            </div>

            <div className="solver__actions">
              <button type="button" className="btn btn--primary" onClick={solve} disabled={busy}>
                {busy ? "Solving..." : "Solve"}
              </button>
              {answer !== null && (
                <button
                  type="button"
                  className="btn"
                  onClick={() => solution.add(markdown)}
                >
                  Add to solution
                </button>
              )}
            </div>

            {problem && <p className="form-error">{problem}</p>}
            {solution.notice && (
              <p className={solution.failed ? "form-error" : "muted"}>{solution.notice}</p>
            )}

            {answer !== null && (
              <p className="solver__answer">
                {unknown} = <strong>{round(answer)}</strong>{" "}
                {chosen.variables[unknown]?.unit}
              </p>
            )}

            {chosen.notes && <p className="muted solver__note">{chosen.notes}</p>}
          </>
        )}
      </div>
    </div>
  );
}

function round(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (value !== 0 && (Math.abs(value) < 1e-4 || Math.abs(value) >= 1e7)) {
    return value.toExponential(4);
  }
  return String(Number(value.toPrecision(6)));
}

function groupBySection(formulas: Formula[]): [string, Formula[]][] {
  const groups = new Map<string, Formula[]>();
  for (const formula of formulas) {
    const list = groups.get(formula.section) ?? [];
    list.push(formula);
    groups.set(formula.section, list);
  }
  return [...groups.entries()];
}

/* A reference sheet writes "*" for multiplication, which TeX shows as an asterisk.
   The markdown keeps the equation as it reads on the sheet. */
function tex(equation: string): string {
  return equation.replace(/\*/g, " \\cdot ");
}
