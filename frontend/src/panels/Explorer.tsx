import { useApi } from "../api";
import { openPanel } from "../workspaceBus";

/* The explorer, in three modes.

   Problem sets: subjects -> topics, each topic opening a problem list.
   Resources:    the same tree, each topic opening its notes.
   Tags:         a flat list, because a tag is not a place in the taxonomy.

   It is one component because it is one thing to the reader: a list of what there
   is, which opens a panel. Only what a click does changes. */

export type ExplorerMode = "problems" | "resources" | "tags";

type Subject = {
  id: number;
  name: string;
  topics: { id: number; name: string; questions: number }[];
};

export function Explorer({
  mode,
  onMode,
  open,
  setOpen,
  activeKey,
}: {
  mode: ExplorerMode;
  onMode: (mode: ExplorerMode) => void;
  open: Record<string, boolean>;
  setOpen: (next: Record<string, boolean>) => void;
  activeKey: string;
}) {
  const subjects = useApi<Subject[]>("/api/subjects");
  const tags = useApi<{ id: number; name: string; questions: number }[]>("/api/tags?counts=true");

  const toggle = (key: string) => setOpen({ ...open, [key]: !open[key] });

  function openTopic(subjectId: number, topic: { id: number; name: string }) {
    if (mode === "resources") {
      openPanel({ kind: "resource", title: topic.name, params: { topicId: String(topic.id) } });
    } else {
      openPanel({
        kind: "problems",
        title: topic.name,
        params: { topicId: String(topic.id), subjectId: String(subjectId) },
      });
    }
  }

  return (
    <div className="explorer-panel">
      <div className="explorer-panel__modes" role="tablist">
        {(
          [
            ["problems", "Problem sets"],
            ["resources", "Resources"],
            ["tags", "Tags"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={mode === value}
            className={`explorer-panel__mode${mode === value ? " is-active" : ""}`}
            onClick={() => onMode(value)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="explorer-panel__body">
        {mode === "tags" ? (
          <>
            {tags.loading && <p className="muted pad">Loading...</p>}
            <ul className="tree__files">
              {(tags.data ?? []).map((tag) => (
                <li key={tag.id}>
                  <button
                    type="button"
                    className={`tree__file${activeKey === `tag:${tag.name}` ? " is-active" : ""}`}
                    onClick={() =>
                      openPanel({
                        kind: "tagged",
                        title: `#${tag.name}`,
                        params: { tag: tag.name },
                      })
                    }
                  >
                    <span className="tree__name">#{tag.name}</span>
                    <span className="tree__count">{tag.questions}</span>
                  </button>
                </li>
              ))}
            </ul>
            {(tags.data ?? []).length === 0 && !tags.loading && (
              <p className="muted pad">No tags yet.</p>
            )}
          </>
        ) : (
          (subjects.data ?? []).map((subject) => {
            const expanded = open[`s${subject.id}`] ?? false;
            return (
              <div className="tree__group" key={subject.id}>
                <button
                  type="button"
                  className="tree__folder"
                  onClick={() => toggle(`s${subject.id}`)}
                  aria-expanded={expanded}
                >
                  <span className={`tree__caret${expanded ? " is-open" : ""}`}>▸</span>
                  {subject.name}
                </button>
                {expanded && (
                  <ul className="tree__files">
                    {subject.topics.map((topic) => (
                      <li key={topic.id}>
                        <button
                          type="button"
                          className={`tree__file${
                            activeKey === `${mode}:${topic.id}` ? " is-active" : ""
                          }`}
                          onClick={() => openTopic(subject.id, topic)}
                        >
                          <span className="tree__name">{topic.name}</span>
                          <span className="tree__count">{topic.questions}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
