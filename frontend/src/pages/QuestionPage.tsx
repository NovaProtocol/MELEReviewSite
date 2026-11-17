import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, invalidate, post, useApi, type Question } from "../api";
import { Prose } from "../Prose";

/* A question is a workspace: the problem on the left, the working on the right.
   The right side is the member's own draft, which is private until they tick
   "mark as solution"; that tick publishes the same text, and un-ticking withdraws
   the publication without touching what they wrote. */

type Draft = {
  body: string;
  published: boolean;
  solution_id: number | null;
  solution_body: string;
};

export function QuestionPage() {
  const { questionId } = useParams();
  const id = Number(questionId);
  const { data, error, loading, reload } = useApi<Question>(`/api/questions/${id}`, [id]);
  const draftState = useApi<Draft>(`/api/questions/${id}/draft`, [id]);

  const [body, setBody] = useState("");
  const [publish, setPublish] = useState(false);
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState("");
  const loaded = useRef(false);

  useEffect(() => {
    if (!draftState.data || loaded.current) return;
    loaded.current = true;
    setBody(draftState.data.body || draftState.data.solution_body || "");
    setPublish(draftState.data.published);
  }, [draftState.data]);

  if (loading) return <p className="muted pad">Loading question...</p>;
  if (error) return <p className="form-error pad">{error}</p>;
  if (!data) return null;

  const solved = Boolean(data.attempt?.solved);

  async function answer(letter: string) {
    if (solved) return;
    try {
      const result = await post<{ is_correct: boolean; attempts: number }>(
        `/api/questions/${id}/attempt`,
        { chosen: letter }
      );
      invalidate("/api/questions/");
      setFeedback(result.is_correct ? "Correct." : "Not this one. Try another choice.");
      reload();
    } catch (problem) {
      setFeedback((problem as Error).message);
    }
  }

  async function save(nextPublish = publish) {
    setSaving(true);
    setStatus("");
    try {
      await api(`/api/questions/${id}/draft`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body, publish: nextPublish }),
      });
      invalidate(`/api/questions/${id}`);
      setStatus(nextPublish ? "Saved and published." : "Saved as your private note.");
      reload();
    } catch (problem) {
      setStatus((problem as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function togglePublish() {
    const next = !publish;
    setPublish(next);
    // The tick is the act, not a form field: saving immediately is what "mark as
    // solution" means, and a switch that needs a second click is a trap.
    if (next) void save(true);
  }

  return (
    <div className="qsplit">
      <section className="qsplit__pane qsplit__pane--problem">
        <header className="qsplit__head">
          <Link to={`/library/${data.topic_id}`} className="crumb-back">
            ← Topic
          </Link>
          <span className="qsplit__id">#{data.id}</span>
          {data.kind && <span className="chip">{data.kind}</span>}
          {solved && <span className="chip chip--ok">answered</span>}
        </header>

        <div className="qsplit__scroll">
          <Prose className="q-prose" html={data.body_html} />

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
                    className={`q__choice${right ? " is-right" : ""}${wrong ? " is-wrong" : ""}`}
                    onClick={() => answer(letter)}
                    disabled={solved}
                  >
                    <span className="q__letter">{letter}</span>
                    <span>{text}</span>
                  </button>
                );
              })}
          </div>

          {feedback && <p className={feedback === "Correct." ? "q__feedback is-ok" : "q__feedback"}>{feedback}</p>}

          {data.note_html && (
            <details className="q__note">
              <summary>Note</summary>
              <Prose html={data.note_html} />
            </details>
          )}

          <div className="q__tags">
            {data.tags.map((tag) => (
              <span className="chip" key={tag}>
                {tag}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section className="qsplit__pane qsplit__pane--work">
        <header className="qsplit__head">
          <span className="qsplit__label">Your working</span>
          <span className="qsplit__hint">
            {publish ? "visible to everyone" : "private to you"}
          </span>
        </header>

        <div className="editor">
          <div className="editor__bar">
            <button type="button" className="editor__tool" onClick={() => setBody((b) => b + "**bold**")}>
              <strong>B</strong>
            </button>
            <button type="button" className="editor__tool" onClick={() => setBody((b) => b + "_italic_")}>
              <em>I</em>
            </button>
            <button type="button" className="editor__tool" onClick={() => setBody((b) => b + "$x^2$")}>
              ƒ
            </button>
            <button type="button" className="editor__tool" onClick={() => setBody((b) => b + "\n```\n\n```")}>
              &lt;/&gt;
            </button>
            <button
              type="button"
              className="editor__tool"
              onClick={() => setBody((b) => b + "\n$$\n\n$$")}
              title="Display formula"
            >
              Σ
            </button>
            <span className="editor__spacer" />
            <button type="button" className="btn btn-sm" onClick={() => save()} disabled={saving}>
              {saving ? "Saving..." : "Save"}
            </button>
          </div>

          <textarea
            className="editor__area"
            value={body}
            onChange={(event) => setBody(event.target.value)}
            placeholder="Work it out here. Markdown, $formulas$ and images all work.

This stays private unless you mark it as a solution."
            spellCheck={false}
          />

          <div className="editor__foot">
            <label className="switch">
              <input type="checkbox" checked={publish} onChange={togglePublish} />
              <span className="switch__track">
                <span className="switch__dot" />
              </span>
              <span className="switch__label">Mark as solution</span>
            </label>
            <span className="editor__status">{status}</span>
          </div>
        </div>
      </section>
    </div>
  );
}

/* The library and topic pages are documents, which is the right shape for
   browsing: a workspace there would be noise. */
