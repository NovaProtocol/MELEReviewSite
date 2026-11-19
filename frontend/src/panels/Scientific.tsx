import { useMemo, useState } from "react";
import { compile, format, normalise, solve, type AngleMode } from "../calc/engine";
import { useSolution } from "../workspace/useSolution";

/* One calculator, three faces.

   The photographed machines — a Casio fx-991ES PLUS, an fx-82ES PLUS, a Canon
   F-789SGA — differ in printing, not in arithmetic. Sine is sine. So the brain is
   the shared engine and a skin only supplies the legend, the accent and the order of
   the keys; switching skin cannot change a result, which is the point.

   SHIFT-SOLVE gets first-class treatment because it is the reason a board exam
   candidate wants a scientific calculator at all: the equation is given, the
   rearranging is the time sink, and four possible answers are printed. Type the
   equation with X in it, SHIFT, SOLVE, and it hands back X. */

type SkinName = "fx-991ES" | "fx-82ES" | "F-789SGA";

type Skin = {
  name: SkinName;
  brand: string;
  model: string;
  note: string;
};

const SKINS: Skin[] = [
  { name: "fx-991ES", brand: "CASIO", model: "fx-991ES PLUS", note: "NATURAL-V.P.A.M." },
  { name: "fx-82ES", brand: "CASIO", model: "fx-82ES PLUS", note: "NATURAL-V.P.A.M." },
  { name: "F-789SGA", brand: "Canon", model: "F-789SGA", note: "" },
];

type Key = {
  /** Primary legend. */
  label: string;
  /** What SHIFT turns it into, printed above the key. */
  shift?: string;
  /** What the key inserts; defaults to the label. */
  insert?: string;
  /** Amber function when ALPHA is held. */
  alpha?: string;
  action?: "shift" | "alpha" | "solve" | "equals" | "clear" | "delete" | "mode" | "memory";
  wide?: boolean;
};

/* The keypad as a calculator has it: functions on top, digits in a 3×3 block, and
   the two big keys at the bottom right. */
const PAD: Key[][] = [
  [
    { label: "SHIFT", action: "shift" },
    { label: "ALPHA", action: "alpha" },
    { label: "▲" },
    { label: "MODE", action: "mode" },
    { label: "ON", action: "clear" },
  ],
  [
    { label: "CALC", shift: "SOLVE", action: "solve" },
    { label: "x⁻¹", insert: "^(-1)" },
    { label: "nCr", insert: "nCr(" },
    { label: "POL", insert: "pol(" },
    { label: "x³", insert: "^3" },
  ],
  [
    { label: "√", shift: "∛", insert: "√(" },
    { label: "x²", insert: "^2" },
    { label: "x^", insert: "^" },
    { label: "log", shift: "10^", insert: "log(" },
    { label: "ln", shift: "e^", insert: "ln(" },
  ],
  [
    { label: "(-)", insert: "-" },
    { label: "°'\"", insert: "°" },
    { label: "hyp", insert: "sinh(" },
    { label: "sin", shift: "sin⁻¹", insert: "sin(" },
    { label: "cos", shift: "cos⁻¹", insert: "cos(" },
  ],
  [
    { label: "RCL", shift: "STO", action: "memory" },
    { label: "ENG", insert: "E" },
    { label: "(", insert: "(" },
    { label: ")", insert: ")" },
    { label: "M+", action: "memory" },
  ],
  [
    { label: "7" },
    { label: "8" },
    { label: "9" },
    { label: "DEL", action: "delete" },
    { label: "AC", action: "clear" },
  ],
  [
    { label: "4" },
    { label: "5" },
    { label: "6" },
    { label: "×", insert: "×" },
    { label: "÷", insert: "÷" },
  ],
  [
    { label: "1" },
    { label: "2" },
    { label: "3" },
    { label: "+", insert: "+" },
    { label: "−", insert: "−" },
  ],
  [
    { label: "0" },
    { label: "." },
    { label: "×10^", insert: "E" },
    { label: "Ans", insert: "Ans" },
    { label: "=", action: "equals" },
  ],
];

type Entry = { expression: string; result: string; error?: boolean };

export function Scientific() {
  const [skin, setSkin] = useState<Skin>(SKINS[0]);
  const [expression, setExpression] = useState("");
  const [angle, setAngle] = useState<AngleMode>("DEG");
  const [shift, setShift] = useState(false);
  const [alpha, setAlpha] = useState(false);
  const [answer, setAnswer] = useState(0);
  const [history, setHistory] = useState<Entry[]>([]);
  const [solved, setSolved] = useState<{ x: number; residual: number } | null>(null);
  const [error, setError] = useState("");
  const solution = useSolution();

  const preview = useMemo(() => {
    if (!expression.trim()) return "";
    try {
      return format(compile(expression, angle === "DEG").evaluate({}));
    } catch {
      return "";
    }
  }, [expression, angle]);

  function insert(text: string) {
    setSolved(null);
    setError("");
    setExpression((current) => current + text);
  }

  function press(key: Key) {
    if (key.action === "shift") {
      setShift((current) => !current);
      return;
    }
    if (key.action === "alpha") {
      setAlpha((current) => !current);
      return;
    }
    if (key.action === "clear") {
      setExpression("");
      setSolved(null);
      setError("");
      setShift(false);
      return;
    }
    if (key.action === "delete") {
      setExpression((current) => current.slice(0, -1));
      return;
    }
    if (key.action === "mode") {
      setAngle((current) => (current === "DEG" ? "RAD" : "DEG"));
      return;
    }
    if (key.action === "memory") {
      return;
    }
    if (key.action === "equals") {
      commit();
      return;
    }
    if (key.action === "solve") {
      if (shift) solveForX();
      else commit();
      return;
    }
    insert(key.insert ?? key.label);
  }

  function commit() {
    const source = expression.trim();
    if (!source) return;
    try {
      const value = compile(source, angle === "DEG").evaluate({});
      setAnswer(value);
      setHistory((current) =>
        [{ expression: source, result: format(value) }, ...current].slice(0, 50)
      );
      setExpression(format(value));
      setError("");
    } catch (problem) {
      setError((problem as Error).message);
      setHistory((current) =>
        [{ expression: source, result: (problem as Error).message, error: true }, ...current].slice(
          0,
          50
        )
      );
    }
    setShift(false);
  }

  function solveForX() {
    const source = expression.trim();
    if (!source) {
      setError("Type the equation first, with X in it.");
      return;
    }
    const result = solve(source, "X", angle, Math.abs(answer) > 1e-9 ? answer : 1);
    setShift(false);
    if (!result.ok) {
      setError(result.error);
      setSolved(null);
      return;
    }
    setError("");
    setSolved({ x: result.value, residual: result.residual });
    setAnswer(result.value);
    setHistory((current) =>
      [
        { expression: `${source}  →  X`, result: format(result.value) },
        ...current,
      ].slice(0, 50)
    );
  }

  const solveMarkdown = useMemo(() => {
    if (!solved) return "";
    return [
      `**Equation**`,
      "",
      "$$" + tex(expression) + "$$",
      "",
      `**Solved for X**`,
      "",
      `$$X = ${format(solved.x)}$$`,
      "",
      `*residual*: ${format(Math.abs(solved.residual))} — close to zero means the root is exact.`,
    ].join("\n");
  }, [solved, expression]);

  return (
    <div className={`calc calc--${skin.name.replace(/[^a-z0-9]/gi, "").toLowerCase()}`}>
      <div className="calc__body">
        <div className="calc__plate">
          <span className="calc__brand">{skin.brand}</span>
          <span className="calc__model">{skin.model}</span>
          {skin.note && <span className="calc__badge">{skin.note}</span>}
        </div>

      <div className="calc__screen">
        <div className="calc__status">
          <span>{shift ? "S" : ""}</span>
          <span>{alpha ? "A" : ""}</span>
          <span className="calc__mode">{angle === "DEG" ? "D" : "R"}</span>
          <span className="calc__hint">{skin.note}</span>
        </div>
        <input
          className="calc__entry"
          value={expression}
          onChange={(event) => {
            setExpression(event.target.value);
            setSolved(null);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") commit();
          }}
          spellCheck={false}
          aria-label="Expression"
          placeholder="solve for X:  2X^2 + 3X = 20"
        />
        <div className="calc__readout">
          {solved ? (
            <span>
              X = <strong>{format(solved.x)}</strong>
            </span>
          ) : (
            <span className="calc__preview">{preview || "\u00a0"}</span>
          )}
        </div>
      </div>

      <div className="calc__pad">
        {PAD.flat().map((key) => {
          const legend = shift && key.shift ? key.shift : alpha && key.alpha ? key.alpha : key.label;
          const isOn =
            (key.action === "shift" && shift) || (key.action === "alpha" && alpha);
          return (
            <button
              key={key.label + (key.shift ?? "")}
              type="button"
              className={
                [
                  "calc__key",
                  isOn ? "is-on" : "",
                  key.action === "equals" ? "is-go" : "",
                  key.action === "clear" || key.action === "delete" ? "is-warn" : "",
                  key.shift ? "has-shift" : "",
                ]
                  .filter(Boolean)
                  .join(" ")
              }
              onClick={() => press(key)}
              title={key.shift ? `${key.label} — SHIFT: ${key.shift}` : key.label}
            >
              {key.shift && <span className="calc__shift-legend">{key.shift}</span>}
              <span className="calc__legend">{legend}</span>
            </button>
          );
        })}
        </div>
      </div>

      {error && (
        <p className="calc__error" role="status">
          {error}
        </p>
      )}
      {solution.notice && (
        <p className={solution.failed ? "calc__error" : "muted"} role="status">
          {solution.notice}
        </p>
      )}

      <div className="calc__tools">
        <button type="button" className="chip" onClick={() => setAngle(angle === "DEG" ? "RAD" : "DEG")}>
          {angle}
        </button>
        <button
          type="button"
          className="chip"
          onClick={() => {
            setShift(true);
            solveForX();
          }}
          title="Solve the equation for X"
        >
          SHIFT+SOLVE
        </button>
        {(["fx-991ES", "fx-82ES", "F-789SGA"] as SkinName[]).map((name) => (
          <button
            key={name}
            type="button"
            className={`chip${skin.name === name ? " is-on" : ""}`}
            onClick={() => setSkin(SKINS.find((candidate) => candidate.name === name) ?? SKINS[0])}
          >
            {name}
          </button>
        ))}
      </div>

      {solved && (
        <div className="calc__actions">
          <button type="button" className="btn btn--primary" onClick={() => solution.add(solveMarkdown)}>
            Add to solution
          </button>
        </div>
      )}

      <div className="calc__history">
        <div className="calc__history-head">
          <span>History</span>
          {history.length > 0 && (
            <button
              type="button"
              className="link"
              onClick={() =>
                solution.add(
                  "**Calculator history**\n\n" +
                    history
                      .slice()
                      .reverse()
                      .map((entry) => `- $${tex(entry.expression)} = ${entry.result}$`)
                      .join("\n")
                )
              }
            >
              add all to solution
            </button>
          )}
          {history.length > 0 && (
            <button type="button" className="link" onClick={() => setHistory([])}>
              clear
            </button>
          )}
        </div>
        {history.length === 0 && <p className="muted">Nothing yet.</p>}
        <ul>
          {history.map((entry, index) => (
            <li key={`${entry.expression}-${index}`} className={entry.error ? "is-error" : ""}>
              <button type="button" className="link" onClick={() => setExpression(entry.expression)}>
                {entry.expression}
              </button>
              <span>= {entry.result}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/** The screen writes × and ÷; TeX does not. */
function tex(expression: string): string {
  return normalise(expression).replace(/\*/g, " \\cdot ").replace(/√/g, "\\sqrt ");
}
