import { useEffect, useMemo, useState } from "react";
import { Workspace, StackedWorkspace, isNarrow } from "./Workspace";
import { bootstrap, type PanelSpec, type SpecialistTool } from "./tools";
import { openPanel } from "./workspaceBus";

const ICONS: Record<string, string> = {
  library: "M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5Zm0 0V21M8 7h8M8 11h6",
  calculator: "M7 3h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm2 4v3h6V7Zm0 6h2v2H9Zm4 0h2v2h-2Zm-4 4h2v2H9Zm4 0h2v2h-2Z",
  converter: "M4 7h11l-2.5-2.5M20 17H9l2.5 2.5",
  formula: "M5 5h9M9 5c-1.8 0-2.6 1-2.6 3v8c0 2-.8 3-2.6 3M14 9l5 6m0-6-5 6",
  tools: "M14 4l6 6-9 9H5v-6Z",
};

function Icon({ name }: { name: string }) {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
      <path d={ICONS[name]} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function App() {
  const [spawns, setSpawns] = useState<PanelSpec[]>([]);
  const [narrow, setNarrow] = useState(isNarrow);
  const [specialistOpen, setSpecialistOpen] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 900px)");
    const update = () => setNarrow(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  const specialists = useMemo(() => bootstrap.specialists, []);

  function spawn(spec: PanelSpec) {
    setSpecialistOpen(false);
    setSpawns((current) => [...current, spec]);
  }

  /* Content panels open through the same bus the library uses, so a click in the
     rail and a click in the library take the same path. */
  function spawnPanel(request: { kind: string; title: string }) {
    setSpecialistOpen(false);
    openPanel(request);
  }

  function spawnSpecialist(tool: SpecialistTool) {
    spawn({ kind: "tool", slug: tool.slug, title: tool.name });
  }

  function clearAll() {
    setSpawns([]);
    if (!narrow) {
      localStorage.removeItem("mele.workspace.v1");
      window.location.reload();
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <a className="topbar__brand" href={bootstrap.library_url}>
          ~/<span>melereview</span>
        </a>
        <nav className="topbar__nav">
          <a href={bootstrap.library_url}>Library</a>
          <a href="/tags">Tags</a>
          <a href="/quiz">Quiz</a>
          {bootstrap.viewer.is_admin && <a href="/admin">Admin</a>}
        </nav>
        <div className="topbar__spacer" />
        <div className="topbar__right">
          <span className="topbar__user" title="Your page">
            {bootstrap.viewer.avatar ? (
              <img src={bootstrap.viewer.avatar} alt="" />
            ) : (
              bootstrap.viewer.username.slice(0, 1).toUpperCase()
            )}
            <span>{bootstrap.viewer.username}</span>
          </span>
          <a className="topbar__link" href="/library">
            classic site
          </a>
        </div>
      </header>

      <div className="body">
        <aside className="rail" aria-label="Tools">
          <button
            className="rail__btn"
            onClick={() =>
              spawnPanel({ kind: "library", title: "Library" })
            }
            title="Library"
          >
            <Icon name="library" />
            <span>Library</span>
          </button>
          <button className="rail__btn" onClick={() => spawn({ kind: "scientific", title: "Scientific calculator" })} title="Scientific calculator">
            <Icon name="calculator" />
            <span>Calc</span>
          </button>
          <button className="rail__btn" onClick={() => spawn({ kind: "converter", title: "Unit converter" })} title="Unit converter">
            <Icon name="converter" />
            <span>Convert</span>
          </button>
          <button
            className="rail__btn"
            onClick={() => setSpecialistOpen((open) => !open)}
            title="Specialist calculators"
            aria-expanded={specialistOpen}
          >
            <Icon name="tools" />
            <span>Tools</span>
          </button>
          <button className="rail__btn" onClick={() => spawn({ kind: "formula", title: "Formula search" })} title="Formula search">
            <Icon name="formula" />
            <span>Formula</span>
          </button>
          <div className="rail__spacer" />
          <button className="rail__btn rail__btn--quiet" onClick={clearAll} title="Close every panel">
            reset
          </button>
        </aside>

        {specialistOpen && (
          <div className="specialists" role="menu">
            {specialists.map((tool) => (
              <button key={tool.slug} role="menuitem" onClick={() => spawnSpecialist(tool)}>
                <strong>{tool.name}</strong>
                <span>{tool.group}</span>
              </button>
            ))}
            {specialists.length === 0 && <p className="muted">No specialist tools.</p>}
          </div>
        )}

        <main className="workspace">
          {narrow ? <StackedWorkspace spawns={spawns} /> : <Workspace spawns={spawns} />}
        </main>
      </div>
    </div>
  );
}
