import { useState } from "react";
import { invalidate, post, useApi, type Question } from "../api";
import { Prose } from "../Prose";

/* One question, with its choices, in its own panel. Answering writes through the
   same endpoint the classic page uses, so both stay in step. */

export function QuestionPanel({ questionId }: { questionId: number }) {
  const { data, error, loading, reload } = useApi<Question>(`/api/questions/${questionId}`);
  const [busy, setBusy] = useState("");
  const [feedback, setFeedback] = useState("");

  if (loading) return <p className="muted pad">Loading question...</p>;
  if (error) return <p className="form-error pad">{error}</p>;
  if (!data) return null;

  const solved = Boolean(data.attempt?.solved);

  async function answer(letter: string) {
    if (busy || solved) return;
    setBusy(letter);
    setFeedback("");
    try {
      const result = await post<{ is_correct: boolean; attempts: number }>(
        `/api/questions/${questionId}/attempt`,
        { chosen: letter }
      );
      invalidate("/api/questions/");
      invalidate("/api/topics/");
      setFeedback(
        result.is_correct
          ? `Correct on try ${result.attempts}.`
          : "Not this one. Try another choice."
      );
      reload();
    } catch (problem) {
      setFeedback((problem as Error).message);
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="q">
      <Prose className="q__prose" html={data.body_html} />

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
                disabled={solved || Boolean(busy)}
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

      {Boolean(data.solution_count) && (
        <p className="muted">
          {data.solution_count} solution{data.solution_count === 1 ? "" : "s"}
          {data.may_see_solutions ? "" : " · unlocks on a correct answer"}
        </p>
      )}
    </div>
  );
}
