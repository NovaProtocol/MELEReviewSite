/* Diagrams the prose describes in Mermaid.

   The source stays in the document as text, so a reader whose script fails sees
   the definition rather than an empty hole, and the server never draws anything. */
(function () {
"use strict";

let ready = false;

function start() {
  if (!window.mermaid || ready) return;
  window.mermaid.initialize({
    startOnLoad: false,
    // No HTML in labels and no click handlers: the diagram is a picture.
    securityLevel: "strict",
    theme: "base",
    themeVariables: {
      fontFamily: "Inter, system-ui, sans-serif",
      primaryColor: "#eef7f5",
      primaryTextColor: "#1b2430",
      primaryBorderColor: "#2f9e8f",
      lineColor: "#6b7a8a",
      fontSize: "14px",
    },
  });
  ready = true;
}

function render(root) {
  start();
  if (!window.mermaid) return;
  const scope = root || document;
  const nodes = [...scope.querySelectorAll("pre.mermaid:not([data-processed])")];
  for (const node of nodes) {
    // Keep the source: a re-render after a tab switch should start from it.
    if (!node.dataset.source) node.dataset.source = node.textContent;
  }
  if (!nodes.length) return;
  window.mermaid.run({ nodes }).catch(() => {
    /* a malformed diagram stays as its source, which is still readable */
  });
}

window.MELE_DIAGRAMS = { render };

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => render());
} else {
  render();
}
})();
