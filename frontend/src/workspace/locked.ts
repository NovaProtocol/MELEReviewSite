/* Columns that do not move.

   The map and the tools are fixed widths. Not "remembered" and not "as wide as the
   split happened to make them": a constant. Every split dockview performs divides
   space between neighbours, so anything that opens beside these must not take the
   space from them, and the workspace column absorbs whatever is left.

   Recording the width instead of fixing it is what produced a 772px explorer: the
   first time a tool opened, the grid split the window evenly and that even half got
   remembered as the reader's preference. */

import type { DockviewApi } from "dockview";
import { typeOf } from "./panelTypes";

export const EXPLORER_WIDTH = 260;
export const TOOLS_WIDTH = 380;

export function enforce(api: DockviewApi) {
  for (const group of api.groups) {
    const kind = group.panels[0]?.id.split("|")[0] ?? "";
    const type = typeOf(kind);
    if (type !== "system" && type !== "tools") continue;

    const width = type === "system" ? EXPLORER_WIDTH : TOOLS_WIDTH;
    group.api.setConstraints({ minimumWidth: width, maximumWidth: width });
  }
}
