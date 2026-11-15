/* Question authoring: create when the form has no id, update when it does. */

/* Shared helpers come from app.js; this file stays inside its own scope so two
   page scripts can load together without redeclaring the same binding. */
(function () {
"use strict";


const { apiJson } = window.MELE_API;

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("question-form");
  if (!form) return;
  const questionId = form.dataset.id;

  const params = new URLSearchParams(window.location.search);
  const presetTopic = params.get("topic");
  if (presetTopic) {
    const select = document.getElementById("f-topic");
    if (select) select.value = presetTopic;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const error = document.getElementById("f-error");
    error.hidden = true;
    const payload = {
      topic_id: Number(document.getElementById("f-topic").value),
      body: document.getElementById("f-body").value,
      choice_a: document.getElementById("f-choice-a").value,
      choice_b: document.getElementById("f-choice-b").value,
      choice_c: document.getElementById("f-choice-c").value,
      choice_d: document.getElementById("f-choice-d").value,
      choice_e: document.getElementById("f-choice-e").value || null,
      correct_choice: document.getElementById("f-correct").value,
      explanation: document.getElementById("f-explanation").value || null,
      tags: document
        .getElementById("f-tags")
        .value.split(",")
        .map((part) => part.trim())
        .filter(Boolean),
    };
    try {
      if (questionId) {
        await apiJson(`/api/questions/${questionId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      } else {
        await apiJson("/api/questions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }
      window.location.href = "/topics/" + payload.topic_id;
    } catch (failure) {
      error.textContent = failure.message;
      error.hidden = false;
    }
  });
});
})();
