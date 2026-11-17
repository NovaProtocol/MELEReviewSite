import { useEffect, useState } from "react";

/* One fetch helper for the whole client. The API is the contract: the same
   endpoints serve the Jinja pages, so anything this panel can do, a script can. */

export type Subject = {
  id: number;
  name: string;
  topics: { id: number; name: string; questions: number; answers: number; newest: string | null }[];
};

export type Question = {
  id: number;
  topic_id: number;
  body_html: string;
  note_html?: string;
  choices: Record<string, string | null>;
  kind: string;
  tags: string[];
  struck: string;
  answer_count?: number;
  solution_count?: number;
  score?: number;
  attempt?: { chosen: string; is_correct: boolean; solved: boolean } | null;
  may_see_solutions?: boolean;
  solutions?: unknown[];
};

function csrf(): string {
  const match = document.cookie.match(/(?:^|;\s*)melereview_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (method !== "GET") headers.set("X-CSRF-Token", csrf());
  const response = await fetch(path, { ...init, headers, credentials: "include" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      (body as { error?: { message?: string } }).error?.message ??
      (body as { detail?: string }).detail ??
      `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return body as T;
}

export async function post<T>(path: string, payload: unknown): Promise<T> {
  return api<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

/* A small cache: two panels showing the same topic must not double every request.
   Entries are dropped when anything writes, which is cheap and always correct. */
const cache = new Map<string, unknown>();

export function invalidate(prefix = "") {
  for (const key of [...cache.keys()]) if (key.startsWith(prefix)) cache.delete(key);
}

export function useApi<T>(path: string | null, deps: unknown[] = []): {
  data: T | null;
  error: string;
  loading: boolean;
  reload: () => void;
} {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(Boolean(path));
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!path) {
      setData(null);
      setLoading(false);
      return;
    }
    const cached = cache.get(path);
    if (cached !== undefined) {
      setData(cached as T);
      setLoading(false);
      return;
    }
    let live = true;
    setLoading(true);
    api<T>(path)
      .then((value) => {
        cache.set(path, value);
        if (live) {
          setData(value);
          setError("");
        }
      })
      .catch((problem: Error) => live && setError(problem.message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, nonce, ...deps]);

  return { data, error, loading, reload: () => setNonce((n) => n + 1) };
}
