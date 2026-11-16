/* Writing a topic's Resources or Reference panel. Markdown, saved as source. */
(function () {
"use strict";

const { apiJson } = window.MELE_API;

document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("topic-page-editor");
  const form = document.getElementById("topic-page-form");
  if (!root || !form) return;

  const error = document.getElementById("page-error");
  const editor = (window.MELE_EDITOR || {}).page;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    const body = editor ? editor.value() : document.getElementById("f-page").value;
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      await apiJson(`/api/topics/${root.dataset.topic}/pages/${root.dataset.kind}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body }),
      });
      window.location.href = `/library/${root.dataset.topic}`;
    } catch (failure) {
      error.textContent = failure.message;
      error.hidden = false;
      button.disabled = false;
    }
  });
});
})();
