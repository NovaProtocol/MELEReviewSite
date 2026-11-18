import { useEffect, useState } from "react";
import { api, useApi } from "../api";
import { Prose } from "../Prose";
import { openPanel } from "../workspaceBus";

/* The quiz builder, doing what the server already supports: pick a topic, choose
   how many questions, and create. The endpoint takes `selections` — topic id to
   count — which is what "Choose at least one question" was actually complaining
   about when this sent an empty array. */

type Subject = {
  id: number;
  name: string;
  topics: { id: number; name: string; questions: number }[];
};

type Quiz = {
  uid: string;
  title: string;
  questions: number;
  taken: boolean;
  is_private: boolean;
  owner: string;
};

export function QuizBuilderPanel() {
  const subjects = useApi<Subject[]>("/api/subjects");
  const quizzes = useApi<{ quizzes: Quiz[] }>("/api/quizzes");
  const [title, setTitle] = useState("");
  const [selections, setSelections] = useState<Record<number, number>>({});
  const [timer, setTimer] = useState(30);
  const [isPrivate, setPrivate] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const chosen = Object.entries(selections).filter(([, count]) => count > 0);
  const total = chosen.reduce((sum, [, count]) => sum + count, 0);

  async function create() {
    if (!total) {
      setMessage("Choose at least one question.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const created = await api<{ uid: string }>("/api/quizzes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title.trim() || "Untitled paper",
          selections: Object.fromEntries(
            chosen.map(([topicId, count]) => [Number(topicId), count])
          ),
          timer_minutes: timer,
          is_private: isPrivate,
        }),
      });
      setMessage(`Created. /quiz/${created.uid}`);
      setTitle("");
      setSelections({});
      quizzes.reload();
    } catch (problem) {
      setMessage((problem as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(uid: string) {
    try {
      await api(`/api/quizzes/${uid}`, { method: "DELETE" });
      quizzes.reload();
    } catch (problem) {
      setMessage((problem as Error).message);
    }
  }

  return (
    <div className="quizbuilder">
      <section className="quizbuilder__build">
        <h3 className="quizbuilder__head">New paper</h3>

        <label className="field">
          Title
          <input value={title} onChange={(event) => setTitle(event.target.value)} />
        </label>

        <div className="quizbuilder__row">
          <label className="field">
            Timer (minutes)
            <input
              type="number"
              min={0}
              max={600}
              value={timer}
              onChange={(event) => setTimer(Number(event.target.value))}
            />
          </label>
          <label className="switch quizbuilder__private">
            <input
              type="checkbox"
              checked={isPrivate}
              onChange={() => setPrivate(!isPrivate)}
            />
            <span className="switch__track">
              <span className="switch__dot" />
            </span>
            <span className="switch__label">Unlisted</span>
          </label>
        </div>

        <h4 className="quizbuilder__sub">Questions by topic</h4>
        <div className="quizbuilder__topics">
          {(subjects.data ?? []).map((subject) => (
            <div key={subject.id} className="quizbuilder__group">
              <span className="quizbuilder__subject">{subject.name}</span>
              {subject.topics.map((topic) => (
                <label key={topic.id} className="quizbuilder__topic">
                  <span>{topic.name}</span>
                  <input
                    type="number"
                    min={0}
                    max={topic.questions}
                    value={selections[topic.id] ?? 0}
                    onChange={(event) =>
                      setSelections({
                        ...selections,
                        [topic.id]: Math.max(0, Math.min(topic.questions, Number(event.target.value))),
                      })
                    }
                    aria-label={`Questions from ${topic.name}`}
                  />
                  <span className="quizbuilder__available">of {topic.questions}</span>
                </label>
              ))}
            </div>
          ))}
        </div>

        <footer className="quizbuilder__foot">
          <span className="muted">{total} question{total === 1 ? "" : "s"} selected</span>
          <button type="button" className="btn btn--primary" onClick={create} disabled={busy}>
            {busy ? "Creating..." : "Create paper"}
          </button>
        </footer>
        {message && <p className="muted">{message}</p>}
      </section>

      <section className="quizbuilder__list">
        <h3 className="quizbuilder__head">Your papers</h3>
        {quizzes.loading && <p className="muted">Loading...</p>}
        <ul>
          {(quizzes.data?.quizzes ?? []).map((quiz) => (
            <li key={quiz.uid} className="quizbuilder__item">
              <a href={`/quiz/${quiz.uid}`}>{quiz.title}</a>
              <span className="muted">
                {quiz.questions} q · {quiz.owner}
              </span>
              {quiz.taken && <span className="chip chip--ok">taken</span>}
              <button type="button" className="link" onClick={() => remove(quiz.uid)}>
                delete
              </button>
            </li>
          ))}
        </ul>
        {(quizzes.data?.quizzes ?? []).length === 0 && !quizzes.loading && (
          <p className="muted">Nothing yet.</p>
        )}
      </section>
    </div>
  );
}

/* The admin surface, as a panel. */
export function AdminPanel() {
  const overview = useApi<Record<string, number | Record<string, number>>>("/api/admin/overview");
  const users = useApi<{ items: { id: number; username: string; status: string; is_system_admin: boolean }[] }>(
    "/api/admin/users?per_page=100"
  );
  const [note, setNote] = useState("");

  useEffect(() => {
    if (overview.error) setNote(overview.error);
  }, [overview.error]);

  const total = (value: number | Record<string, number> | undefined) =>
    typeof value === "number" ? value : value ? Object.values(value).reduce((a, b) => a + b, 0) : 0;

  return (
    <div className="adminpanel">
      <div className="stats">
        {(
          [
            ["Members", total(overview.data?.users)],
            ["Questions", total(overview.data?.questions)],
            ["Solutions", total(overview.data?.solutions)],
            ["Reports", total(overview.data?.open_reports)],
          ] as const
        ).map(([label, value]) => (
          <div className="stat" key={label}>
            <span className="stat__value">{value}</span>
            <span className="stat__label">{label}</span>
          </div>
        ))}
      </div>

      <table className="table">
        <thead>
          <tr>
            <th>Member</th>
            <th>Status</th>
            <th>Role</th>
          </tr>
        </thead>
        <tbody>
          {(users.data?.items ?? []).map((user) => (
            <tr key={user.id}>
              <td>{user.username}</td>
              <td>
                <span className={user.status === "active" ? "chip chip--ok" : "chip"}>
                  {user.status}
                </span>
              </td>
              <td>{user.is_system_admin ? "system admin" : "member"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {note && <p className="form-error">{note}</p>}
    </div>
  );
}


/* Search, as a tool panel: it searches the bank and opens what it finds. */
export function SearchPanel() {
  const [query, setQuery] = useState("");
  const trimmed = query.trim();
  const { data, loading } = useApi<{
    results: { id: number; topic_id: number; body_html: string }[];
  }>(trimmed.length >= 2 ? `/api/search?q=${encodeURIComponent(trimmed)}` : null, [trimmed]);

  return (
    <div className="pane">
      <input
        className="searchbig"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="pressure, carnot, beam deflection..."
        aria-label="Search"
        autoFocus
      />
      {loading && <p className="muted pad">Searching...</p>}
      {trimmed.length >= 2 && !loading && (data?.results ?? []).length === 0 && (
        <p className="muted pad">Nothing matched.</p>
      )}
      <ul className="plist">
        {(data?.results ?? []).map((result) => (
          <li key={result.id}>
            <button
              type="button"
              className="plist__card"
              onClick={() =>
                openPanel({
                  kind: "question",
                  title: `#${result.id}`,
                  params: { questionId: String(result.id) },
                })
              }
            >
              <div className="plist__meta">
                <span className="plist__id">#{result.id}</span>
              </div>
              <Prose className="plist__body" html={result.body_html} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
