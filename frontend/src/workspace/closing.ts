/* Closing a panel, with one rule: a column never empties.

   dockview removes a group when its last panel goes, and the grid reallocates the
   space to a neighbour. That is the resize the reader did not ask for: closing a
   question widened the explorer, because the explorer was next to it.

   So the last workspace panel in a group is not simply closed. A placeholder goes
   into the group first, and only then does the panel leave, which leaves the group,
   and therefore the geometry, exactly where it was. */

import type { DockviewApi, DockviewPanelApi } from "dockview";

type Closer = (panel: DockviewPanelApi) => void;

let closer: Closer | null = null;

/** The workspace installs this once; the tab and header buttons call it. */
export function setPanelCloser(fn: Closer | null) {
  closer = fn;
}

export function closePanel(panel: DockviewPanelApi) {
  if (closer) closer(panel);
  else panel.close();
}

/** How many panels of each type a group holds, by panel id prefix. */
export function groupTypes(api: DockviewApi, groupId: string): string[] {
  const group = api.groups.find((item) => item.id === groupId);
  if (!group) return [];
  return group.panels.map((panel) => panel.id.split("|")[0]);
}
