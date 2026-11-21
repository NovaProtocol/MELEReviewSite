import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { invalidate, post, put, useApi, type Question, type Subject } from "../api";
import { EditorMount } from "../workspace/EditorMount";

/* Writing a question, and editing one.

   This was a server-rendered form. It is the same form: the same fields, the same
   editor (mounted, not rebuilt), the same tags. What changed is who draws it. */

const LETTERS = ["A", "B", "C", "D"] as const;

/* The editor takes its subject from props, not from the address.

   It has to work in two places: as a panel in the workspace, where there is no URL to
   read, and on its own route, which passes the same values in. */
export type QuestionEditorProps = {
  questionId?: number;
  /** Where to go when cancelled, saved, or closed. Defaults to the workspace. */
  onDone?: (topicId?: number, questionId?: number) => void;
};

export function QuestionEditor({ questionId, onDone }: QuestionEditorProps) {
  const navigate = useNavigate();
  const editing = questionId !== undefined;

  const finish = (topic?: number, question?: number) => {
    if (onDone) onDone(topic, question);
    else navigate(topic ? `/app?panel=problems&topicId=${topic}` : "/app?panel=problems");
  };

  const subjects = useApi<Subject[]>("/api/subjects");
  const existing = useApi<Question>(editing ? `/api/questions/${questionId}` : null);

  const [topicId, setTopicId] = useState("");
  const [body, setBody] = useState("");
  const [kind, setKind] = useState<"identification" | "computation">("identification");
  const [choices, setChoices] = useState<Record<string, string>>({
    a: "",
    b: "",
    c: "",
    d: "",
    e: "",
  });
  const [correct, setCorrect] = useState("A");
  const [note, setNote] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [tagText, setTagText] = useState("");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  /* The server's copy fills the form once. After that the reader owns it: refilling on
     every refetch would overwrite what they had typed. */
  useEffect(() => {
    const data = existing.data;
    if (!data || loaded) return;
    setTopicId(String(data.topic_id));
    setBody(data.body ?? "");
    setKind((data.kind as "identification" | "computation") ?? "identification");
    const next: Record<string, string> = { a: "", b: "", c: "", d: "", e: "" };
    for (const letter of ["a", "b", "c", "d", "e"]) {
      const value = (data.choices ?? {})[letter];
      if (value) next[letter] = value;
    }
    setChoices(next);
    setCorrect(data.correct_choice ?? "A");
    setNote(data.explanation ?? "");
    setTags(data.tags ?? []);
    setLoaded(true);
  }, [existing.data, loaded]);

  function addTag() {
    const value = tagText.trim().toLowerCase();
    if (!value || tags.includes(value)) {
      setTagText("");
      return;
    }
    setTags([...tags, value]);
    setTagText("");
  }

  async function save() {
    setProblem("");
    if (!topicId) {
      setProblem("Choose a topic.");
      return;
    }
    if (!body.trim()) {
      setProblem("The question needs some text.");
      return;
    }
    for (const letter of LETTERS) {
      if (!choices[letter].trim()) {
        setProblem(`Choice ${letter.toUpperCase()} is required.`);
        return;
      }
    }
    setBusy(true);
    try {
      const payload = {
        topic_id: Number(topicId),
        body,
        kind,
        choices,
        correct_choice: correct,
        explanation: note,
        tags,
      };
      if (editing) await put(`/api/questions/${questionId}`, payload);
      else await post("/api/questions", payload);
      invalidate("/api/questions/");
      invalidate("/api/topics/");
      finish(Number(topicId), editing ? questionId : undefined);
    } catch (error) {
      setProblem((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (editing && existing.loading) return <p className="muted pad">Loading...</p>;
  if (editing && existing.error) return <p className="form-error pad">{existing.error}</p>;

  /* Editing somebody else's question is refused before the form is drawn. The server
     refuses the save too; saying so here means the reader does not write a paragraph
     and then lose it. */
  if (editing && existing.data?.may_edit === false) {
    return (
      <div className="doc editorial">
        <p className="form-error">This is not your question, so it cannot be edited.</p>
        <button type="button" className="btn" onClick={() => navigate(-1)}>
          Back
        </button>
      </div>
    );
  }

  return (
    <div className="doc editorpage">
      <header className="doc__head">
        <div>
          <p className="eyebrow">{editing ? "Edit" : "New"}</p>
          <h1>{editing ? "Edit question" : "Add a question"}</h1>
        </div>
        <button
          type="button"
          className="btn btn--quiet"
          onClick={() => finish(topicId ? Number(topicId) : undefined)}
        >
          Cancel
        </button>
      </header>

      <label className="field">
        <span>Topic</span>
        <select value={topicId} onChange={(event) => setTopicId(event.target.value)}>
          <option value="">Choose a topic</option>
          {(subjects.data ?? []).map((subject) => (
            <optgroup key={subject.id} label={subject.name}>
              {subject.topics.map((topic) => (
                <option key={topic.id} value={topic.id}>
                  {topic.name}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>

      <div className="field">
        <span>Question</span>
        <EditorMount editorKey="question-body" value={body} onChange={setBody} />
      </div>

      <div className="field">
        <span>Kind of question</span>
        <div className="chips">
          {(["identification", "computation"] as const).map((option) => (
            <button
              key={option}
              type="button"
              className={`chip${kind === option ? " is-on" : ""}`}
              onClick={() => setKind(option)}
            >
              {option}
            </button>
          ))}
        </div>
        <span className="muted field-note">Computations can be left out of quizzes.</span>
      </div>

      {(["A", "B", "C", "D", "E"] as const).map((letter) => {
        const key = letter.toLowerCase();
        return (
          <label key={letter} className="field">
            <span>
              Choice {letter}
              {letter === "E" && <span className="muted"> (optional)</span>}
            </span>
            <input
              value={choices[key]}
              onChange={(event) => setChoices({ ...choices, [key]: event.target.value })}
            />
          </label>
        );
      })}

      <label className="field">
        <span>Correct choice</span>
        <select value={correct} onChange={(event) => setCorrect(event.target.value)}>
          {["A", "B", "C", "D", "E"].map((letter) => (
            <option key={letter} value={letter}>
              {letter}
            </option>
          ))}
        </select>
      </label>

      <div className="field">
        <span>Note (optional)</span>
        <EditorMount editorKey="question-note" value={note} onChange={setNote} />
      </div>

      <div className="field">
        <span>Tags</span>
        <div className="chips">
          {tags.map((tag) => (
            <button
              key={tag}
              type="button"
              className="chip is-on"
              title="Remove this tag"
              onClick={() => setTags(tags.filter((item) => item !== tag))}
            >
              {tag} ×
            </button>
          ))}
        </div>
        <input
          value={tagText}
          placeholder="add a tag and press Enter"
          onChange={(event) => setTagText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addTag();
            }
          }}
        />
      </div>

      {problem && <p className="form-error">{problem}</p>}

      <div className="doc__actions">
        <button type="button" className="btn btn--primary" onClick={save} disabled={busy}>
          {busy ? "Saving..." : editing ? "Save changes" : "Add question"}
        </button>
      </div>
    </div>
  );
}

/* Editing one of a topic's two resource sheets.

   The sheet is long — some run to tens of thousands of characters — so the editor is
   mounted at full height and the page scrolls as a document. Saving is explicit here
   because a resource is not a draft: an accidental half-edit should not publish. */
export type ResourceEditorProps = { topicId: number; kind: string };

export function ResourceEditor({ topicId, kind }: ResourceEditorProps) {
  const navigate = useNavigate();
  const path = `/api/topics/${topicId}/pages/${kind}`;
  const existing = useApi<{ body: string }>(path);
  const [body, setBody] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [problem, setProblem] = useState("");
  const [state, setState] = useState("");

  useEffect(() => {
    if (!existing.data || loaded) return;
    setBody(existing.data.body ?? "");
    setLoaded(true);
  }, [existing.data, loaded]);

  async function save() {
    setProblem("");
    setState("Saving...");
    try {
      await put(path, { body });
      invalidate(`/api/topics/${topicId}`);
      setState("Saved");
    } catch (error) {
      setProblem((error as Error).message);
      setState("");
    }
  }

  return (
    <div className="doc editorpage">
      <header className="doc__head">
        <div>
          <p className="eyebrow">Topic {topicId}</p>
          <h1>Edit {kind}</h1>
        </div>
        <div className="doc__actions">
          <span className="muted">{state}</span>
          <button type="button" className="btn btn--quiet" onClick={() => navigate(-1)}>
            Back
          </button>
          <button type="button" className="btn btn--primary" onClick={save}>
            Save
          </button>
        </div>
      </header>

      {existing.loading && <p className="muted pad">Loading...</p>}
      {existing.error && <p className="form-error pad">{existing.error}</p>}
      {problem && <p className="form-error">{problem}</p>}

      {!existing.loading && !existing.error && (
        <div className="editorpage__editor">
          <EditorMount editorKey={`page-${kind}`} value={body} onChange={setBody} />
        </div>
      )}
    </div>
  );
}
