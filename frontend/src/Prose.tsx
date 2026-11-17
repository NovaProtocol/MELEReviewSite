import { useEffect } from "react";
import katex from "katex";

/* The server renders prose to HTML and leaves formulas as spans carrying their
   TeX in an attribute. The classic pages hydrate those in place; so does this, and
   for the same reason: one parser, one escaping rule, and the browser only typesets.

   A component rather than a ref per panel keeps the call site honest: HTML goes in,
   typeset maths comes out, and a second render is a no-op because the spans are
   replaced by their own output. */
export function Prose({ html, className }: { html: string; className?: string }) {
  const ref = (node: HTMLElement | null) => {
    if (!node) return;
    hydrate(node);
  };

  useEffect(() => {
    // Nothing to do: the ref callback already ran for this node.
  }, [html]);

  return <div ref={ref} className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}

function hydrate(root: HTMLElement) {
  for (const node of root.querySelectorAll<HTMLElement>("[data-tex]")) {
    const tex = node.dataset.tex;
    if (!tex) continue;
    try {
      katex.render(tex, node, {
        throwOnError: false,
        strict: false,
        trust: false,
        displayMode: node.classList.contains("math-display"),
      });
    } catch {
      /* a formula that will not typeset stays as its source, which is readable */
    }
  }
}
