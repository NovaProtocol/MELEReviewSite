import { useMemo, useState } from "react";
import { useApi } from "../api";
import { openPanel } from "../workspaceBus";
import { useRowMenu, type RowAction } from "../workspace/RowMenu";

/* The explorer, as a tree you drill into.

   One branch open at a time: opening a subject hides every other subject, and
   opening a topic hides its siblings and shows that topic's questions. A tree that
   expands everything at once is a directory listing, and the eye has nowhere to
   start. Indentation carries the levels: subject at 0, topic at 1, question at 2. */

export type ExplorerMode = "library" | "problems" | "tags";

type Subject = {
  id: number;
  name: string;
  topics: { id: number; name: string; questions: number; answers: number }[];
};

type Question = {
  id: number;
  topic_id: number;
  body: string;
  kind: string;
  attempt?: { solved: boolean } | null;
};

export type ExplorerFilters = {
  answered: "all" | "answered" | "unanswered";
  kind: "" | "identification" | "computation";
  hasSolution: boolean;
  withImages: boolean;
};

const EMPTY_FILTERS: ExplorerFilters = {
  answered: "all",
  kind: "",
  hasSolution: false,
  withImages: false,
};

export function Explorer({
  mode,
  onMode,
  filters,
}: {
  mode: ExplorerMode;
  onMode: (mode: ExplorerMode) => void;
  filters: ExplorerFilters;
}) {
  const subjects = useApi<Subject[]>("/api/subjects");
  const tags = useApi<{ id: number; name: string; questions: number }[]>("/api/tags?counts=true");

  const [query, setQuery] = useState("");
  // One open branch at a time: [subjectId] or [subjectId, topicId].
  const [branch, setBranch] = useState<number[]>([]);

  const needle = query.trim().toLowerCase();

  const visible = useMemo(() => {
    const list = subjects.data ?? [];
    if (!needle) return list;
    return list
      .map((subject) => ({
        ...subject,
        topics: subject.topics.filter((topic) => topic.name.toLowerCase().includes(needle)),
      }))
      .filter(
        (subject) =>
          subject.topics.length > 0 || subject.name.toLowerCase().includes(needle)
      );
  }, [subjects.data, needle]);

  const openSubject = (id: number) =>
    setBranch((current) => (current[0] === id && current.length === 1 ? [] : [id]));

  const openTopic = (subjectId: number, topicId: number) =>
    setBranch((current) =>
      current[0] === subjectId && current[1] === topicId ? [subjectId] : [subjectId, topicId]
    );

  function openResource(topic: { id: number; name: string }) {
    openPanel({ kind: "resource", title: topic.name, params: { topicId: String(topic.id) } });
  }

  return (
    <div className="explorer-panel">
      <div className="explorer-panel__modes" role="tablist">
        {(
          [
            ["library", "Library"],
            ["problems", "Problems"],
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

      {mode !== "tags" && (
        <div className="explorer-panel__search">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter topics"
            aria-label="Filter topics"
          />
          {query && (
            <button type="button" className="link" onClick={() => setQuery("")}>
              clear
            </button>
          )}
        </div>
      )}

      <div className="explorer-panel__body">
        {mode === "tags" ? (
          <ul className="tree__list">
            {(tags.data ?? []).map((tag) => (
              <li key={tag.id}>
                <button
                  type="button"
                  className="tree__row depth-0"
                  onClick={() =>
                    openPanel({
                      kind: "tagged",
                      title: `#${tag.name}`,
                      params: { tag: tag.name, filters: JSON.stringify(filters) },
                    })
                  }
                >
                  <span className="tree__label">#{tag.name}</span>
                  <span className="tree__count">{tag.questions}</span>
                </button>
              </li>
            ))}
            {(tags.data ?? []).length === 0 && (
              <li className="muted pad">No tags yet.</li>
            )}
          </ul>
        ) : (
          <ul className="tree__list">
            {subjects.loading && <li className="muted pad">Loading...</li>}
            {visible.map((subject) => {
              const subjectOpen = branch[0] === subject.id;
              return (
                <li key={subject.id}>
                  <button
                    type="button"
                    className={`tree__row depth-0${subjectOpen ? " is-open" : ""}`}
                    onClick={() => openSubject(subject.id)}
                    aria-expanded={subjectOpen}
                  >
                    <span className={`tree__caret${subjectOpen ? " is-open" : ""}`}>▸</span>
                    <span className="tree__label">{subject.name}</span>
                    <span className="tree__count">{subject.topics.length}</span>
                  </button>

                  {subjectOpen && (
                    <ul className="tree__list">
                      {subject.topics.map((topic) => {
                        const topicOpen = branch[1] === topic.id;
                        return (
                          <li key={topic.id}>
                            <TopicRow
                              topic={topic}
                              open={topicOpen}
                              onOpen={() => openTopic(subject.id, topic.id)}
                              onResource={() => openResource(topic)}
                              mode={mode}
                              activeLabel={mode === "library" ? "OPEN" : String(topic.questions)}
                            />

                            {topicOpen && (
                              <TopicQuestions
                                topicId={topic.id}
                                mode={mode}
                                filters={filters}
                                onOpenResource={() => openResource(topic)}
                              />
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

/* One topic, with the menu code-server's tree has: open, open the notes beside it,
   and copy the address so the topic can be linked. The row stays a button, because
   clicking it is still the common thing. */
function TopicRow({
  topic,
  open,
  onOpen,
  onResource,
  mode,
  activeLabel,
}: {
  topic: { id: number; name: string; questions: number };
  open: boolean;
  onOpen: () => void;
  onResource: () => void;
  mode: ExplorerMode;
  activeLabel: string;
}) {
  const { handlers, menu } = useRowMenu((): RowAction[] => [
    { label: open ? "Collapse" : "Expand", run: onOpen },
    {
      label: mode === "library" ? "Open notes" : "Open problem set",
      run: mode === "library" ? onResource : onOpen,
    },
    {
      label: "Copy link",
      run: () => {
        const url = `${window.location.origin}/resource/${topic.id}`;
        void navigator.clipboard?.writeText(url);
      },
    },
  ]);

  return (
    <>
      <button
        type="button"
        className={`tree__row depth-1${open ? " is-open" : ""}`}
        onClick={onOpen}
        aria-expanded={open}
        {...handlers}
      >
        <span className={`tree__caret${open ? " is-open" : ""}`}>▸</span>
        <span className="tree__label">{topic.name}</span>
        <span className="tree__count">{activeLabel}</span>
      </button>
      {menu}
    </>
  );
}

/* The questions of one topic, indented a level below it. In the library the notes
   are the content, so the row offers them; in the problem sets the questions are
   the content, so the rows are the questions. */
function TopicQuestions({
  topicId,
  mode,
  filters,
  onOpenResource,
}: {
  topicId: number;
  mode: ExplorerMode;
  filters: ExplorerFilters;
  onOpenResource: () => void;
}) {
  const params = new URLSearchParams({ sort: "newest" });
  if (filters.answered === "answered") params.set("answer_state", "answered");
  if (filters.answered === "unanswered") params.set("answer_state", "unanswered");
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.hasSolution) params.set("has_solution", "true");

  const { data, loading } = useApi<Question[]>(
    `/api/topics/${topicId}/questions?${params}`,
    [topicId, JSON.stringify(filters)]
  );

  const shown = (data ?? []).filter((question) =>
    filters.withImages ? question.body.includes("![") : true
  );

  if (mode === "library") {
    return (
      <ul className="tree__list">
        <li>
          <button type="button" className="tree__row depth-2" onClick={onOpenResource}>
            <span className="tree__label">Resources</span>
          </button>
        </li>
        <li>
          <button type="button" className="tree__row depth-2" onClick={onOpenResource}>
            <span className="tree__label">Reference</span>
          </button>
        </li>
        <li>
          <button
            type="button"
            className="tree__row depth-2"
            onClick={() =>
              openPanel({
                kind: "problems",
                title: `Problems in ${topicId}`,
                params: { topicId: String(topicId) },
              })
            }
          >
            <span className="tree__label muted">Practise this topic</span>
          </button>
        </li>
      </ul>
    );
  }

  return (
    <ul className="tree__list">
      {loading && <li className="muted pad">Loading...</li>}
      {shown.map((question) => (
        <li key={question.id}>
          <button
            type="button"
            className="tree__row depth-2"
            onClick={() =>
              openPanel({
                kind: "question",
                title: `#${question.id}`,
                params: { questionId: String(question.id) },
              })
            }
          >
            <span className="tree__label">
              <span className="tree__qid">#{question.id}</span>{" "}
              {question.body.replace(/[*_#$`]/g, "").slice(0, 46)}
            </span>
            {question.attempt?.solved && <span className="tree__solved">✓</span>}
          </button>
        </li>
      ))}
      {!loading && shown.length === 0 && (
        <li className="muted pad">Nothing matches the filters.</li>
      )}
    </ul>
  );
}

export { EMPTY_FILTERS };
