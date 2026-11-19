import { useEffect, useRef, useState } from "react";
import { useSharedText } from "../workspace/sharedDoc";
import { EditorMount } from "../workspace/EditorMount";
import { invalidate, post, useApi, type Question } from "../api";
import { Prose } from "../Prose";
import { openPanel } from "../workspaceBus";

/* A topic's problem list, in its own panel. A card opens the question; the list
   stays where it is. */
export function ProblemsPanel({ topicId }: { topicId: number }) {
  const { data, loading, error } = useApi<Question[]>(
    `/api/topics/${topicId}/questions?sort=newest`,
    [topicId]
  );

  return (
    <div className="pane">
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
                  params: { questionId: String(question.id), topicId: String(topicId) },
                })
              }
            >
              <div className="plist__meta">
                <span className="plist__id">#{question.id}</span>
                {question.kind && <span className="chip">{question.kind}</span>}
                {question.attempt?.solved && <span className="chip chip--ok">answered</span>}
                {Boolean(question.solution_count) && (
                  <span className="chip">{question.solution_count} sol</span>
                )}
              </div>
              <Prose className="plist__body" html={question.body_html} />
            </button>
          </li>
        ))}
      </ul>
      {!loading && (data ?? []).length === 0 && <p className="muted pad">Nothing here yet.</p>}
    </div>
  );
}

/* One question: the problem on the left, this member's solution on the right, and
   a drag handle between them. The width is remembered. */
export function QuestionPanel({ questionId }: { questionId: number }) {
  const { data, loading, error, reload } = useApi<Question>(
    `/api/questions/${questionId}`,
    [questionId]
  );
  const [width, setWidth] = useState(() => {
    const saved = Number(localStorage.getItem("mele.solution-width"));
    return Number.isFinite(saved) && saved > 200 ? saved : 320;
  });
  const [available, setAvailable] = useState(0);
  const shell = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = shell.current;
    if (!node) return;
    // Observe the panel, not the window: docking changes the panel's width without
    // any window resize, and a stale measurement is what squeezed the problem.
    const observer = new ResizeObserver(() => setAvailable(node.clientWidth));
    observer.observe(node);
    setAvailable(node.clientWidth);
    return () => observer.disconnect();
  }, []);

  // Never let the solution take more than two thirds of the panel: a problem
  // squeezed to one character per line is not a problem you can read.
  /* The problem is the reason the panel exists, so the solution never takes more
     than half of it. Below 620px there is no room for two readable columns, so the
     solution goes underneath and the problem keeps the full width. */
  const stacked = available > 0 && available < 620;
  const solutionWidth = available ? Math.min(width, Math.round(available * 0.45)) : width;

  function startResize(event: React.PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    const container = event.currentTarget.parentElement;
    const bounds = container?.getBoundingClientRect();
    if (!bounds) return;
    const move = (moveEvent: PointerEvent) => {
      // Measured against the panel, not the window: the panel is what is narrow.
      const next = Math.min(
        Math.max(bounds.right - moveEvent.clientX, 220),
        Math.round(bounds.width * 0.75)
      );
      setWidth(next);
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      localStorage.setItem("mele.solution-width", String(width));
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  }

  if (loading) return <p className="muted pad">Loading question...</p>;
  if (error) return <p className="form-error pad">{error}</p>;
  if (!data) return null;

  return (
    <div
      className="qpanel"
      ref={shell}
      style={
        stacked
          ? { gridTemplateColumns: "minmax(0, 1fr)", gridTemplateRows: "minmax(0, 1fr) auto" }
          : { gridTemplateColumns: `minmax(0, 1fr) 5px ${solutionWidth}px` }
      }
    >
      <section className="qpanel__problem">
        <div className="qpanel__scroll">
          <Prose className="q-prose" html={data.body_html} />
          <Choices data={data} onAnswered={reload} />
          {data.note_html && (
            <details className="q__note">
              <summary>Note</summary>
              <Prose html={data.note_html} />
            </details>
          )}
          <Solutions data={data} />
        </div>
      </section>

      {!stacked && (
      <div
        className="qpanel__resize"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize the solution"
        onPointerDown={startResize}
      />
      )}

      <section className="qpanel__solution" style={stacked ? { height: "42%" } : undefined}>
        <SolutionPane questionId={questionId} />
      </section>
    </div>
  );
}

function Choices({ data, onAnswered }: { data: Question; onAnswered: () => void }) {
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  const solved = Boolean(data.attempt?.solved);

  async function answer(letter: string) {
    if (busy || solved) return;
    setBusy(true);
    setFeedback("");
    try {
      const result = await post<{ is_correct: boolean; attempts: number }>(
        `/api/questions/${data.id}/attempt`,
        { chosen: letter }
      );
      invalidate("/api/questions/");
      invalidate("/api/topics/");
      setFeedback(
        result.is_correct
          ? `Correct on try ${result.attempts}. Other people's working is below.`
          : "Not this one. Try another choice."
      );
      onAnswered();
    } catch (problem) {
      setFeedback((problem as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="q__choices">
        {Object.entries(data.choices)
          .filter(([, text]) => text)
          .map(([letter, text]) => {
            const picked = data.attempt?.chosen === letter;
            const right = solved && data.attempt?.is_correct && picked;
            const wrong = !right && picked && Boolean(data.attempt);
            return (
              <button
                key={letter}
                type="button"
                className={`q__choice${right ? " is-right" : ""}${wrong ? " is-wrong" : ""}`}
                onClick={() => answer(letter)}
                disabled={solved || busy}
                title={solved ? "This sheet is closed" : `Answer ${letter}`}
              >
                <span className="q__letter">{letter}</span>
                <span>{text}</span>
              </button>
            );
          })}
      </div>

      {feedback && (
        <p className={feedback.startsWith("Correct") ? "q__feedback is-ok" : "q__feedback"}>
          {feedback}
        </p>
      )}
      {solved && !feedback && <p className="q__feedback is-ok">Correct.</p>}
    </>
  );
}

function Solutions({ data }: { data: Question }) {
  const solutions = (data.solutions ?? []) as {
    id: number;
    author: string;
    body_html: string;
    date_created: string;
  }[];

  return (
    <section className="solutions">
      <h3 className="solutions__head">
        Solutions <span className="solutions__count">{solutions.length}</span>
      </h3>

      {!data.may_see_solutions && (
        <p className="muted">Answer correctly to unlock other people's working.</p>
      )}
      {data.may_see_solutions && solutions.length === 0 && (
        <p className="muted">Nobody has posted one yet. Write yours on the right.</p>
      )}

      {solutions.map((solution) => (
        <article className="solution" key={solution.id}>
          <header className="solution__head">
            <span className="solution__author">{solution.author}</span>
            <time className="solution__time">{solution.date_created?.slice(0, 10)}</time>
          </header>
          <Prose className="solution__body" html={solution.body_html} />
        </article>
      ))}
    </section>
  );
}

function SolutionPane({ questionId }: { questionId: number }) {
  const { data, error, loading, reload } = useApi<{ body: string; published: boolean }>(
    `/api/questions/${questionId}/draft`,
    [questionId]
  );
  /* The text lives in a shared document keyed by question: open the same question
     twice and typing in one appears in the other, because each pane is a viewport
     onto one value rather than a copy of it. */
  const [body, setBody] = useSharedText(`draft:${questionId}`, data?.body ?? "");
  const [published, setPublished] = useState(false);
  const [state, setState] = useState("");
  const [loaded, setLoaded] = useState(false);

  if (data && !loaded) {
    setBody(data.body);
    setPublished(data.published);
    setLoaded(true);
  }

  async function save(publish = published) {
    setState("Saving...");
    try {
      await fetch(`/api/questions/${questionId}/draft`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": document.cookie.match(/melereview_csrf=([^;]+)/)?.[1] ?? "",
        },
        credentials: "include",
        body: JSON.stringify({ body, publish }),
      });
      setState(publish ? "Published." : "Private.");
      reload();
    } catch {
      setState("Could not save.");
    }
  }

  return (
    <div className="solution-pane">
      <header className="solution-pane__head">
        <span className="solution-pane__label">Your solution</span>
        <span className="solution-pane__state">{state || (published ? "public" : "private")}</span>
      </header>

      {loading ? (
        <p className="muted pad">Loading...</p>
      ) : error ? (
        <p className="form-error pad">{error}</p>
      ) : (
        <>
          <div className="solution-pane__editor">
            <EditorMount value={body} onChange={setBody} />
          </div>
          <footer className="solution-pane__foot">
            <label className="switch">
              <input
                type="checkbox"
                checked={published}
                onChange={() => {
                  const next = !published;
                  setPublished(next);
                  void save(next);
                }}
              />
              <span className="switch__track">
                <span className="switch__dot" />
              </span>
              <span className="switch__label">Mark as solution</span>
            </label>
            <button type="button" className="btn btn-sm" onClick={() => save()}>
              Save
            </button>
          </footer>
        </>
      )}
    </div>
  );
}
