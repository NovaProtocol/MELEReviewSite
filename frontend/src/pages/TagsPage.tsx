import { Link, useParams } from "react-router-dom";
import { useApi } from "../api";
import { Prose } from "../Prose";

type Tag = { id: number; name: string; questions: number };

type TaggedQuestion = { id: number; topic_id: number; body_html: string };

export function TagsPage() {
  const { data, error, loading } = useApi<Tag[]>("/api/tags?counts=true");

  return (
    <div className="doc">
      <h1 className="doc__title">Tags</h1>
      {loading && <p className="muted">Loading...</p>}
      {error && <p className="form-error">{error}</p>}
      <div className="tagcloud">
        {(data ?? []).map((tag) => (
          <Link key={tag.id} className="tagcloud__item" to={`/tags/${tag.name}`}>
            {tag.name}
            <span className="tagcloud__count">{tag.questions}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function TagPage() {
  const { name } = useParams();
  const { data, error, loading } = useApi<TaggedQuestion[]>(
    `/api/tags/${encodeURIComponent(name ?? "")}/questions`
  );

  return (
    <div className="doc">
      <nav className="doc__crumbs">
        <Link to="/tags">Tags</Link>
        <span>/</span>
        <span>{name}</span>
      </nav>
      <h1 className="doc__title">{name}</h1>
      {loading && <p className="muted">Loading...</p>}
      {error && <p className="form-error">{error}</p>}
      {!loading && !error && (data ?? []).length === 0 && (
        <p className="muted">No questions carry this tag.</p>
      )}
      <ul className="doc__problems">
        {(data ?? []).map((question) => (
          <li key={question.id}>
            <Link
              className="doc__problem"
              to={`/app?panel=question&questionId=${question.id}&topicId=${question.topic_id}`}
            >
              <div className="doc__problem-meta">
                <span className="plist__id">#{question.id}</span>
              </div>
              <Prose className="doc__problem-body" html={question.body_html} />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
