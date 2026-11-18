/* Where the arrangement lives.

   Two copies, one truth: the browser's, for the first paint, and the member's on
   the server, so it follows them to another machine. They are merged by timestamp
   and nothing else; the newer edit wins, and the loser adopts the winner rather
   than being overwritten mid-session. */

import type { DockviewApi } from "dockview";

const KEY = "mele.workspace.v4";

export type SavedLayout = { version: 4; layout: unknown; saved_at: number };

export function readLocal(): SavedLayout | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SavedLayout;
    if (parsed?.version !== 4 || !parsed.layout) return null;
    return parsed;
  } catch {
    localStorage.removeItem(KEY);
    return null;
  }
}

export function writeLocal(api: DockviewApi): number {
  const saved_at = Date.now();
  try {
    localStorage.setItem(
      KEY,
      JSON.stringify({ version: 4, layout: api.toJSON(), saved_at } satisfies SavedLayout)
    );
  } catch {
    /* a full quota must not break the drag that filled it */
  }
  return saved_at;
}

export function clearLocal() {
  localStorage.removeItem(KEY);
}

/* The server copy, with the merge rule. Returns the winner so the caller can adopt
   it when the server turns out to be newer than this browser. */
export async function syncWithServer(
  local: SavedLayout | null,
  layout: unknown | null
): Promise<SavedLayout | null> {
  const csrf = document.cookie.match(/melereview_csrf=([^;]+)/)?.[1] ?? "";

  try {
    const remote = await fetch("/api/workspace/layout", {
      headers: { Accept: "application/json" },
      credentials: "include",
    }).then((response) => response.json() as Promise<{ layout: string | null; saved_at: number }>);

    const localStamp = local?.saved_at ?? 0;
    const remoteStamp = remote.saved_at ?? 0;

    if (remote.layout && remoteStamp > localStamp) {
      // The server was edited more recently: adopt it.
      return { version: 4, layout: JSON.parse(remote.layout), saved_at: remoteStamp };
    }

    if (layout && localStamp > remoteStamp) {
      await fetch("/api/workspace/layout", {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        credentials: "include",
        body: JSON.stringify({ layout: JSON.stringify(layout), saved_at: localStamp }),
      });
    }
  } catch {
    /* offline: the local copy stands, and the next save catches up */
  }
  return null;
}

export async function upload(api: DockviewApi, savedAt: number) {
  const csrf = document.cookie.match(/melereview_csrf=([^;]+)/)?.[1] ?? "";
  try {
    await fetch("/api/workspace/layout", {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      credentials: "include",
      body: JSON.stringify({ layout: JSON.stringify(api.toJSON()), saved_at: savedAt }),
    });
  } catch {
    /* the browser still has it */
  }
}
