import { useEffect, useRef, useState } from "react";

/* The site's own editor, mounted.

   It is a proven piece: Markdown and rich text over one value, media upload that
   writes its own /media/<uid> reference, formulas, and the rule that a cancelled
   edit discards whatever it uploaded. Rebuilding that in React is how it went
   missing once; this mounts the real one and talks to it through its documented
   interface.

   The markup comes from the server (`/editor/partial`) because the editor's HTML
   and the Jinja page's must be the same HTML: two copies would drift. */

type EditorApi = {
  value: () => string;
  setValue: (text: string) => void;
  discard: () => Promise<void>;
};

declare global {
  interface Window {
    MELE_EDITOR?: Record<string, EditorApi>;
    MELE_EDITOR_WIRE?: () => void;
  }
}

const STYLE = "/static/css/main.css?v=3";
const KATEX_CSS = "/static/vendor/katex/katex.min.css?v=1";

/* The editor is written against `app.js`: that is where `MELE_API` and the fetch
   wrapper live. Loading the editor alone leaves it with nothing to call, which is a
   missing dependency rather than a broken editor, so both are loaded in order. */
/* KaTeX and the maths renderer come first. The editor's rich view typesets formulas
   through window.MELE_MATH, which comes from math.js, which needs KaTeX: without both
   the preview showed raw TeX, so `\text{pascal}` appeared as literal source. */
const SCRIPTS = [
  "/static/vendor/katex/katex.min.js?v=1",
  "/static/js/math.js?v=1",
  "/static/js/app.js?v=2",
  "/static/js/editor.js?v=2",
];

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`could not load ${src}`));
    document.head.appendChild(script);
  });
}

async function loadEditor() {
  for (const src of SCRIPTS) await loadScript(src);
}

export function EditorMount({
  value,
  onChange,
  onReady,
  editorKey = "mounted",
}: {
  value: string;
  onChange?: (markdown: string) => void;
  onReady?: (api: EditorApi | null) => void;
  /** Unique per mounted editor. The markup arrives with a fixed key, and the
   *  wiring pass skips any key it has already seen — so two panes, or two copies of
   *  one question, left the second editor inert. */
  editorKey?: string;
}) {
  const host = useRef<HTMLDivElement | null>(null);
  const api = useRef<EditorApi | null>(null);
  const [error, setError] = useState("");
  const seeded = useRef(false);

  useEffect(() => {
    let live = true;

    // The editor's stylesheet belongs to the classic pages; the client needs it for
    // the same reason they do, and it is already cached for a member who has used them.
    for (const href of [STYLE, KATEX_CSS]) {
      if (document.querySelector(`link[href="${href}"]`)) continue;
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = href;
      document.head.appendChild(link);
    }

    (async () => {
      if (!host.current) return;
      try {
        if (!host.current.childElementCount) {
          const markup = await fetch("/editor/partial", {
            headers: { Accept: "text/html" },
            credentials: "include",
          }).then((response) => {
            if (!response.ok) throw new Error("the editor is unavailable");
            return response.text();
          });
          if (!live || !host.current) return;
          host.current.innerHTML = markup;
        }

        await loadEditor();
        if (!live) return;

        /* Give this instance its own key before the wiring pass runs, so the editor
           registry holds one entry per mounted editor instead of one entry total. */
        const root = host.current.querySelector<HTMLElement>(".editor");
        if (root) root.dataset.editor = editorKey;

        /* The script wires `.editor` elements on load, and this markup arrived after
           that. Its rescan hook is what makes a late mount possible. */
        window.MELE_EDITOR_WIRE?.();
        api.current = window.MELE_EDITOR?.[editorKey] ?? null;
        if (!api.current) throw new Error("the editor did not register");

        if (!seeded.current) {
          api.current.setValue(value);
          seeded.current = true;
        }
        onReady?.(api.current);

        const source = host.current.querySelector<HTMLTextAreaElement>(".editor__source");
        // A rich-mode edit does not touch the textarea, so the editor's own input
        // events are the signal rather than one element's.
        const notify = () => onChange?.(api.current?.value() ?? "");
        source?.addEventListener("input", notify);
        host.current?.querySelector(".editor__rich")?.addEventListener("input", notify);
      } catch (problem) {
        setError((problem as Error).message);
      }
    })();

    return () => {
      live = false;
      // Anything uploaded and not saved goes back, which is the editor's own rule.
      void api.current?.discard();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* An external change — a tool adding its working, or the same question opened in
     two panes — has to reach the editor. It is seeded once on mount, which is right
     for the first value and wrong for every later one: without this, "Add to solution"
     updated React state and the editor never noticed, so the button looked broken.
     The comparison is against the editor's own text, so typing does not trigger a
     write back into the element the reader is typing in. */
  useEffect(() => {
    if (!api.current) return;
    if (api.current.value() !== value) api.current.setValue(value);
  }, [value]);

  return (
    <div className="editor-mount">
      {error && <p className="form-error">{error}</p>}
      <div ref={host} />
    </div>
  );
}
