/* Putting a tool's result into the solution being written.

   Tools compute; the solution is where the working goes. Rather than each tool
   knowing how the editor works, they hand markdown to the problem the reader is
   working on.

   Which problem that is cannot be guessed from "whatever is open": two questions can
   be open side by side, and appending to both would put one reader's working into two
   drafts. So each solution pane announces itself when it is clicked, and that pane —
   the last one touched — is the one that receives. With nothing open there is no
   target, and the tool says so instead of reporting success into a void. */

type Target = { id: number; append: (markdown: string) => void };

const targets = new Map<number, Target>();
let activeId: number | null = null;

export function registerSolution(id: number, append: (markdown: string) => void): () => void {
  targets.set(id, { id, append });
  // The first pane to register becomes the target, so a single open question works
  // without the reader having to click it first.
  if (activeId === null) activeId = id;
  return () => {
    targets.delete(id);
    if (activeId === id) {
      const remaining = [...targets.keys()];
      activeId = remaining.length ? remaining[remaining.length - 1] : null;
    }
  };
}

/** Called by a pane when the reader interacts with it. The last one wins. */
export function activateSolution(id: number) {
  if (targets.has(id)) activeId = id;
}

export type AppendResult = { ok: true } | { ok: false; reason: string };

export function appendToSolution(markdown: string): AppendResult {
  const target = activeId === null ? null : targets.get(activeId);
  if (!target) {
    return { ok: false, reason: "Open a problem first — there is nothing to add to." };
  }
  target.append(markdown);
  return { ok: true };
}

export function hasSolutionTarget(): boolean {
  return activeId !== null && targets.has(activeId);
}
