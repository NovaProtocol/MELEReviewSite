import { useEffect, useRef, useState } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";
import { bootstrap } from "../tools";

/* The index stores TeX, which is what a reader copies; showing it raw would ask
   them to read the notation instead of the formula. */
function Tex({ tex }: { tex: string }) {
  const html = (() => {
    try {
      return katex.renderToString(tex, { throwOnError: false, strict: false, displayMode: false });
    } catch {
      return null;
    }
  })();
  if (!html) return <code>{tex}</code>;
  return <span className="formula__tex" dangerouslySetInnerHTML={{ __html: html }} />;
}

/* Search the formulas the book actually contains. The index is built server side
   from the topic pages, so a formula that was added yesterday is findable today
   without a second copy of the notes. */

type Formula = {
  tex: string;
  topic: string;
  topic_id: number;
  context: string;
};

export function FormulaSearch() {
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<Formula[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (timer.current) window.clearTimeout(timer.current);
    const text = query.trim();
    if (text.length < 2) {
      setRows([]);
      setError("");
      return;
    }
    setBusy(true);
    timer.current = window.setTimeout(async () => {
      try {
        const response = await fetch(`${bootstrap.formulas_url}?q=${encodeURIComponent(text)}`);
        if (!response.ok) throw new Error("Search failed");
        const payload = await response.json();
        setRows(payload.results ?? []);
        setError("");
      } catch (problem) {
        setError((problem as Error).message);
      } finally {
        setBusy(false);
      }
    }, 220);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [query]);

  async function copy(tex: string) {
    const text = `$${tex}$`;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const field = document.createElement("textarea");
      field.value = text;
      document.body.appendChild(field);
      field.select();
      document.execCommand("copy");
      field.remove();
    }
    setCopied(tex);
    window.setTimeout(() => setCopied(""), 1200);
  }

  return (
    <div className="formula">
      <input
        className="formula__search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="carnot, reynolds, bending stress..."
        aria-label="Search formulas"
        autoFocus
      />

      {error && <p className="form-error">{error}</p>}
      {busy && <p className="muted">Searching...</p>}
      {!busy && query.trim().length >= 2 && rows.length === 0 && !error && (
        <p className="muted">Nothing matched.</p>
      )}

      <ul className="formula__list">
        {rows.map((row) => (
          <li key={`${row.topic_id}-${row.tex}-${row.context.slice(0, 12)}`}>
            <Tex tex={row.tex} />
            <p className="formula__context">{row.context}</p>
            <div className="formula__foot">
              <a href={`${bootstrap.library_url}/${row.topic_id}`}>{row.topic}</a>
              <button className="link" onClick={() => copy(row.tex)}>
                {copied === row.tex ? "copied" : "copy TeX"}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
