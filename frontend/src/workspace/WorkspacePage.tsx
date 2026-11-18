import { useCallback, useEffect, useRef, useState } from "react";
import {
  DockviewReact,
  themeAbyss,
  themeLight,
  type DockviewApi,
  type DockviewReadyEvent,
  type DockviewWillDropEvent,
  type IDockviewHeaderActionsProps,
  type IDockviewPanelProps,
} from "dockview";
import "dockview/dist/styles/dockview.css";
import { openPanel, onOpenPanel } from "../workspaceBus";
import { readLayout, writeLayout, clearLayout } from "./store";
import { Explorer, EMPTY_FILTERS, type ExplorerFilters, type ExplorerMode } from "../panels/Explorer";
import { ProblemsPanel, QuestionPanel } from "../panels/ProblemsPanel";
import { ResourcePanel, TaggedPanel } from "../panels/ResourcePanel";
import { Scientific } from "../panels/Scientific";
import { Converter } from "../panels/Converter";
import { FormulaSearch } from "../panels/FormulaSearch";
import { ToolFrame } from "../panels/ToolFrame";
import { QuizBuilderPanel, AdminPanel, SearchPanel } from "../panels/QuizBuilder";
import { WelcomePanel } from "../panels/WelcomePanel";
import { bootstrap } from "../tools";
import { canClose, mayStack, typeOf } from "./panelTypes";

/* Everything is a panel, and every panel has a type.

   The type is a promise about where it may go, and dockview's will-drop hook is
   where that promise is kept: a calculator cannot be tabbed into a question, and
   the explorer cannot be tabbed at all. */

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
  tagged: (props: IDockviewPanelProps<{ tag: string }>) => <TaggedPanel tag={props.params.tag} />,
  quiz: () => <QuizBuilderPanel />,
  admin: () => <AdminPanel />,
  search: () => <SearchPanel />,
  scientific: () => <Scientific />,
  converter: () => <Converter />,
  formula: () => <FormulaSearch />,
  tool: (props: IDockviewPanelProps<{ slug: string; title: string }>) => (
    <ToolFrame slug={props.params.slug} title={props.params.title} />
  ),
  welcome: () => <WelcomePanel />,
};

/* The explorer's mode and filters live above the panel: dockview does not
   re-render a panel when our own state changes. */
const explorerState = {
  mode: "problems" as ExplorerMode,
  filters: EMPTY_FILTERS as ExplorerFilters,
};
const explorerListeners = new Set<() => void>();

function ExplorerHost() {
  const [, force] = useState(0);
  useEffect(() => {
    const listener = () => force((n) => n + 1);
    explorerListeners.add(listener);
    return () => {
      explorerListeners.delete(listener);
    };
  }, []);
  return (
    <Explorer
      mode={explorerState.mode}
      onMode={(next) => {
        explorerState.mode = next;
        for (const listener of explorerListeners) listener();
      }}
      filters={explorerState.filters}
    />
  );
}

/* Placing a panel, by its type.

   The same rule as dragging, applied when we open something ourselves, because
   otherwise a calculator lands in the explorer's tab strip and the map disappears
   behind it. A panel joins an existing group of its own type when there is one;
   otherwise it gets a new column beside the explorer. */
function placePanel(api: DockviewApi, request: { kind: string; title: string; params?: Record<string, string> }) {
  const type = typeOf(request.kind);
  const key = identity(request.kind, request.params);

  // A question belongs with its problem list: that is the pairing the workspace is
  // for, and splitting it across columns loses the connection.
  if (request.kind === "question") {
    const list = api.panels.find((panel) => panel.id.startsWith("problems|"));
    if (list) {
      api.addPanel({
        id: `${key}:${Math.random().toString(36).slice(2, 8)}`,
        component: request.kind,
        title: request.title,
        params: request.params ?? {},
        position: { referencePanel: list.id, direction: "within" },
      });
      return;
    }
  }

  // Otherwise: an existing group of the same type, if it can take a tab.
  if (type !== "system") {
    const same = api.panels.find(
      (panel) =>
        panel.id !== request.kind &&
        typeOf(panel.id.split("|")[0]) === type &&
        panel.group.panels.length > 0
    );
    if (same) {
      api.addPanel({
        id: `${key}:${Math.random().toString(36).slice(2, 8)}`,
        component: request.kind,
        title: request.title,
        params: request.params ?? {},
        position: { referencePanel: same.id, direction: "within" },
      });
      return;
    }
  }

  // A new column. Tools go right of the workspace; workspace goes right of the
  // explorer; the explorer goes left.
  const anchor =
    type === "tools"
      ? api.panels.find((panel) => typeOf(panel.id.split("|")[0]) === "workspace")
      : api.panels.find((panel) => panel.id.startsWith("explorer|"));
  api.addPanel({
    id: `${key}:${Math.random().toString(36).slice(2, 8)}`,
    component: request.kind,
    title: request.title,
    params: request.params ?? {},
    position: anchor
      ? { referencePanel: anchor.id, direction: "right" }
      : api.panels.length
        ? { direction: "right" }
        : undefined,
  });
}

const identity = (kind: string, params?: Record<string, string>) =>
  `${kind}|${Object.keys(params ?? {})
    .sort()
    .map((key) => `${key}=${params![key]}`)
    .join(",")}`;

export function WorkspacePage() {
  const [api, setApi] = useState<DockviewApi | null>(null);
  const [filters, setFilters] = useState<ExplorerFilters>(EMPTY_FILTERS);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const explorerPanel = useRef<string | null>(null);

  explorerState.filters = filters;

  /* Requests from the explorer and the rail. One panel per target, and a request
     for something already open raises it. A question tabs into its own problem
     list when there is one, which is the grouping that makes sense while working. */
  useEffect(() => {
    if (!api) return;
    return onOpenPanel((request) => {
      const key = identity(request.kind, request.params);
      const existing = api.panels.find((panel) => panel.id.startsWith(key));
      if (existing) {
        existing.api.setActive();
        return;
      }
      if (request.kind === "problems") {
        for (const panel of api.panels.filter((item) => item.id.startsWith("problems|"))) {
          panel.api.close();
        }
      }
      placePanel(api, request);

      const welcome = api.panels.find((panel) => panel.id.startsWith("welcome|"));
      if (welcome) welcome.api.close();
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

  /* A closed question leaves an empty canvas and no way back in, so the canvas
     says how to use the site instead of being blank. */
  useEffect(() => {
    if (!api) return;
    const check = () => {
      const workspace = api.panels.filter(
        (panel) => typeOf(panel.id.split("|")[0]) === "workspace"
      );
      const welcome = api.panels.some((panel) => panel.id.startsWith("welcome|"));
      if (workspace.length === 0 && !welcome && api.panels.length > 0) {
        api.addPanel({
          id: `welcome|${Math.random().toString(36).slice(2, 6)}`,
          component: "welcome",
          title: "Start here",
          position: { direction: "right" },
        });
      }
    };
    const disposable = api.onDidRemovePanel(check);
    return () => disposable.dispose();
  }, [api]);

  /* The type rule, at the one moment dockview asks: joining a tab strip. Splits
     and floats are always allowed, because a column of panels is still legible. */
  function willDrop(event: DockviewWillDropEvent) {
    if (event.kind !== "tab") return;
    const moving = event.getData()?.panelId;
    const target = event.group?.panels?.[0]?.id;
    if (!moving || !target) return;
    const from = moving.split("|")[0];
    const into = target.split("|")[0];
    if (typeOf(from) === "system" || typeOf(into) === "system") {
      event.preventDefault();
      return;
    }
    if (!mayStack(from, into)) event.preventDefault();
  }

  function switchExplorer(next: ExplorerMode) {
    if (!api) return;
    explorerState.mode = next;
    for (const listener of explorerListeners) listener();
    const current = api.panels.find((panel) => panel.id.startsWith("explorer|"));
    if (current) {
      current.api.setActive();
      return;
    }
    const panel = api.addPanel({
      id: "explorer|main",
      component: "explorer",
      title: "Explorer",
      params: {},
      position: { direction: "left" },
    });
    explorerPanel.current = panel.id;
  }

  return (
    <div className="workspace-body">
      <nav className="activity" aria-label="Workspace">
        <ActivityButton icon="library" label="Library" onClick={() => switchExplorer("library")} />
        <ActivityButton icon="explorer" label="Problems" onClick={() => switchExplorer("problems")} />
        <ActivityButton icon="tags" label="Tags" onClick={() => switchExplorer("tags")} />
        <ActivityButton
          icon="search"
          label="Search"
          onClick={() => openPanel({ kind: "search", title: "Search" })}
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
          onClick={() =>
            openPanel({
              kind: "tool",
              title: "Steam tables",
              params: { slug: "steam", title: "Steam tables" },
            })
          }
        />
      </nav>

      <div className="workspace-dock">
        <DockviewReact
          className="workspace-dock__inner"
          theme={document.documentElement.dataset.theme === "dark" ? themeAbyss : themeLight}
          components={components}
          onReady={ready}
          onWillDrop={willDrop}
          rightHeaderActionsComponent={(props: IDockviewHeaderActionsProps) => (
            <HeaderActions
              props={props}
              filtersOpen={filtersOpen}
              onFilters={() => setFiltersOpen((open) => !open)}
            />
          )}
          watermarkComponent={() => (
            <div className="workspace-empty">
              <p>Open something on the left.</p>
              <p className="muted">Panels drag, dock, tab and resize.</p>
            </div>
          )}
        />

        {filtersOpen && (
          <FiltersPopover
            filters={filters}
            onChange={setFilters}
            onClose={() => setFiltersOpen(false)}
          />
        )}
      </div>
    </div>
  );
}

function HeaderActions({
  props,
  filtersOpen,
  onFilters,
}: {
  props: IDockviewHeaderActionsProps;
  filtersOpen: boolean;
  onFilters: () => void;
}) {
  const panel = props.activePanel;
  if (!panel) return null;
  const kind = panel.id.split("|")[0];
  const isExplorer = kind === "explorer";

  return (
    <span className="header-actions">
      {isExplorer && (
        <button
          type="button"
          className={`workspace-float${filtersOpen ? " is-on" : ""}`}
          title="Filters"
          aria-label="Filters"
          onClick={onFilters}
        >
          <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">
            <path d="M3 5h18l-7 8v6l-4 2v-8Z" fill="none" stroke="currentColor" strokeWidth="1.7" />
          </svg>
        </button>
      )}
      {canClose(kind) && (
        <button
          type="button"
          className="workspace-float"
          title="Close"
          aria-label="Close this panel"
          onClick={() => panel.api.close()}
        >
          <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">
            <path d="M18 6 6 18M6 6l12 12" fill="none" stroke="currentColor" strokeWidth="1.7" />
          </svg>
        </button>
      )}
    </span>
  );
}

/* The filters beside the explorer rather than inside it: one control for one tree,
   so the tree stays the thing you read. */
function FiltersPopover({
  filters,
  onChange,
  onClose,
}: {
  filters: ExplorerFilters;
  onChange: (next: ExplorerFilters) => void;
  onClose: () => void;
}) {
  return (
    <div className="filters" role="dialog" aria-label="Filters">
      <header className="filters__head">
        <span>Filters</span>
        <button type="button" className="link" onClick={onClose}>
          close
        </button>
      </header>

      <label className="filters__row">
        Answers
        <select
          value={filters.answered}
          onChange={(event) =>
            onChange({ ...filters, answered: event.target.value as ExplorerFilters["answered"] })
          }
        >
          <option value="all">All</option>
          <option value="answered">Answered</option>
          <option value="unanswered">Unanswered</option>
        </select>
      </label>

      <label className="filters__row">
        Kind
        <select
          value={filters.kind}
          onChange={(event) =>
            onChange({ ...filters, kind: event.target.value as ExplorerFilters["kind"] })
          }
        >
          <option value="">Any</option>
          <option value="identification">Identification</option>
          <option value="computation">Computation</option>
        </select>
      </label>

      <label className="filters__check">
        <input
          type="checkbox"
          checked={filters.hasSolution}
          onChange={(event) => onChange({ ...filters, hasSolution: event.target.checked })}
        />
        Has a solution
      </label>

      <label className="filters__check">
        <input
          type="checkbox"
          checked={filters.withImages}
          onChange={(event) => onChange({ ...filters, withImages: event.target.checked })}
        />
        Has a figure
      </label>

      <button type="button" className="btn btn-sm" onClick={() => onChange(EMPTY_FILTERS)}>
        Reset
      </button>
    </div>
  );
}

function ActivityButton({
  icon,
  label,
  onClick,
}: {
  icon: string;
  label: string;
  onClick: () => void;
}) {
  return (
    <button type="button" className="activity__button" onClick={onClick} title={label} aria-label={label}>
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
    search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm6 13-4-4",
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
