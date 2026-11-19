/* Minimising a panel.

   dockview has no collapse, and a group constrained to 40px does not come back by
   clearing the constraint: the grid keeps the track it allocated and no API call
   re-runs it. Four attempts at ordering setSize and setConstraints all left the
   strip at 40px.

   So restore does not resize anything: the panel is removed and re-added beside
   what is left, which runs a real allocation. The content is the same and the
   position is the one it had, so to the reader it is the panel coming back. */

import type { DockviewApi, DockviewGroupPanel, IDockviewPanel } from "dockview";

const collapsed = new Map<string, { panel: IDockviewPanel; anchor: string | null }>();

export function isMinimized(groupId: string): boolean {
  return collapsed.has(groupId);
}

export function toggle(api: DockviewApi, group: DockviewGroupPanel) {
  const panel = group.panels[0];
  if (!panel) return;

  if (collapsed.has(group.id)) {
    restore(api, group);
    return;
  }

  // Remember the panel and a neighbour, then take it out of the grid.
  const others = api.panels.filter((item) => item.id !== panel.id);
  collapsed.set(group.id, { panel, anchor: others[others.length - 1]?.id ?? null });
  panel.api.close();
}

/* Back beside whatever it was next to, which is where it was. A reopened panel gets
   a real allocation, so the width is the grid's decision rather than a value we
   argued with it about. */
function restore(api: DockviewApi, group: DockviewGroupPanel) {
  const saved = collapsed.get(group.id);
  collapsed.delete(group.id);
  if (!saved) return;

  const { panel, anchor } = saved;
  const kind = panel.id.split("|")[0];
  const position = anchor && api.getPanel(anchor)
    ? { referencePanel: anchor, direction: "right" as const }
    : undefined;

  const reopened = api.addPanel({
    id: `${kind}|${Math.random().toString(36).slice(2, 8)}`,
    component: kind,
    title: panel.title ?? kind,
    params: (panel as unknown as { params?: Record<string, string> }).params ?? {},
    ...(position ? { position } : {}),
  });
  reopened.api.setActive();
}
