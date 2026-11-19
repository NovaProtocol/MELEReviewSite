/* The map and the tools have a width, and opening a panel does not change it.

   What is enforced is a *constraint*, not a size: a minimum and a maximum equal to
   the remembered width. Constraints are the one thing dockview's grid honours for a
   track it shares, and they are safe to re-apply — setting a size instead fires a
   layout change that re-enters this function, which locked the page.

   A drag is the only thing allowed to change the width: pointer-down lifts the
   ceiling, pointer-up records the result and puts it back. */

import type { DockviewApi } from "dockview";
import { typeOf } from "./panelTypes";

const START: Record<string, number> = { system: 260, tools: 380 };
const KEY = "mele.column-widths.v1";

function load(): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}") as Record<string, number>;
  } catch {
    return {};
  }
}

function store(widths: Record<string, number>) {
  try {
    localStorage.setItem(KEY, JSON.stringify(widths));
  } catch {
    /* a full quota must not break the drag that filled it */
  }
}

export function widthFor(type: string): number {
  return load()[type] ?? START[type] ?? 0;
}

/* A new column is allocated by the split that creates it, and constraints only clamp
   the *next* allocation. So a freshly created column is set explicitly here.

   This is deliberately not called from the layout-change handler: setting a size
   fires a layout change, and doing that from the handler is the loop that locked the
   page. It runs only where a panel is added, which is a one-off act. */
export function pinNew(api: DockviewApi) {
  enforce(api);
  for (const group of api.groups) {
    const kind = group.panels[0]?.id.split("|")[0] ?? "";
    const type = typeOf(kind);
    if (type !== "system" && type !== "tools") continue;

    const wanted = widthFor(type);
    if (!wanted) continue;
    const element = (group as unknown as { element?: HTMLElement }).element;
    if (Math.abs(Math.round(element?.clientWidth ?? 0) - wanted) <= 2) continue;
    group.api.setSize({ width: wanted } as never);
  }
}

function rememberWidth(type: string, width: number) {
  if (width < 120) return;
  store({ ...load(), [type]: Math.round(width) });
}

/* What each column gets, in one pass.

   The pinned ones take their width, and the workspace takes the remainder as a
   minimum: without that it is simply the space the grid has left over, and any
   reallocation hands it to whoever asked. Giving it a floor is what stops a second
   tool from shrinking it from 904 to 380. */
export function enforce(api: DockviewApi) {
  let reserved = 0;

  for (const group of api.groups) {
    const kind = group.panels[0]?.id.split("|")[0] ?? "";
    const type = typeOf(kind);
    if (type !== "system" && type !== "tools") continue;

    const wanted = widthFor(type);
    if (!wanted) continue;
    group.api.setConstraints({ minimumWidth: wanted, maximumWidth: wanted });
    reserved += wanted;
  }

  // The canvas is the element the groups live in; its width is the budget.
  const host = (api.groups[0] as unknown as { element?: HTMLElement }).element?.parentElement;
  const total = host?.clientWidth ?? 0;
  if (!total) return;

  const separators = Math.max(api.groups.length - 1, 0) * 5;
  const room = Math.max(total - reserved - separators, 320);

  for (const group of api.groups) {
    const kind = group.panels[0]?.id.split("|")[0] ?? "";
    if (typeOf(kind) !== "workspace") continue;
    group.api.setConstraints({ minimumWidth: room });
  }
}

/** Unclamp, so a sash can move at all. */
export function release(api: DockviewApi) {
  for (const group of api.groups) {
    const kind = group.panels[0]?.id.split("|")[0] ?? "";
    const type = typeOf(kind);
    if (type !== "system" && type !== "tools") continue;
    group.api.setConstraints({ maximumWidth: undefined });
  }
}

function capture(api: DockviewApi) {
  for (const group of api.groups) {
    const kind = group.panels[0]?.id.split("|")[0] ?? "";
    const type = typeOf(kind);
    if (type !== "system" && type !== "tools") continue;
    const element = (group as unknown as { element?: HTMLElement }).element;
    const width = Math.round(element?.clientWidth ?? 0);
    if (width >= 120) rememberWidth(type, width);
  }
}

/** A drag is the only thing that may move a pinned column. */
export function trackSashes(api: DockviewApi): () => void {
  const down = (event: PointerEvent) => {
    if (!(event.target as HTMLElement | null)?.classList.contains("dv-sash")) return;
    release(api);
  };
  const up = (event: PointerEvent) => {
    if (!(event.target as HTMLElement | null)?.classList.contains("dv-sash")) return;
    capture(api);
    enforce(api);
  };
  window.addEventListener("pointerdown", down, true);
  window.addEventListener("pointerup", up);
  return () => {
    window.removeEventListener("pointerdown", down, true);
    window.removeEventListener("pointerup", up);
  };
}
