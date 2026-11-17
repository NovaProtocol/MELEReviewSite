import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "../api";
import { Prose } from "../Prose";

/* Search, the profile, and the sign-in screen. Sign-in is part of the client too:
   one app, one header, one theme, no second document with its own stylesheet. */

export function SearchPage() {
  const [query, setQuery] = useState("");
  const trimmed = query.trim();
  const { data, loading } = useApi<{ results: { id: number; topic_id: number; body_html: string }[] }>(
    trimmed.length >= 2 ? `/api/search?q=${encodeURIComponent(trimmed)}` : null,
    [trimmed]
  );

  return (
    <div className="doc">
      <h1 className="doc__title">Search</h1>
      <input
        className="searchbig"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="pressure, carnot, beam deflection..."
        aria-label="Search"
        autoFocus
      />

      {loading && <p className="muted">Searching...</p>}
      {trimmed.length >= 2 && !loading && (data?.results ?? []).length === 0 && (
        <p className="muted">Nothing matched.</p>
      )}

      <ul className="doc__problems" style={{ marginTop: "1rem" }}>
        {(data?.results ?? []).map((result) => (
          <li key={result.id}>
            <Link className="doc__problem" to={`/problem-sets/${result.topic_id}/${result.id}`}>
              <div className="doc__problem-meta">
                <span className="plist__id">#{result.id}</span>
              </div>
              <Prose className="doc__problem-body" html={result.body_html} />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

type Me = {
  username: string;
  email: string;
  bio: string | null;
  permissions: number;
  is_system_admin: boolean;
  progress?: {
    answered?: number;
    solved?: number;
    accuracy?: number | null;
    by_subject?: { subject: string; answered: number; solved: number }[];
  };
};

export function ProfilePage() {
  const { data, error, loading } = useApi<Me>("/api/auth/me");

  if (loading) return <p className="muted pad">Loading...</p>;
  if (error) return <p className="form-error pad">{error}</p>;
  if (!data) return null;

  const progress = data.progress;

  return (
    <div className="doc">
      <h1 className="doc__title">{data.username}</h1>
      <p className="muted">{data.email}</p>
      {data.bio && <Prose html={data.bio} />}

      <div className="stats">
        <div className="stat">
          <span className="stat__value">{progress?.answered ?? 0}</span>
          <span className="stat__label">Answered</span>
        </div>
        <div className="stat">
          <span className="stat__value">{progress?.solved ?? 0}</span>
          <span className="stat__label">Solved</span>
        </div>
        <div className="stat">
          <span className="stat__value">
            {progress?.accuracy == null ? "—" : `${Math.round(progress.accuracy * 100)}%`}
          </span>
          <span className="stat__label">First-try accuracy</span>
        </div>
      </div>

      <h2 className="doc__heading">By subject</h2>
      <ul className="breadown">
        {(progress?.by_subject ?? []).map((row) => (
          <li key={row.subject}>
            <span>{row.subject}</span>
            <span className="muted">
              {row.solved} solved of {row.answered}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function MemberPage() {
  const { username } = useParams();
  const { data, error, loading } = useApi<Me>(`/api/users/${encodeURIComponent(username ?? "")}`);

  if (loading) return <p className="muted pad">Loading...</p>;
  if (error) return <p className="form-error pad">{error}</p>;
  if (!data) return null;

  return (
    <div className="doc">
      <h1 className="doc__title">{data.username}</h1>
      {data.bio && <Prose html={data.bio} />}
    </div>
  );
}
