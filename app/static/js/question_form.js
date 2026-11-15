/* Question authoring: create when the form has no id, update when it does. */

/* Shared helpers come from app.js; this file stays inside its own scope so two
   page scripts can load together without redeclaring the same binding. */
(function () {
"use strict";


const { apiJson } = window.MELE_API;

/* Tag picker: click an existing tag to add it, type a new one and press Enter.
   A question may carry any tag, including one that does not exist yet, so the
   free-text field is the primary path and the suggestions are just a shortcut. */
function wireTagPicker() {
  const host = document.getElementById("tag-input");
  const field = document.getElementById("f-tags");
  const chosen = document.getElementById("tag-chosen");
  const suggest = document.getElementById("tag-suggest");
  if (!host || !field || !chosen) return null;

  const selected = new Set(
    (host.dataset.selected || "").split(",").map((t) => t.trim()).filter(Boolean)
  );
  let known = [];

  const clean = (raw) =>
    raw.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  function render() {
    chosen.innerHTML = "";
    for (const name of [...selected].sort()) {
      const pill = document.createElement("span");
      pill.className = "tag-pill tag-pill--sm";
      pill.innerHTML = `${name} <span aria-hidden="true">×</span>`;
      pill.title = "Remove this tag";
      pill.addEventListener("click", () => {
        selected.delete(name);
        render();
      });
      chosen.appendChild(pill);
    }
  }

  function renderSuggestions() {
    if (!suggest) return;
    const term = clean(field.value);
    const matches = known.filter(
      (name) => !selected.has(name) && (!term || name.includes(term))
    );
    suggest.innerHTML = "";
    suggest.hidden = !matches.length;
    for (const name of matches.slice(0, 24)) {
      const pill = document.createElement("button");
      pill.type = "button";
      pill.className = "tag-pill tag-pill--sm";
      pill.textContent = name;
      pill.addEventListener("click", () => {
        selected.add(name);
        field.value = "";
        render();
        renderSuggestions();
      });
      suggest.appendChild(pill);
    }
  }

  function addFromField() {
    const name = clean(field.value);
    if (!name) return;
    selected.add(name);
    field.value = "";
    render();
    renderSuggestions();
  }

  field.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      addFromField();
    }
    if (event.key === "Backspace" && !field.value && selected.size) {
      const last = [...selected].sort().pop();
      selected.delete(last);
      render();
    }
  });
  field.addEventListener("input", renderSuggestions);

  fetch("/api/tags", { credentials: "include" })
    .then((response) => (response.ok ? response.json() : []))
    .then((tags) => {
      known = tags.map((tag) => tag.name);
      renderSuggestions();
    })
    .catch(() => {
      /* suggestions are optional; free text still works */
    });

  render();
  return { values: () => [...selected] };
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("question-form");
  if (!form) return;
  const tagPicker = wireTagPicker();
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
      tags: tagPicker ? tagPicker.values() : [],
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
