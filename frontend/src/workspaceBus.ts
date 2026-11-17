/* Requests from one panel to the workspace: a click in the library opens a
   problem list, a click on a problem opens the question. Going through a bus keeps
   panels from importing the dock component, which would be a cycle. */

export type OpenRequest = {
  kind: string;
  title: string;
  params?: Record<string, string>;
};

type Handler = (request: OpenRequest) => void;

const handlers = new Set<Handler>();

export function openPanel(request: OpenRequest) {
  for (const handler of handlers) handler(request);
}

export function onOpenPanel(handler: Handler): () => void {
  handlers.add(handler);
  return () => handlers.delete(handler);
}
