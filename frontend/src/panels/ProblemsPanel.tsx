import { useEffect, useRef, useState } from "react";
import { useSharedText } from "../workspace/sharedDoc";
import { EditorMount } from "../workspace/EditorMount";
import { registerSolution } from "../workspace/solutionBus";
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
  const shell = useRef<HTMLDivElement | null>(null);

  /* No measurement decides the layout.

     The previous version read the panel's width in JS and fell back to the *saved*
     pixel width while the measurement was still 0 — which is one frame, but a frame
     in which a wide saved width took the whole panel and the problem rendered at
     zero. Whether the split fits is a question CSS can answer exactly, at every
     size, without a first frame that guesses. */
  const columns = `minmax(0, 1fr) 5px min(${width}px, 45%)`;

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
      style={{ gridTemplateColumns: columns }}
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

      <div
        className="qpanel__resize"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize the solution"
        onPointerDown={startResize}
      />

      <section className="qpanel__solution">
        <SolutionPane
          questionId={questionId}
          canPublish={Boolean(data.attempt?.solved)}
        />
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

  /* Nothing is shown before the answer is right, not even a count. A count would
     still tell a reader that somebody else found it, and the whole point of the
     gate is that they work it out first. */
  const solved = Boolean(data.attempt?.solved);
  const moderator = data.may_see_solutions && !solved;

  if (!solved) {
    return (
      <section className="solutions solutions--locked">
        <h3 className="solutions__head">
          <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
            <rect x="5" y="11" width="14" height="9" rx="2" fill="none" stroke="currentColor" strokeWidth="1.8" />
            <path d="M8 11V8a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" strokeWidth="1.8" />
          </svg>
          Solutions
        </h3>
        <p className="muted">
          Hidden for now. Answer the question first to see how other people solved it.
          {moderator && " You can read them as a moderator once you have answered."}
        </p>
      </section>
    );
  }

  return (
    <section className="solutions">
      <h3 className="solutions__head">
        Solutions <span className="solutions__count">{solutions.length}</span>
      </h3>

      {solutions.length === 0 && (
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

function SolutionPane({
  questionId,
  canPublish,
}: {
  questionId: number;
  canPublish: boolean;
}) {
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

  /* Saving is automatic, and the state line is the only report.

     A Save button beside an editor that looks live is a trap: the text is on screen
     and in the shared document, so it reads as saved. It now saves shortly after
     typing stops, and the line says "Saved" when it lands. The switch publishes, so
     it still saves immediately — that click is a claim about the answer, not an
     edit. */
  const [dirty, setDirty] = useState(false);
  const timer = useRef<number | null>(null);

  if (data && !loaded) {
    setBody(data.body);
    setPublished(data.published);
    setLoaded(true);
  }

  async function save(publish = published) {
    setState("Saving...");
    try {
      const response = await fetch(`/api/questions/${questionId}/draft`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": document.cookie.match(/melereview_csrf=([^;]+)/)?.[1] ?? "",
        },
        credentials: "include",
        body: JSON.stringify({ body, publish }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload?.error?.message ?? "Could not save");
      }
      setState(publish ? "Published" : "Saved");
      setDirty(false);
      reload();
    } catch (problem) {
      setState((problem as Error).message);
    }
  }

  /* A tool's result arrives as markdown and is appended to the working: the reader
     put the numbers in somewhere, and retyping the LaTeX by hand is the part they
     were trying to skip. */
  useEffect(
    () =>
      registerSolution((markdown) => {
        setBody(body.trim() ? `${body.trim()}\n\n${markdown}` : markdown);
        setDirty(true);
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [body]
  );

  // Typing marks the draft dirty; a short pause saves it.
  useEffect(() => {
    if (!dirty) return;
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void save(), 900);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [body, dirty]);

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
            <EditorMount
              value={body}
              onChange={(markdown) => {
                setBody(markdown);
                setDirty(true);
              }}
            />
          </div>
          <footer className="solution-pane__foot">
            {/* Writing is always allowed; publishing is earned. A note is private
                working and a solution is a claim about the answer, so the switch
                waits for the answer to be right. */}
            <label
              className={`switch${canPublish ? "" : " is-locked"}`}
              title={
                canPublish
                  ? "Publish this as your solution"
                  : "Answer the question correctly to publish a solution"
              }
            >
              <input
                type="checkbox"
                checked={published}
                disabled={!canPublish}
                onChange={() => {
                  if (!canPublish) return;
                  const next = !published;
                  setPublished(next);
                  void save(next);
                }}
              />
              <span className="switch__track">
                <span className="switch__dot" />
              </span>
              <span className="switch__label">
                {canPublish ? "Mark as solution" : "Answer it first"}
              </span>
            </label>
            <span className="solution-pane__saved muted">
              {state === "Saving..." ? "Saving..." : dirty ? "Unsaved" : ""}
            </span>
          </footer>
        </>
      )}
    </div>
  );
}
