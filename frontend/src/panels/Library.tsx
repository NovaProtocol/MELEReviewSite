import { useState } from "react";
import { useApi, type Subject } from "../api";
import { openPanel } from "../workspaceBus";

/* The library is a panel, not a page: a reader keeps it open beside the question
   they are working on, and clicking a topic adds a problem list next to it rather
   than navigating away from their place. */
export function Library() {
  const { data, error, loading } = useApi<Subject[]>("/api/subjects");
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState<Record<number, boolean>>({});

  if (loading) return <p className="muted pad">Loading the library...</p>;
  if (error) return <p className="form-error pad">{error}</p>;
  if (!data) return null;

  const needle = filter.trim().toLowerCase();

  return (
    <div className="lib">
      <input
        className="lib__search"
        placeholder="Filter subjects and topics"
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
        aria-label="Filter"
      />

      {data.map((subject) => {
        const topics = subject.topics.filter(
          (topic) => !needle || topic.name.toLowerCase().includes(needle)
        );
        if (!topics.length && needle) return null;
        const expanded = open[subject.id] ?? Boolean(needle);
        return (
          <section className="lib__subject" key={subject.id}>
            <button
              className="lib__head"
              onClick={() => setOpen((current) => ({ ...current, [subject.id]: !expanded }))}
              aria-expanded={expanded}
            >
              <span className={`lib__caret${expanded ? " is-open" : ""}`}>▸</span>
              {subject.name}
              <span className="lib__count">{subject.topics.length}</span>
            </button>
            {expanded && (
              <ul className="lib__topics">
                {topics.map((topic) => (
                  <li key={topic.id}>
                    <button
                      className="lib__topic"
                      onClick={() =>
                        openPanel({
                          kind: "problems",
                          title: topic.name,
                          params: { topicId: String(topic.id) },
                        })
                      }
                    >
                      <span>{topic.name}</span>
                      <span className="lib__count" title="Questions, answered">
                        {topic.questions}
                        {topic.answers ? ` · ${topic.answers}` : ""}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
