/* The workspace's layout store.

   The arrangement is the member's, so it survives a reload, another tab, and a trip
   to a page outside the workspace. Server state (answers, solutions) lives on the
   server; this is only what is where. */

import type { DockviewApi } from "dockview";

const KEY = "mele.workspace.v3";

export type SavedTab = {
  id: string;
  kind: string;
  title: string;
  params: Record<string, string>;
};

export type SavedLayout = {
  version: 3;
  layout: unknown;
  active: string | null;
};

export function readLayout(): SavedLayout | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SavedLayout;
    if (parsed?.version !== 3 || !parsed.layout) return null;
    return parsed;
  } catch {
    localStorage.removeItem(KEY);
    return null;
  }
}

export function writeLayout(api: DockviewApi, active: string | null) {
  try {
    const payload: SavedLayout = {
      version: 3,
      layout: api.toJSON(),
      active,
    };
    localStorage.setItem(KEY, JSON.stringify(payload));
  } catch {
    /* a full quota must not break the drag that filled it */
  }
}

export function clearLayout() {
  localStorage.removeItem(KEY);
}
