/* Putting a tool's result into the solution being written.

   Tools compute; the solution is where the working goes. Rather than each tool
   knowing how the editor works, they hand markdown to whichever question is open,
   and the pane appends it. If nothing is open, the text is kept so the reader is not
   told their work vanished. */

type Receiver = (markdown: string) => void;

const receivers = new Set<Receiver>();
let pending: string | null = null;

export function registerSolution(receiver: Receiver): () => void {
  receivers.add(receiver);
  if (pending) {
    receiver(pending);
    pending = null;
  }
  return () => {
    receivers.delete(receiver);
  };
}

export function appendToSolution(markdown: string) {
  if (!receivers.size) {
    pending = markdown;
    return;
  }
  for (const receiver of receivers) receiver(markdown);
}
