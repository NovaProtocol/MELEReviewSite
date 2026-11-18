import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { invalidate, post, useApi, type Question, type Subject } from "../api";
import { Prose } from "../Prose";
import { Icon } from "../Chrome";

/* A problem set is a file explorer, and the problem is a tab.

   Opening a topic from the tree opens a tab; opening a problem opens another tab
   with the question and its notes side by side. That is the shape of an editor,
   because working through forty problems is the same job as reading forty files.

   Tabs are keyed by address, so a reload lands on the same problem, and closing a
   tab walks back to whatever is left. */

type Tab =
  | { kind: "problems"; topicId: number; title: string }
  | { kind: "question"; topicId: number; questionId: number; title: string };

const MAX_TABS = 12;

export function ProblemSetsPage() {
  const { topicId } = useParams();
  const navigate = useNavigate();
  const subjects = useApi<Subject[]>("/api/subjects");
  const [open, setOpen] = useState<Record<number, boolean>>({});
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [active, setActive] = useState<string>("");

  const key = (tab: Tab) =>
    tab.kind === "problems" ? `t:${tab.topicId}` : `q:${tab.questionId}`;

  const topicName = useCallback(
    (id: number) =>
      (subjects.data ?? [])
        .flatMap((subject) => subject.topics)
        .find((topic) => topic.id === id)?.name ?? "",
    [subjects.data]
  );

  /* The address decides the active tab: /problem-sets/1 opens the topic's list,
     /problem-sets/1/7 opens that question beside it. */
  useEffect(() => {
    if (!topicId) return;
    const id = Number(topicId);
    const title = topicName(id) || `Topic ${id}`;
    const tab: Tab = { kind: "problems", topicId: id, title };

    setTabs((current) => {
      // A topic browser is mutually exclusive: opening another one closes the one
      // already open, because two lists of problems side by side answer nothing.
      const withoutOtherBrowsers = current.filter(
        (item) => !(item.kind === "problems" && item.topicId !== id)
      );
      if (withoutOtherBrowsers.some((item) => key(item) === key(tab))) {
        return withoutOtherBrowsers.map((item) =>
          key(item) === key(tab) ? { ...item, title } : item
        );
      }
      return [...withoutOtherBrowsers, tab].slice(-MAX_TABS);
    });
    setActive(key(tab));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicId, topicName]);

  function openTopic(id: number) {
    navigate(`/problem-sets/${id}`);
  }

  function openQuestion(topicIdValue: number, questionId: number) {
    const tab: Tab = {
      kind: "question",
      topicId: topicIdValue,
      questionId,
      title: `#${questionId}`,
    };
    setTabs((current) =>
      current.some((item) => key(item) === key(tab)) ? current : [...current, tab].slice(-MAX_TABS)
    );
    setActive(key(tab));
    window.history.replaceState(null, "", `/problem-sets/${topicIdValue}/${questionId}`);
  }

  function closeTab(tab: Tab) {
    setTabs((current) => {
      const remaining = current.filter((item) => key(item) !== key(tab));
      if (active === key(tab)) {
        const next = remaining[remaining.length - 1];
        if (next) {
          setActive(key(next));
          window.history.replaceState(
            null,
            "",
            next.kind === "problems"
              ? `/problem-sets/${next.topicId}`
              : `/problem-sets/${next.topicId}/${next.questionId}`
          );
        } else {
          setActive("");
          window.history.replaceState(null, "", "/problem-sets");
        }
      }
      return remaining;
    });
  }

  /* `active` is the tab the address points at. When a tab is added by a click the
     address is updated in the same act, so the two cannot disagree. */
  const activeTab = tabs.find((tab) => key(tab) === active) ?? tabs[tabs.length - 1];

  /* The solution pane is resizable: reading a long problem wants a wide problem,
     and a derivation wants a wide solution. The width is remembered per browser. */
  const [solutionWidth, setSolutionWidth] = useState(() => {
    const saved = Number(localStorage.getItem("mele.solution-width"));
    return Number.isFinite(saved) && saved > 240 ? saved : 360;
  });

  const startResize = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const move = (moveEvent: PointerEvent) => {
      const next = Math.min(
        Math.max(window.innerWidth - moveEvent.clientX, 240),
        Math.round(window.innerWidth * 0.7)
      );
      setSolutionWidth(next);
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      localStorage.setItem("mele.solution-width", String(solutionWidth));
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  };

  return (
    <div className="explorer">
      <aside className="tree" aria-label="Problem sets">
        <header className="tree__head">Problem sets</header>
        <div className="tree__body">
          {(subjects.data ?? []).map((subject) => {
            // Closed on first view: the tree is a map, not a wall of topics.
            const expanded = open[-subject.id] ?? false;
            return (
              <div className="tree__group" key={subject.id}>
                <button
                  type="button"
                  className="tree__folder"
                  onClick={() => setOpen((current) => ({ ...current, [-subject.id]: !expanded }))}
                  aria-expanded={expanded}
                >
                  <span className={`tree__caret${expanded ? " is-open" : ""}`}>▸</span>
                  {subject.name}
                </button>
                {expanded && (
                  <ul className="tree__files">
                    {subject.topics.map((topic) => (
                      <li key={topic.id}>
                        <button
                          type="button"
                          className={`tree__file${active === `t:${topic.id}` ? " is-active" : ""}`}
                          onClick={() => openTopic(topic.id)}
                        >
                          <span className="tree__name">{topic.name}</span>
                          <span className="tree__count">{topic.questions}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      </aside>

      <section className="tabsarea">
        <div className="tabstrip">
          {tabs.map((tab) => (
            <div
              key={key(tab)}
              className={`tab${active === key(tab) ? " is-active" : ""}`}
              role="tab"
              aria-selected={active === key(tab)}
            >
              <button type="button" className="tab__label" onClick={() => setActive(key(tab))}>
                {tab.title}
              </button>
              <button
                type="button"
                className="tab__close"
                aria-label={`Close ${tab.title}`}
                onClick={() => closeTab(tab)}
              >
                ×
              </button>
            </div>
          ))}
        </div>

        <div className="tabbody">
          {!activeTab && <Nothing />}
          {activeTab?.kind === "problems" && (
            <TopicProblems topicId={activeTab.topicId} onOpen={openQuestion} />
          )}
          {activeTab?.kind === "question" && (
            <QuestionWorkspace
              topicId={activeTab.topicId}
              questionId={activeTab.questionId}
              solutionWidth={solutionWidth}
              onResize={startResize}
            />
          )}
        </div>
      </section>
    </div>
  );
}

function Nothing() {
  return (
    <div className="nothing">
      <p>Open a topic on the left.</p>
      <p className="muted">Each topic opens a tab; each problem opens its own.</p>
    </div>
  );
}

function TopicProblems({
  topicId,
  onOpen,
}: {
  topicId: number;
  onOpen: (topicId: number, questionId: number) => void;
}) {
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
            <button type="button" className="plist__card" onClick={() => onOpen(topicId, question.id)}>
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
    </div>
  );
}

/* A problem, with its notes beside it. The notes belong to this entry: they are
   not a separate thing you can open on its own, because working is not separable
   from the problem being worked. */
function QuestionWorkspace({
  topicId,
  questionId,
  solutionWidth,
  onResize,
}: {
  topicId: number;
  questionId: number;
  solutionWidth: number;
  onResize: (event: React.PointerEvent<HTMLDivElement>) => void;
}) {
  const navigate = useNavigate();
  const { data, loading, error, reload } = useApi<Question>(
    `/api/questions/${questionId}`,
    [questionId]
  );

  return (
    <div
      className="qwork"
      style={{
        // Problem, the grab handle, then the solution: three children, three tracks.
        gridTemplateColumns: `minmax(0, 1fr) 5px ${solutionWidth}px`,
      }}
    >
      <section className="qwork__problem">
        <header className="qwork__head">
          <button type="button" className="link" onClick={() => navigate(`/resource/${topicId}`)}>
            <Icon name="library" size={13} /> notes
          </button>
          <span className="plist__id">#{questionId}</span>
          {data?.kind && <span className="chip">{data.kind}</span>}
          {data?.attempt?.solved && <span className="chip chip--ok">answered</span>}
        </header>

        {loading && <p className="muted pad">Loading...</p>}
        {error && <p className="form-error pad">{error}</p>}

        {data && (
          <div className="qwork__scroll">
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
        )}
      </section>

      <div
        className="qwork__resize"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize the solution"
        onPointerDown={onResize}
      />

      <section className="qwork__notes">
        <NotesPanel questionId={questionId} />
      </section>
    </div>
  );
}

/* Answering, on the question you deliberately opened.

   The browser tab shows choices without letting you answer them, because a card
   in a list is for reading. A question in its own tab is for working, and a
   choice that does nothing is a broken site. */
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

/* Other people's working. This is the point of the site, and it was missing. */
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

/* The notes pane, which only exists while a problem is open. */
function NotesPanel({ questionId }: { questionId: number }) {
  const { data, error, loading, reload } = useApi<{
    body: string;
    published: boolean;
  }>(`/api/questions/${questionId}/draft`, [questionId]);
  const [body, setBody] = useState("");
  const [published, setPublished] = useState(false);
  const [state, setState] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!data || loaded) return;
    setBody(data.body);
    setPublished(data.published);
    setLoaded(true);
  }, [data, loaded]);

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
    <div className="notes">
      <header className="notes__head">
        <span className="notes__label">Your solution</span>
        <span className="notes__state">{state || (published ? "public" : "private")}</span>
      </header>

      {loading ? (
        <p className="muted pad">Loading...</p>
      ) : error ? (
        <p className="form-error pad">{error}</p>
      ) : (
        <>
          <textarea
            className="notes__area"
            value={body}
            onChange={(event) => setBody(event.target.value)}
            placeholder="Work it out here. Markdown, $formulas$ and images all work."
            spellCheck={false}
          />
          <footer className="notes__foot">
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
