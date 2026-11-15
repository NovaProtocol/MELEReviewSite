/* Typeset every formula the server marked up.

   The renderer writes each formula as a span carrying its TeX in `data-tex`, so
   nothing is typeset on the server and the source is still there if the script
   never loads: the reader sees the TeX instead of a blank. */
(function () {
"use strict";

function render(root) {
  if (!window.katex) return;
  const scope = root || document;
  for (const node of scope.querySelectorAll("[data-tex]")) {
    if (node.dataset.rendered === "1") continue;
    const tex = node.getAttribute("data-tex") || "";
    try {
      window.katex.render(tex, node, {
        displayMode: node.classList.contains("math-display"),
        throwOnError: false,
        strict: false,
        // No \href or \url: a formula is not a place to hide a link.
        trust: false,
      });
      node.dataset.rendered = "1";
    } catch (error) {
      /* Leave the source visible rather than an empty box. */
    }
  }
}

window.MELE_MATH = { render };

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => render());
} else {
  render();
}
})();
