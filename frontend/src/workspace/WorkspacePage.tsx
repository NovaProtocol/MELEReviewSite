import { useCallback, useEffect, useRef, useState } from "react";
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
import { openPanel, onOpenPanel } from "../workspaceBus";
import { readLayout, writeLayout, clearLayout } from "./store";
import { Explorer, type ExplorerMode } from "../panels/Explorer";
import { ProblemsPanel, QuestionPanel } from "../panels/ProblemsPanel";
import { ResourcePanel, TaggedPanel } from "../panels/ResourcePanel";
import { Scientific } from "../panels/Scientific";
import { Converter } from "../panels/Converter";
import { FormulaSearch } from "../panels/FormulaSearch";
import { ToolFrame } from "../panels/ToolFrame";
import { QuizBuilderPanel, AdminPanel } from "../panels/QuizBuilder";
import { bootstrap } from "../tools";

/* Everything is a panel.

   The explorer is dockable like anything else: it can be moved under the whole
   workspace, tabbed behind a question, or closed. Nothing is pinned, because a
   layout that cannot be rearranged is a page, not a workspace. */


const components = {
  explorer: () => <ExplorerHost />,
  problems: (props: IDockviewPanelProps<{ topicId: string }>) => (
    <ProblemsPanel topicId={Number(props.params.topicId)} />
  ),
  question: (props: IDockviewPanelProps<{ questionId: string }>) => (
    <QuestionPanel questionId={Number(props.params.questionId)} />
  ),
  resource: (props: IDockviewPanelProps<{ topicId: string }>) => (
    <ResourcePanel topicId={Number(props.params.topicId)} />
  ),
  tagged: (props: IDockviewPanelProps<{ tag: string }>) => (
    <TaggedPanel tag={props.params.tag} />
  ),
  quiz: () => <QuizBuilderPanel />,
  admin: () => <AdminPanel />,
  scientific: () => <Scientific />,
  converter: () => <Converter />,
  formula: () => <FormulaSearch />,
  tool: (props: IDockviewPanelProps<{ slug: string; title: string }>) => (
    <ToolFrame slug={props.params.slug} title={props.params.title} />
  ),
};

/* The explorer's mode and its open folders live above the panel, because dockview
   does not re-render a panel when our own state changes: a click would leave the
   tree on the old mode. */
const explorerMemory = {
  mode: "problems" as ExplorerMode,
  open: {} as Record<string, boolean>,
  active: "",
};

const explorerListeners = new Set<() => void>();

function useExplorerState() {
  const [, force] = useState(0);
  useEffect(() => {
    const listener = () => force((n) => n + 1);
    explorerListeners.add(listener);
    return () => {
      explorerListeners.delete(listener);
    };
  }, []);
  return {
    mode: explorerMemory.mode,
    open: explorerMemory.open,
    active: explorerMemory.active,
    setMode(mode: ExplorerMode) {
      explorerMemory.mode = mode;
      for (const listener of explorerListeners) listener();
    },
    setOpen(open: Record<string, boolean>) {
      explorerMemory.open = open;
      for (const listener of explorerListeners) listener();
    },
  };
}

function ExplorerHost() {
  const state = useExplorerState();
  return (
    <Explorer
      mode={state.mode}
      onMode={state.setMode}
      open={state.open}
      setOpen={state.setOpen}
      activeKey={state.active}
    />
  );
}

function FloatButton({ props }: { props: IDockviewHeaderActionsProps }) {
  const panel = props.activePanel;
  if (!panel) return null;
  return (
    <button
      type="button"
      className="workspace-float"
      title="Float this panel"
      aria-label="Float this panel"
      onClick={() =>
        props.containerApi.addFloatingGroup(panel, { x: 180, y: 130, width: 480, height: 560 })
      }
    >
      <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">
        <rect x="4" y="7" width="12" height="12" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.7" />
        <path
          d="M8 7V5.5A1.5 1.5 0 0 1 9.5 4H18.5A1.5 1.5 0 0 1 20 5.5v9A1.5 1.5 0 0 1 18.5 16H17"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
        />
      </svg>
    </button>
  );
}

const identity = (kind: string, params?: Record<string, string>) =>
  `${kind}|${Object.keys(params ?? {})
    .sort()
    .map((key) => `${key}=${params![key]}`)
    .join(",")}`;

export function WorkspacePage() {
  const [api, setApi] = useState<DockviewApi | null>(null);
  const [mode, setMode] = useState<ExplorerMode>("problems");
  const explorerPanel = useRef<string | null>(null);

  /* Panels ask to be opened; the workspace decides whether that means a new one or
     raising the one already showing it. */
  useEffect(() => {
    if (!api) return;
    return onOpenPanel((request) => {
      const key = identity(request.kind, request.params);
      const existing = api.panels.find((panel) => panel.id.startsWith(key));
      if (existing) {
        existing.api.setActive();
        return;
      }
      // A topic browser is exclusive: one problem list at a time.
      if (request.kind === "problems") {
        for (const panel of api.panels.filter((item) => item.id.startsWith("problems|"))) {
          panel.api.close();
        }
      }
      /* Where a new panel goes:

         - next to its own list if one is open, as a tab, so a question and the
           list it came from share a column;
         - otherwise beside the explorer. */
      const sibling =
        request.kind === "question"
          ? api.panels.find((panel) => panel.id.startsWith("problems|"))
          : api.panels.find((panel) => panel.id.startsWith("explorer|"));
      api.addPanel({
        id: `${key}:${Math.random().toString(36).slice(2, 8)}`,
        component: request.kind,
        title: request.title,
        params: request.params ?? {},
        ...(sibling
          ? { position: { referencePanel: sibling.id, direction: "within" as const } }
          : api.panels.length
            ? { position: { direction: "right" as const } }
            : {}),
      });
    });
  }, [api]);

  const ready = useCallback((event: DockviewReadyEvent) => {
    const saved = readLayout();
    if (saved) {
      try {
        event.api.fromJSON(saved.layout as never);
        setApi(event.api);
        return;
      } catch {
        clearLayout();
      }
    }
    // First visit: the explorer on the left, empty space to work in.
    const explorer = event.api.addPanel({
      id: "explorer|main",
      component: "explorer",
      title: "Explorer",
      params: {},
    });
    explorerPanel.current = explorer.id;
    setApi(event.api);
  }, []);

  useEffect(() => {
    if (!api) return;
    const save = () => writeLayout(api, explorerPanel.current);
    const disposable = api.onDidLayoutChange(save);
    return () => disposable.dispose();
  }, [api]);

  function switchExplorer(next: ExplorerMode) {
    if (!api) return;
    setMode(next);
    explorerMemory.mode = next;
    for (const listener of explorerListeners) listener();

    const current = api.panels.find((panel) => panel.id.startsWith("explorer|"));
    if (current) {
      // Already docked: change the mode in place and raise it, rather than
      // destroying the panel the reader may have moved somewhere deliberate.
      current.api.setActive();
      return;
    }
    const panel = api.addPanel({
      id: `explorer|mode=${next}`,
      component: "explorer",
      title: "Explorer",
      params: {},
      position: { direction: "left" },
    });
    explorerPanel.current = panel.id;
  }

  const explorerCount = api?.panels.filter((panel) => panel.id.startsWith("explorer|")).length ?? 0;

  return (
    <div className="workspace-body">
      <nav className="activity" aria-label="Workspace">
        <ActivityButton
          icon="library"
          label="Library"
          active={mode === "resources" && explorerCount > 0}
          onClick={() => switchExplorer("resources")}
        />
        <ActivityButton
          icon="explorer"
          label="Problems"
          active={mode === "problems" && explorerCount > 0}
          onClick={() => switchExplorer("problems")}
        />
        <ActivityButton
          icon="tags"
          label="Tags"
          active={mode === "tags" && explorerCount > 0}
          onClick={() => switchExplorer("tags")}
        />
        <ActivityButton
          icon="quiz"
          label="Quiz"
          onClick={() => openPanel({ kind: "quiz", title: "Quiz builder" })}
        />
        {bootstrap.viewer.is_admin && (
          <ActivityButton
            icon="admin"
            label="Admin"
            onClick={() => openPanel({ kind: "admin", title: "Admin" })}
          />
        )}

        <span className="activity__gap" />

        <ActivityButton
          icon="calculator"
          label="Calc"
          onClick={() => openPanel({ kind: "scientific", title: "Scientific calculator" })}
        />
        <ActivityButton
          icon="converter"
          label="Convert"
          onClick={() => openPanel({ kind: "converter", title: "Unit converter" })}
        />
        <ActivityButton
          icon="formula"
          label="Formula"
          onClick={() => openPanel({ kind: "formula", title: "Formula search" })}
        />
        <ActivityButton
          icon="tools"
          label="Tools"
          onClick={() => openPanel({ kind: "tool", title: "Steam tables", params: { slug: "steam", title: "Steam tables" } })}
        />
      </nav>

      <div className="workspace-dock">
        <DockviewReact
          className="workspace-dock__inner"
          theme={document.documentElement.dataset.theme === "dark" ? themeAbyss : themeLight}
          components={components}
          onReady={ready}
          rightHeaderActionsComponent={(props: IDockviewHeaderActionsProps) => (
            <FloatButton props={props} />
          )}
          watermarkComponent={() => (
            <div className="workspace-empty">
              <p>Open something on the left.</p>
              <p className="muted">Panels drag, dock, tab and resize.</p>
            </div>
          )}
        />
      </div>
    </div>
  );
}

function ActivityButton({
  icon,
  label,
  active,
  onClick,
}: {
  icon: string;
  label: string;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`activity__button${active ? " is-active" : ""}`}
      onClick={onClick}
      title={label}
      aria-label={label}
    >
      <ActivityIcon name={icon} />
      <span>{label}</span>
    </button>
  );
}

function ActivityIcon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    library: "M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5Zm0 0V21M8 7h8M8 11h6",
    explorer: "M3 7h6l2 2h10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z",
    tags: "M3 12V5a2 2 0 0 1 2-2h7l9 9-9 9Z",
    quiz: "M9 3h6a1 1 0 0 1 1 1v1h2a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h2V4a1 1 0 0 1 1-1Zm-1 8h8M8 15h5",
    admin: "M12 3l8 4v6c0 4-3.4 7.3-8 8-4.6-.7-8-4-8-8V7Z",
    calculator:
      "M7 3h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm2 4v3h6V7Zm0 6h2v2H9Zm4 0h2v2h-2Zm-4 4h2v2H9Zm4 0h2v2h-2Z",
    converter: "M4 7h11l-2.5-2.5M20 17H9l2.5 2.5",
    formula: "M5 5h9M9 5c-1.8 0-2.6 1-2.6 3v8c0 2-.8 3-2.6 3M14 9l5 6m0-6-5 6",
    tools: "M14 4l6 6-9 9H5v-6Z",
  };
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
      <path
        d={paths[name] ?? ""}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
