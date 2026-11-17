import { useState } from "react";
import { useApi, type Question } from "../api";
import { Prose } from "../Prose";
import { openPanel } from "../workspaceBus";

/* The problem set for one topic. Each card opens the question in its own panel,
   so answering one does not close the list you were working through. */

const SORTS = [
  { value: "newest", label: "Newest" },
  { value: "oldest", label: "Oldest" },
  { value: "score", label: "Score" },
  { value: "answered", label: "Most answered" },
  { value: "unsolved", label: "Least solved" },
];

export function Problems({ topicId, topicName }: { topicId: number; topicName?: string }) {
  const [sort, setSort] = useState("newest");
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("");

  const query = new URLSearchParams({ sort });
  if (search.trim()) query.set("search", search.trim());
  if (kind) query.set("kind", kind);
  const { data, error, loading } = useApi<Question[]>(
    `/api/topics/${topicId}/questions?${query}`,
    [sort, search, kind]
  );

  return (
    <div className="problems">
      <div className="problems__bar">
        <input
          className="problems__search"
          placeholder="Search this topic"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          aria-label="Search questions"
        />
        <select value={sort} onChange={(event) => setSort(event.target.value)} aria-label="Sort">
          {SORTS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <select value={kind} onChange={(event) => setKind(event.target.value)} aria-label="Kind">
          <option value="">Any kind</option>
          <option value="identification">Identification</option>
          <option value="computation">Computation</option>
        </select>
      </div>

      {loading && <p className="muted pad">Loading...</p>}
      {error && <p className="form-error pad">{error}</p>}

      <ul className="problems__list">
        {(data ?? []).map((question) => {
          const answered = Boolean(question.attempt?.solved);
          return (
            <li key={question.id}>
              <button
                className="problems__card"
                onClick={() =>
                  openPanel({
                    kind: "question",
                    title: `#${question.id}`,
                    params: { questionId: String(question.id), topicName: topicName ?? "" },
                  })
                }
              >
                <span className="problems__meta">
                  <span className="problems__id">#{question.id}</span>
                  {question.kind && <span className="chip">{question.kind}</span>}
                  {answered && <span className="chip chip--ok">answered</span>}
                </span>
                <Prose className="problems__body" html={question.body_html} />
              </button>
            </li>
          );
        })}
      </ul>

      {!loading && !error && (data ?? []).length === 0 && (
        <p className="muted pad">Nothing matches those filters.</p>
      )}
    </div>
  );
}
