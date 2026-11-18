import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, post, useApi } from "../api";
import { Prose } from "../Prose";

/* The quiz list and the runner. The runner is the one page that has to keep the
   answers off the wire until submission, so it asks the API for a paper without a
   key and sends the paper back for marking. */

type Quiz = {
  uid: string;
  title: string;
  description: string | null;
  owner: string;
  is_private: boolean;
  is_mine: boolean;
  questions: number;
  taken: boolean;
  my_score: number | null;
};

export function QuizListPage() {
  const { data, error, loading } = useApi<{ quizzes: Quiz[] }>("/api/quizzes");

  return (
    <div className="doc">
      <header className="resource__head">
        <div>
          <h1 className="doc__title">Quiz</h1>
          <p className="muted">Timed papers, shared by link.</p>
        </div>
        <Link className="btn" to="/quiz/new">
          Build a quiz
        </Link>
      </header>

      {loading && <p className="muted">Loading...</p>}
      {error && <p className="form-error">{error}</p>}

      <ul className="quizlist">
        {(data?.quizzes ?? []).map((quiz) => (
          <li key={quiz.uid}>
            <Link className="quizlist__item" to={`/quiz/${quiz.uid}`}>
              <div>
                <span className="quizlist__title">{quiz.title}</span>
                <span className="muted"> · {quiz.questions} questions · {quiz.owner}</span>
              </div>
              <div className="quizlist__meta">
                {quiz.taken && <span className="chip chip--ok">taken</span>}
                {quiz.is_private && <span className="chip">unlisted</span>}
              </div>
            </Link>
          </li>
        ))}
      </ul>

      {!loading && (data?.quizzes ?? []).length === 0 && (
        <p className="muted">No quizzes yet.</p>
      )}
    </div>
  );
}

type Paper = {
  uid: string;
  title: string;
  questions: { id: number; body_html: string; choices: Record<string, string | null> }[];
};

export function QuizRunPage() {
  const { uid } = useParams();
  const [paper, setPaper] = useState<Paper | null>(null);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [result, setResult] = useState<{ score: number; total: number; time?: number } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const quiz = useApi<{ locked: string | null; title: string; questions: unknown[] }>(
    `/api/quizzes/${uid}`
  );

  async function start() {
    setBusy(true);
    try {
      setPaper(await post<Paper>(`/api/quizzes/${uid}/start`, {}));
    } catch (problem) {
      setError((problem as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    setBusy(true);
    try {
      const marked = await post<{ score: number; total: number }>(
        `/api/quizzes/${uid}/submit`,
        { answers }
      );
      setResult(marked);
    } catch (problem) {
      setError((problem as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <div className="doc">
        <h1 className="doc__title">{result.score} / {result.total}</h1>
        <p className="muted">Submitted. Your first attempt is the one that counts.</p>
        <Link className="btn" to="/quiz">
          Back to the list
        </Link>
      </div>
    );
  }

  if (!paper) {
    /* A paper holding a withdrawn question cannot be sat, and saying so is part of
       the feature: silently starting it would mark people against a question the
       bank no longer stands behind. */
    if (quiz.data?.locked) {
      return (
        <div className="doc">
          <h1 className="doc__title">{quiz.data.title}</h1>
          <p className="form-error">{quiz.data.locked}</p>
          <p className="muted">
            The owner can rebuild the paper without it; a locked paper stays closed.
          </p>
          <Link className="btn" to="/quiz">
            Back to the list
          </Link>
        </div>
      );
    }

    return (
      <div className="doc">
        <h1 className="doc__title">{quiz.data?.title ?? "Ready?"}</h1>
        <p className="muted">
          {quiz.data ? `${quiz.data.questions.length} questions. The clock starts when you do.` : ""}
        </p>
        {error && <p className="form-error">{error}</p>}
        <button type="button" className="btn" onClick={start} disabled={busy || quiz.loading}>
          {busy ? "Starting..." : "Start"}
        </button>
      </div>
    );
  }

  return (
    <div className="doc">
      <h1 className="doc__title">{paper.title}</h1>
      <ol className="quizrun">
        {paper.questions.map((question, index) => (
          <li key={question.id}>
            <div className="quizrun__q">
              <span className="plist__id">{index + 1}</span>
              <Prose html={question.body_html} />
            </div>
            <div className="q__choices">
              {Object.entries(question.choices)
                .filter(([, text]) => text)
                .map(([letter, text]) => (
                  <button
                    key={letter}
                    type="button"
                    className={`q__choice${answers[question.id] === letter ? " is-picked" : ""}`}
                    onClick={() => setAnswers((current) => ({ ...current, [question.id]: letter }))}
                  >
                    <span className="q__letter">{letter}</span>
                    <span>{text}</span>
                  </button>
                ))}
            </div>
          </li>
        ))}
      </ol>
      <button type="button" className="btn" onClick={submit} disabled={busy}>
        {busy ? "Submitting..." : "Submit"}
      </button>
    </div>
  );
}

export function QuizBuildPage() {
  const [title, setTitle] = useState("");
  const [count, setCount] = useState(10);
  const [toast, setToast] = useState("");
  const subjects = useApi<{ id: number; name: string }[]>("/api/subjects");

  async function create() {
    try {
      const created = await api<{ uid: string }>("/api/quizzes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, questions: [], random: { count } }),
      });
      setToast(`Created: /quiz/${created.uid}`);
    } catch (problem) {
      setToast((problem as Error).message);
    }
  }

  return (
    <div className="doc">
      <h1 className="doc__title">Build a quiz</h1>
      <p className="muted">
        {subjects.loading ? "Loading subjects..." : "A random paper from the bank."}
      </p>
      <label className="field">
        Title
        <input value={title} onChange={(event) => setTitle(event.target.value)} />
      </label>
      <label className="field">
        Questions
        <input
          type="number"
          min={1}
          max={100}
          value={count}
          onChange={(event) => setCount(Number(event.target.value))}
        />
      </label>
      <button type="button" className="btn" onClick={create} disabled={!title.trim()}>
        Create
      </button>
      {toast && <p className="muted">{toast}</p>}
    </div>
  );
}
