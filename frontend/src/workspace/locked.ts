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

/* Only the map is pinned by kind. The placeholder is system-shaped because it is not
   content, but it sits in the workspace column and must take that column's width. */
function isPinned(kind: string): boolean {
  if (kind === "welcome" || kind === "filler") return false;
  const type = typeOf(kind);
  return type === "system" || type === "tools";
}
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
  /* Only columns that were just *created* need this. An existing column already has
     its width, and re-applying it here is what shrank the workspace column to 260
     when a question replaced the placeholder inside it. */
  enforce(api);

  /* One frame later: the split allocates its column when the panel is added, and a
     size set inside that same tick is overwritten by it. Deferring is what makes the
     first spawn correct; the layout-change handler stays out of this because setting
     a size from there re-entered it and hung the page. */
  window.setTimeout(() => {
    for (const group of api.groups) {
      const kind = group.panels[0]?.id.split("|")[0] ?? "";
      if (!isPinned(kind)) continue;

      const wanted = widthFor(typeOf(kind));
      if (!wanted) continue;
      const element = (group as unknown as { element?: HTMLElement }).element;
      if (Math.abs(Math.round(element?.clientWidth ?? 0) - wanted) <= 2) continue;
      group.api.setSize({ width: wanted } as never);
    }
    enforce(api);
  }, 0);
}

function rememberWidth(type: string, width: number) {
  if (width < FLOOR) return;
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
    if (!isPinned(kind)) continue;

    const wanted = widthFor(typeOf(kind));
    if (!wanted) continue;

    /* Pinned: equal minimum and maximum. The ceiling is what makes an opening panel
       take its space from the workspace instead of from here. It also blocks a drag,
       which is why the drag path lifts it — see trackSashes. */
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
    // The seat counts as the workspace column: it is where content will go.
    if (typeOf(kind) !== "workspace" && kind !== "welcome" && kind !== "filler") continue;
    group.api.setConstraints({ minimumWidth: room });
  }
}

/* A drag must be free in BOTH directions.

   The pin is a floor equal to the remembered width, so leaving it in place during a
   drag meant the sash could only ever make a column wider: the floor was the current
   width, and the column could never return to being narrow. The floor drops to a
   small constant for the duration of the drag — enough that the column cannot vanish
   — and goes back to the new width on release. */
const FLOOR = 120;
const WORKSPACE_FLOOR = 320;

export function release(api: DockviewApi) {
  for (const group of api.groups) {
    const kind = group.panels[0]?.id.split("|")[0] ?? "";
    if (isPinned(kind)) {
      group.api.setConstraints({
        minimumWidth: FLOOR,
        maximumWidth: Number.MAX_SAFE_INTEGER,
      });
      continue;
    }
    /* The workspace column holds a minimum of all the space left over, which is what
       stops a panel stealing it. During a drag that floor is what the sash is pushing
       against, so it has to come down too or nothing moves. */
    const type = typeOf(kind);
    if (type === "workspace" || kind === "welcome" || kind === "filler") {
      group.api.setConstraints({ minimumWidth: WORKSPACE_FLOOR });
    }
  }
}

function capture(api: DockviewApi) {
  for (const group of api.groups) {
    const kind = group.panels[0]?.id.split("|")[0] ?? "";
    if (!isPinned(kind)) continue;
    const element = (group as unknown as { element?: HTMLElement }).element;
    const width = Math.round(element?.clientWidth ?? 0);
    if (width >= 120) rememberWidth(typeOf(kind), width);
  }
}

/** A drag is the only thing that may move a pinned column. */
export function trackSashes(api: DockviewApi): () => void {
  /* The target of a pointer event inside a sash may be the sash itself or anything
     dockview puts in it, so this walks up rather than testing one class. */
  const onSash = (event: Event) =>
    (event.target as HTMLElement | null)?.closest?.(".dv-sash") ?? null;

  const down = (event: PointerEvent) => {
    if (!onSash(event)) return;
    release(api);
  };
  const up = (event: PointerEvent) => {
    if (!onSash(event)) return;
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
