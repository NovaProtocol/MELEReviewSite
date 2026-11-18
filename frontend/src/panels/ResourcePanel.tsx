import { useState } from "react";
import { useApi, type Question } from "../api";
import { Prose } from "../Prose";
import { openPanel } from "../workspaceBus";

/* A topic's reading material: notes and the reference sheet, in their own panel. */
export function ResourcePanel({ topicId }: { topicId: number }) {
  const [tab, setTab] = useState<"resources" | "reference">("resources");
  const { data, loading, error } = useApi<Record<string, { html: string }>>(
    `/api/topics/${topicId}/pages`,
    [topicId]
  );

  return (
    <div className="resource-panel">
      <div className="resource-panel__tabs">
        <button
          type="button"
          className={`tab${tab === "resources" ? " is-active" : ""}`}
          onClick={() => setTab("resources")}
        >
          Resources
        </button>
        <button
          type="button"
          className={`tab${tab === "reference" ? " is-active" : ""}`}
          onClick={() => setTab("reference")}
        >
          Reference
        </button>
      </div>
      <div className="resource-panel__body">
        {loading && <p className="muted pad">Loading...</p>}
        {error && <p className="form-error pad">{error}</p>}
        {data?.[tab]?.html ? (
          <Prose html={data[tab].html} />
        ) : (
          !loading && <p className="muted pad">Nothing written for this panel yet.</p>
        )}
      </div>
    </div>
  );
}

/* A tag's questions, which is the same list a topic gives you. */
export function TaggedPanel({ tag }: { tag: string }) {
  const { data, loading, error } = useApi<Question[]>(
    `/api/tags/${encodeURIComponent(tag)}/questions`,
    [tag]
  );

  return (
    <div className="pane">
      <header className="pane__head">
        <span className="chip">#{tag}</span>
        <span className="muted">{(data ?? []).length} questions</span>
      </header>
      {loading && <p className="muted pad">Loading...</p>}
      {error && <p className="form-error pad">{error}</p>}
      <ul className="plist">
        {(data ?? []).map((question) => (
          <li key={question.id}>
            <button
              type="button"
              className="plist__card"
              onClick={() =>
                openPanel({
                  kind: "question",
                  title: `#${question.id}`,
                  params: { questionId: String(question.id) },
                })
              }
            >
              <div className="plist__meta">
                <span className="plist__id">#{question.id}</span>
                {question.kind && <span className="chip">{question.kind}</span>}
                {question.attempt?.solved && <span className="chip chip--ok">answered</span>}
              </div>
              <Prose className="plist__body" html={question.body_html} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
