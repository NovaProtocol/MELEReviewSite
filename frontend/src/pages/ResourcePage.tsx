import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi, type Subject } from "../api";
import { Prose } from "../Prose";
import { Icon } from "../Chrome";

/* Learning material, and nothing else.

   This used to share a page with the problem list, which meant a reader who came
   to read could not tell what was reference and what was homework. It is its own
   route now, with the reference sheet beside it and no questions anywhere. */

type Page = { kind: string; title: string; html: string; updated_at: string | null };

export function ResourcePage() {
  const { topicId } = useParams();
  const id = Number(topicId);
  const pages = useApi<Record<string, Page>>(`/api/topics/${id}/pages`, [id]);
  const subjects = useApi<Subject[]>("/api/subjects");
  const [tab, setTab] = useState<"resources" | "reference">("resources");

  const topic = (subjects.data ?? [])
    .flatMap((subject) => subject.topics.map((item) => ({ ...item, subject: subject.name })))
    .find((item) => item.id === id);

  const page = pages.data?.[tab];

  return (
    <div className="resource">
      <nav className="doc__crumbs">
        <Link to="/problem-sets">Problem sets</Link>
        <span>/</span>
        <span>{topic?.subject ?? ""}</span>
      </nav>

      <header className="resource__head">
        <div>
          <h1 className="doc__title">{topic?.name ?? "Topic"}</h1>
          <p className="muted">
            {tab === "resources" ? "Study notes" : "Formulas, constants and tables"}
          </p>
        </div>
        <Link className="btn" to={`/problem-sets/${id}`}>
          <Icon name="quiz" size={15} /> Practise this topic
        </Link>
      </header>

      <div className="tabs">
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

      {pages.loading && <p className="muted">Loading...</p>}
      {pages.error && <p className="form-error">{pages.error}</p>}
      {page?.html ? (
        <article className="resource__body">
          <Prose html={page.html} />
        </article>
      ) : (
        !pages.loading && (
          <div className="resource__empty">
            <p className="muted">Nothing written for this panel yet.</p>
          </div>
        )
      )}
    </div>
  );
}
