import { useState } from "react";
import { useApi } from "../api";
import { Prose } from "../Prose";

/* A topic's notes and reference sheet. Markdown arrives already rendered by the
   server, so this panel shows exactly what the classic page shows. */

type Page = { kind: string; title: string; html: string; updated_at: string | null; may_edit: boolean };

export function TopicPage({ topicId }: { topicId: number }) {
  const [tab, setTab] = useState<"resources" | "reference">("resources");
  const { data, error, loading } = useApi<Record<string, Page>>(
    `/api/topics/${topicId}/pages`,
    [topicId]
  );

  if (loading) return <p className="muted pad">Loading notes...</p>;
  if (error) return <p className="form-error pad">{error}</p>;
  const page = data?.[tab];

  return (
    <div className="topic-page">
      <div className="topic-page__tabs">
        <button
          className={tab === "resources" ? "chip is-on" : "chip"}
          onClick={() => setTab("resources")}
        >
          Resources
        </button>
        <button
          className={tab === "reference" ? "chip is-on" : "chip"}
          onClick={() => setTab("reference")}
        >
          Reference
        </button>
      </div>
      {page?.html ? (
        <Prose className="md topic-page__body" html={page.html} />
      ) : (
        <p className="muted pad">Nothing here yet.</p>
      )}
    </div>
  );
}
