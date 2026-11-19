/* What a panel is, and therefore where it may go.

   Three kinds, because they behave differently in a way a reader can feel:

   system    the explorer. One of them, never stacked, cannot be closed. It is the
             map, and a map in two places is a wall.
   workspace the question, its problem list, a resource, a tag. These stack and
             split freely: they are the work.
   tools     a calculator, a converter, the formula search. They stack with each
             other and nothing else, because a calculator sharing a tab strip with
             a question is a tab you close by accident. */

export type PanelType = "system" | "workspace" | "tools";

export type PanelKind =
  | "explorer"
  | "welcome"
  | "filler"
  | "problems"
  | "question"
  | "resource"
  | "tagged"
  | "quiz"
  | "admin"
  | "search"
  | "solver"
  | "diagrams"
  | "properties"
  | "scientific"
  | "converter"
  | "formula"
  | "tool";

const TYPES: Record<PanelKind, PanelType> = {
  // The placeholder is not content: it is what stands where content would be, so it
  // must never count as a workspace panel or it closes the thing it replaced.
  welcome: "system",
  // A spacer that holds space while a panel is minimised. Not content, not closeable
  // by the reader, and never a place to read anything.
  filler: "system",
  explorer: "system",
  problems: "workspace",
  question: "workspace",
  resource: "workspace",
  tagged: "workspace",
  quiz: "workspace",
  admin: "workspace",
  search: "tools",
  solver: "tools",
  diagrams: "tools",
  properties: "workspace",
  scientific: "tools",
  converter: "tools",
  formula: "tools",
  tool: "tools",
};

export function typeOf(kind: string): PanelType {
  return TYPES[kind as PanelKind] ?? "workspace";
}

/** A panel of a kind whose instance is shared, so two of them cannot disagree. */
export function isSingleton(kind: string): boolean {
  return kind === "explorer";
}

/** System panels stay: there is always a map. */
export function canClose(kind: string): boolean {
  /* Neither the map nor the seat may be closed.

     The placeholder is a reserved column, not a document. Closing it hands the
     column's width to its neighbour, which is exactly the reflow everything else
     here exists to prevent: closing Start here made the explorer fill the screen.
     It goes away when content takes its place, and in no other way. */
  if (kind === "welcome" || kind === "filler") return false;
  return typeOf(kind) !== "system";
}

/** Tabs may hold several of a type, but never a mix. */
export function mayStack(a: string, b: string): boolean {
  return typeOf(a) === typeOf(b);
}

/** The title of a tab strip: the active panel's, which is the one on top. */
export function groupTitle(titles: string[]): string {
  return titles[titles.length - 1] ?? "Panel";
}
