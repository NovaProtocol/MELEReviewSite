import { useEffect, useMemo, useRef, useState } from "react";
import {
  DockviewReact,
  themeAbyss,
  themeLight,
  type DockviewApi,
  type DockviewReadyEvent,
  type IDockviewPanelProps,
} from "dockview";
import "dockview/dist/styles/dockview.css";
import { Scientific } from "./panels/Scientific";
import { Library } from "./panels/Library";
import { Problems } from "./panels/Problems";
import { QuestionPanel } from "./panels/QuestionPanel";
import { TopicPage } from "./panels/TopicPage";
import { onOpenPanel } from "./workspaceBus";
import { Converter } from "./panels/Converter";
import { FormulaSearch } from "./panels/FormulaSearch";
import { ToolFrame } from "./panels/ToolFrame";
import type { PanelSpec } from "./tools";

const STORAGE_KEY = "mele.workspace.v1";

/* Every component a panel can be. The key is what the saved layout stores, so it
   must not change without bumping STORAGE_KEY.

   Content and tools are the same kind of thing here: a problem set, a question, a
   topic's notes and a calculator are all panels you can put where you want. */
const components = {
  library: () => <Library />,
  problems: (props: IDockviewPanelProps<{ topicId: string; topicName?: string }>) => (
    <Problems
      topicId={Number(props.params.topicId)}
      topicName={props.params.topicName}
    />
  ),
  question: (props: IDockviewPanelProps<{ questionId: string }>) => (
    <QuestionPanel questionId={Number(props.params.questionId)} />
  ),
  notes: (props: IDockviewPanelProps<{ topicId: string }>) => (
    <TopicPage topicId={Number(props.params.topicId)} />
  ),
  scientific: () => <Scientific />,
  converter: () => <Converter />,
  formula: () => <FormulaSearch />,
  tool: (props: IDockviewPanelProps<{ slug: string; title: string }>) => (
    <ToolFrame slug={props.params.slug} title={props.params.title} />
  ),
};

/* One panel per target, so clicking the same topic twice raises the panel already
   showing it rather than stacking duplicates. */
function panelIdentity(kind: string, params?: Record<string, string>) {
  const target = params
    ? Object.keys(params)
        .sort()
        .map((key) => `${key}=${params[key]}`)
        .join(",")
    : "";
  return `${kind}|${target}`;
}

/* Panels ask the workspace to open another panel (library -> problems -> question)
   instead of navigating, which is what keeps the arrangement intact. */
function wireBus(api: DockviewApi) {
  return onOpenPanel((request) => {
    const identity = panelIdentity(request.kind, request.params);
    const existing = api.panels.find((panel) => panel.id.startsWith(identity));
    if (existing) {
      existing.api.setActive();
      return;
    }
    /* Content opens beside what is already there, not on top of it: the point of
       the workspace is seeing the list and the question at the same time. Width is
       what runs out, and tabs in one column cost no width, so the test counts
       columns. Past four the panels are too narrow to read, so later ones tab. */
    const panels = api.panels;
    const anchor = panels[panels.length - 1];
    const columns = new Set(panels.map((panel) => panel.group.id)).size;
    const room = window.innerWidth >= 1000 && columns < 4;
    api.addPanel({
      id: `${identity}:${Math.random().toString(36).slice(2, 8)}`,
      component: request.kind,
      title: request.title,
      params: request.params ?? {},
      ...(room && anchor
        ? { position: { referencePanel: anchor.id, direction: "right" as const } }
        : {}),
    });
  });
}

export function defaultLayout(): PanelSpec[] {
  // The library, because that is the way into everything else. Tools are a click
  // away on the rail, and a workspace that opens with two calculators is a
  // workspace with nowhere to read.
  return [{ kind: "library", title: "Library" }];
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
    if (!api) return;
    return wireBus(api);
  }, [api]);

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
