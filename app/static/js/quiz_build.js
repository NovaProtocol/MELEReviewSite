/* Building a quiz: pick topics, set counts, and save the paper.

   Counts are the fiddly part of a 58-topic bank, so there are three ways to set
   them: per topic, every ticked topic at once, and every topic at once. */
(function () {
"use strict";

const { apiJson, escapeHtml } = window.MELE_API;

const $ = (id) => document.getElementById(id);

function topicRows() {
  return [...document.querySelectorAll(".quiz-topic")];
}

function rebuildCount() {
  let total = 0;
  const perSubject = {};
  for (const row of topicRows()) {
    const check = row.querySelector(".quiz-topic__check");
    const count = row.querySelector(".quiz-topic__count");
    const bank = Number(row.dataset.bank) || 0;
    if (!check.checked) count.value = "0";
    let value = check.checked ? Math.max(0, Math.min(Number(count.value) || 0, bank)) : 0;
    if (check.checked && value === 0 && bank > 0) {
      value = 1;
      count.value = "1";
    }
    count.disabled = !check.checked;
    total += value;
    const subject = row.closest(".quiz-subject");
    if (subject) {
      perSubject[subject.dataset.key] = (perSubject[subject.dataset.key] || 0) + value;
    }
  }
  $("quiz-count").textContent = String(total);
  const bulk = $("quiz-create");
  if (bulk) bulk.disabled = total === 0;
  for (const node of document.querySelectorAll("[data-subject-total]")) {
    const subject = node.closest(".quiz-subject");
    const count = subject ? perSubject[subject.dataset.key] || 0 : 0;
    node.textContent = count ? `${count} picked` : "";
  }
}

function selections() {
  const out = {};
  for (const row of topicRows()) {
    const check = row.querySelector(".quiz-topic__check");
    if (!check.checked) continue;
    const value = Number(row.querySelector(".quiz-topic__count").value) || 0;
    if (value > 0) out[row.dataset.topic] = value;
  }
  return out;
}

function applyToTicked() {
  const wanted = Math.max(0, Number($("quiz-bulk-count").value) || 0);
  for (const row of topicRows()) {
    const check = row.querySelector(".quiz-topic__check");
    if (!check.checked) continue;
    const bank = Number(row.dataset.bank) || 0;
    row.querySelector(".quiz-topic__count").value = String(Math.min(wanted, bank));
  }
  rebuildCount();
}

async function create() {
  const picked = selections();
  const error = $("quiz-error");
  error.hidden = true;
  if (!Object.keys(picked).length) {
    error.textContent = "Pick at least one topic and a number of questions.";
    error.hidden = false;
    return;
  }
  if (!$("quiz-title").value.trim()) {
    error.textContent = "Give the quiz a title, so the list is readable.";
    error.hidden = false;
    $("quiz-title").focus();
    return;
  }
  const button = $("quiz-create");
  button.disabled = true;
  try {
    const created = await apiJson("/api/quizzes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selections: picked,
        timer_minutes: Number($("quiz-timer").value),
        group: $("quiz-group").value,
        title: $("quiz-title").value.trim(),
        description: $("quiz-desc").value,
        is_private: $("quiz-private").checked,
        scores_public: $("quiz-scores").checked,
        filters: {
          kind: $("quiz-kind").value,
          unanswered_only: $("quiz-unanswered").checked,
          favourites_only: $("quiz-favourites").checked,
        },
      }),
    });
    window.location.href = `/quiz/${created.uid}`;
  } catch (failure) {
    error.textContent = failure.message;
    error.hidden = false;
    button.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  for (const subject of document.querySelectorAll(".quiz-subject")) {
    subject.dataset.key = subject.querySelector(".quiz-subject__name").textContent.trim();
  }

  for (const row of topicRows()) {
    row.querySelector(".quiz-topic__check").addEventListener("change", rebuildCount);
    row.querySelector(".quiz-topic__count").addEventListener("input", rebuildCount);
  }

  $("quiz-all").addEventListener("click", () => {
    for (const row of topicRows()) {
      row.querySelector(".quiz-topic__check").checked = Number(row.dataset.bank) > 0;
    }
    rebuildCount();
    applyToTicked();
  });
  $("quiz-none").addEventListener("click", () => {
    for (const row of topicRows()) {
      row.querySelector(".quiz-topic__check").checked = false;
      row.querySelector(".quiz-topic__count").value = "0";
    }
    rebuildCount();
  });
  $("quiz-bulk-apply").addEventListener("click", applyToTicked);
  $("quiz-bulk-count").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      applyToTicked();
    }
  });

  $("quiz-create").addEventListener("click", create);
  rebuildCount();
});
})();
