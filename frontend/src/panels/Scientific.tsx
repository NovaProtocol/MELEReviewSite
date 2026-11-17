import { useMemo, useState } from "react";
import { evaluate } from "mathjs";

/* A scientific calculator that is a panel, not a page: it keeps its own history
   and its own angle mode, so a second instance starts clean. */

type Entry = { expression: string; result: string; error?: boolean };

const KEYS: string[][] = [
  ["sin", "cos", "tan", "(", ")"],
  ["ln", "log", "sqrt", "^", "!"],
  ["7", "8", "9", "÷", "C"],
  ["4", "5", "6", "×", "⌫"],
  ["1", "2", "3", "−", "π"],
  ["0", ".", "E", "+", "="],
];

const SWAP: Record<string, string> = {
  "×": "*",
  "÷": "/",
  "−": "-",
  "π": "pi",
  "E": "e",
};

export function Scientific() {
  const [expression, setExpression] = useState("");
  const [history, setHistory] = useState<Entry[]>([]);
  const [degrees, setDegrees] = useState(true);
  const [memory, setMemory] = useState<number | null>(null);

  const preview = useMemo(() => {
    if (!expression.trim()) return "";
    try {
      const scope = degrees ? { deg: true } : {};
      const value = evaluate(expression.replace(/π/g, "pi"), scope);
      return typeof value === "number" ? String(round(value)) : String(value);
    } catch {
      return "";
    }
  }, [expression, degrees]);

  function round(value: number) {
    if (!Number.isFinite(value)) return value;
    const magnitude = Math.abs(value);
    if (magnitude !== 0 && (magnitude < 1e-6 || magnitude >= 1e12)) return value.toExponential(6);
    return Number(value.toPrecision(12));
  }

  function press(key: string) {
    if (key === "C") {
      setExpression("");
      return;
    }
    if (key === "⌫") {
      setExpression((current) => current.slice(0, -1));
      return;
    }
    if (key === "=") {
      commit();
      return;
    }
    const insert = SWAP[key] && key !== "π" && key !== "E" ? SWAP[key] : key;
    // Functions open a bracket, because that is what the next keystroke needs.
    const text = ["sin", "cos", "tan", "ln", "log", "sqrt"].includes(key) ? `${key}(` : insert;
    setExpression((current) => current + text);
  }

  function commit() {
    const source = expression.trim();
    if (!source) return;
    try {
      const scope = degrees ? { deg: true } : {};
      const value = evaluate(source.replace(/π/g, "pi"), scope);
      const text = typeof value === "number" ? String(round(value)) : String(value);
      setHistory((current) => [{ expression: source, result: text }, ...current].slice(0, 40));
      setExpression(text);
    } catch (error) {
      setHistory((current) =>
        [{ expression: source, result: (error as Error).message, error: true }, ...current].slice(0, 40)
      );
    }
  }

  return (
    <div className="calc">
      <div className="calc__row">
        <button className={degrees ? "chip is-on" : "chip"} onClick={() => setDegrees(!degrees)}>
          {degrees ? "DEG" : "RAD"}
        </button>
        <button
          className="chip"
          onClick={() => setMemory(preview ? Number(preview) : null)}
          title="Store the previewed value"
        >
          {memory === null ? "MS" : `M ${memory}`}
        </button>
        <button className="chip" onClick={() => setExpression((c) => c + (memory ?? 0))} disabled={memory === null}>
          MR
        </button>
        <span className="calc__preview">{preview}</span>
      </div>

      <input
        className="calc__screen"
        value={expression}
        onChange={(event) => setExpression(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") commit();
        }}
        spellCheck={false}
        aria-label="Expression"
        placeholder="2*sin(30)+sqrt(9)"
      />

      <div className="calc__keys">
        {KEYS.flat().map((key) => (
          <button
            key={key}
            className={key === "=" ? "calc__key calc__key--go" : "calc__key"}
            onClick={() => press(key)}
          >
            {key}
          </button>
        ))}
      </div>

      <div className="calc__history">
        <div className="calc__history-head">
          <span>History</span>
          {history.length > 0 && (
            <button className="link" onClick={() => setHistory([])}>
              clear
            </button>
          )}
        </div>
        {history.length === 0 && <p className="muted">Nothing yet.</p>}
        <ul>
          {history.map((entry, index) => (
            <li key={`${entry.expression}-${index}`} className={entry.error ? "is-error" : ""}>
              <button className="link" onClick={() => setExpression(entry.expression)}>
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
