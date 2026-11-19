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

/* The editor is written against `app.js`: that is where `MELE_API` and the fetch
   wrapper live. Loading the editor alone leaves it with nothing to call, which is a
   missing dependency rather than a broken editor, so both are loaded in order. */
const SCRIPTS = ["/static/js/app.js?v=2", "/static/js/editor.js?v=2"];

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
}: {
  value: string;
  onChange?: (markdown: string) => void;
  onReady?: (api: EditorApi | null) => void;
}) {
  const host = useRef<HTMLDivElement | null>(null);
  const api = useRef<EditorApi | null>(null);
  const [error, setError] = useState("");
  const seeded = useRef(false);

  useEffect(() => {
    let live = true;

    // The editor's stylesheet belongs to the classic pages; the client needs it for
    // the same reason they do, and it is already cached for a member who has used them.
    if (!document.querySelector(`link[href="${STYLE}"]`)) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = STYLE;
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

        /* The script wires `.editor` elements on load, and this markup arrived after
           that. Its rescan hook is what makes a late mount possible. */
        window.MELE_EDITOR_WIRE?.();
        api.current = window.MELE_EDITOR?.mounted ?? null;
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

  return (
    <div className="editor-mount">
      {error && <p className="form-error">{error}</p>}
      <div ref={host} />
    </div>
  );
}
