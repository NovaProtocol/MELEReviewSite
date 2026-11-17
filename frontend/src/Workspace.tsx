import { useEffect, useMemo, useRef, useState } from "react";
import {
  DockviewReact,
  themeAbyss,
  themeLight,
  type DockviewApi,
  type DockviewReadyEvent,
  type IDockviewHeaderActionsProps,
  type IDockviewPanelProps,
} from "dockview";
import "dockview/dist/styles/dockview.css";
import { Scientific } from "./panels/Scientific";
import { Converter } from "./panels/Converter";
import { FormulaSearch } from "./panels/FormulaSearch";
import { ToolFrame } from "./panels/ToolFrame";
import type { PanelSpec } from "./tools";

const STORAGE_KEY = "mele.workspace.v1";

/* Every component a panel can be. The key is what the saved layout stores, so it
   must not change without bumping STORAGE_KEY. */
const components = {
  scientific: () => <Scientific />,
  converter: () => <Converter />,
  formula: () => <FormulaSearch />,
  tool: (props: IDockviewPanelProps<{ slug: string; title: string }>) => (
    <ToolFrame slug={props.params.slug} title={props.params.title} />
  ),
};

export function defaultLayout(): PanelSpec[] {
  return [
    { kind: "scientific", title: "Scientific calculator" },
    { kind: "converter", title: "Unit converter" },
  ];
}

function panelId(spec: PanelSpec) {
  return `${spec.kind}:${spec.slug ?? "main"}:${Math.random().toString(36).slice(2, 8)}`;
}

export function Workspace({
  spawns,
  onReady,
}: {
  spawns: PanelSpec[];
  onReady?: (api: DockviewApi | null) => void;
}) {
  const [api, setApi] = useState<DockviewApi | null>(null);
  const handled = useRef(0);

  useEffect(() => {
    onReady?.(api);
  }, [api, onReady]);

  /* Requests from the activity bar land here. The counter means a spawn is only
     added once, however many times React re-renders.

     A spawn opens beside what is already there until the screen is split in two;
     after that it becomes a tab in the group being used, which is the only rule
     that stays usable when somebody spawns fifty. */
  useEffect(() => {
    if (!api) return;
    for (const spec of spawns.slice(handled.current)) {
      const panels = api.panels;
      const anchor = panels[panels.length - 1];
      const opening = panels.length < 2 && anchor;
      api.addPanel({
        id: panelId(spec),
        component: spec.kind,
        title: spec.title,
        params: spec.kind === "tool" ? { slug: spec.slug, title: spec.title } : {},
        ...(opening ? { position: { referencePanel: anchor.id, direction: "right" as const } } : {}),
      });
    }
    handled.current = spawns.length;
  }, [spawns, api]);

  function ready(event: DockviewReadyEvent) {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        event.api.fromJSON(JSON.parse(saved));
        setApi(event.api);
        return;
      } catch {
        localStorage.removeItem(STORAGE_KEY);
      }
    }
    defaultLayout().forEach((spec, index) => {
      event.api.addPanel({
        id: panelId(spec),
        component: spec.kind,
        title: spec.title,
        ...(index === 0 ? {} : { position: { direction: "right" as const } }),
      });
    });
    setApi(event.api);
  }

  useEffect(() => {
    if (!api) return;
    const save = () => {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(api.toJSON()));
      } catch {
        /* a full quota must not break the drag that triggered it */
      }
    };
    const disposable = api.onDidLayoutChange(save);
    return () => disposable.dispose();
  }, [api]);

  return (
    <DockviewReact
      className="workspace__dock"
      rightHeaderActionsComponent={(props: IDockviewHeaderActionsProps) => (
        <FloatButton props={props} />
      )}
      /* The site's own theme decides this, so a light site does not get a dark
         docking frame. */
      theme={document.documentElement.dataset.theme === "dark" ? themeAbyss : themeLight}
      components={components}
      onReady={ready}
      watermarkComponent={() => (
        <div className="workspace__empty">
          <p>Pick a tool on the left.</p>
          <p className="muted">Panels drag, split, tab and resize.</p>
        </div>
      )}
    />
  );
}

/* A panel can also leave the grid entirely and float over it, which is what a
   reader wants when a calculator should sit beside the paragraph they are reading
   rather than take a column of its own. */
function FloatButton({ props }: { props: IDockviewHeaderActionsProps }) {
  const panel = props.activePanel;
  if (!panel) return null;
  return (
    <button
      type="button"
      className="workspace-float"
      title="Float this panel"
      aria-label="Float this panel"
      onClick={() => {
        props.containerApi.addFloatingGroup(panel, {
          x: 160,
          y: 120,
          width: 460,
          height: 560,
        });
      }}
    >
      <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">
        <rect x="4" y="7" width="12" height="12" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.7" />
        <path d="M8 7V5.5A1.5 1.5 0 0 1 9.5 4H18.5A1.5 1.5 0 0 1 20 5.5v9A1.5 1.5 0 0 1 18.5 16H17" fill="none" stroke="currentColor" strokeWidth="1.7" />
      </svg>
    </button>
  );
}

/* Below the docking breakpoint the same tools render as a plain stack: a phone is
   not a place to be dragging split handles. */
export function StackedWorkspace({ spawns }: { spawns: PanelSpec[] }) {
  const list = useMemo(() => (spawns.length ? spawns : defaultLayout()), [spawns]);
  return (
    <div className="stack">
      {list.map((spec, index) => (
        <section className="stack__card" key={`${spec.kind}-${spec.slug ?? ""}-${index}`}>
          <header className="stack__head">{spec.title}</header>
          <div className="stack__body">
            {spec.kind === "scientific" && <Scientific />}
            {spec.kind === "converter" && <Converter />}
            {spec.kind === "formula" && <FormulaSearch />}
            {spec.kind === "tool" && spec.slug && <ToolFrame slug={spec.slug} title={spec.title} />}
          </div>
        </section>
      ))}
    </div>
  );
}

export const isNarrow = () =>
  typeof window !== "undefined" && window.matchMedia("(max-width: 900px)").matches;
