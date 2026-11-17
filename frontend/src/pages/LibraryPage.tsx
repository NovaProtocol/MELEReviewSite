import { Link, useParams } from "react-router-dom";
import { useApi, type Subject, type Question } from "../api";
import { Prose } from "../Prose";

/* The front door: subjects, topics, and a way in. A document, not a workspace. */

export function LibraryPage() {
  const { data, error, loading } = useApi<Subject[]>("/api/subjects");

  if (loading) return <p className="muted pad">Loading the library...</p>;
  if (error) return <p className="form-error pad">{error}</p>;

  return (
    <div className="doc">
      <h1 className="doc__title">Library</h1>
      <div className="doc__subjects">
        {(data ?? []).map((subject) => (
          <section className="doc__subject" key={subject.id}>
            <h2 className="doc__heading">{subject.name}</h2>
            <ul className="doc__topics">
              {subject.topics.map((topic) => (
                <li key={topic.id}>
                  <Link className="doc__topic" to={`/library/${topic.id}`}>
                    <span>{topic.name}</span>
                    <span className="doc__count">
                      {topic.questions} question{topic.questions === 1 ? "" : "s"}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}

/* One topic: its notes and its problem set, which is what a reader browsing wants
   to see. Opening a problem is what switches to the workspace. */

export function TopicPage() {
  const { topicId } = useParams();
  const id = Number(topicId);
  const questions = useApi<Question[]>(`/api/topics/${id}/questions?sort=newest`, [id]);
  const pages = useApi<Record<string, { html: string }>>(`/api/topics/${id}/pages`, [id]);
  const subjects = useApi<Subject[]>("/api/subjects");

  const topic = (subjects.data ?? [])
    .flatMap((subject) => subject.topics.map((item) => ({ ...item, subject: subject.name })))
    .find((item) => item.id === id);

  return (
    <div className="doc">
      <nav className="doc__crumbs">
        <Link to="/library">Library</Link>
        <span>/</span>
        <span>{topic?.subject ?? ""}</span>
      </nav>
      <h1 className="doc__title">{topic?.name ?? "Topic"}</h1>

      <div className="doc__split">
        <section>
          <h2 className="doc__heading">Problems</h2>
          {questions.loading && <p className="muted">Loading...</p>}
          <ul className="doc__problems">
            {(questions.data ?? []).map((question) => (
              <li key={question.id}>
                <Link className="doc__problem" to={`/library/${id}/${question.id}`}>
                  <div className="doc__problem-meta">
                    <span className="qsplit__id">#{question.id}</span>
                    {question.kind && <span className="chip">{question.kind}</span>}
                    {question.attempt?.solved && <span className="chip chip--ok">answered</span>}
                  </div>
                  <Prose className="doc__problem-body" html={question.body_html} />
                </Link>
              </li>
            ))}
          </ul>
          {!questions.loading && (questions.data ?? []).length === 0 && (
            <p className="muted">Nothing here yet.</p>
          )}
        </section>

        <section>
          <h2 className="doc__heading">Notes</h2>
          {pages.data?.resources?.html ? (
            <Prose className="doc__notes" html={pages.data.resources.html} />
          ) : (
            <p className="muted">Nothing here yet.</p>
          )}
        </section>
      </div>
    </div>
  );
}
