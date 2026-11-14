/* Topic page: the list of question cards and the three filters above it. */
(function () {
"use strict";

const { apiJson, escapeHtml } = window.MELE_API;
const { card } = window.MELE_CARD;

const host = () => document.getElementById("q-list");

async function load() {
  const list = host();
  if (!list) return;
  const topicId = list.dataset.topic;
  const params = new URLSearchParams();
  const search = document.getElementById("q-search")?.value.trim();
  const favourites = document.getElementById("q-favourites")?.checked;
  const showHidden = document.getElementById("q-hidden")?.checked;
  const showDownvoted = document.getElementById("q-downvoted")?.checked;
  if (search) params.set("search", search);
  if (favourites) params.set("favourites", "true");
  if (showHidden) params.set("show_hidden", "true");
  if (showDownvoted) params.set("show_downvoted", "true");

  list.innerHTML = '<p class="muted">Loading questions...</p>';
  try {
    const questions = await apiJson(`/api/topics/${topicId}/questions?${params}`);
    list.innerHTML = "";
    const count = document.getElementById("q-count");
    if (count) {
      count.textContent = `${questions.length} question${questions.length === 1 ? "" : "s"}`;
    }
    if (!questions.length) {
      list.innerHTML = '<div class="empty"><p>No questions here yet.</p></div>';
      return;
    }
    const options = {
      canModerate: list.dataset.canModerate === "1",
      onChange: () => load(),
    };
    for (const question of questions) list.appendChild(card(question, options));
  } catch (error) {
    list.innerHTML = `<div class="empty"><p>${escapeHtml(error.message)}</p></div>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  if (!host()) return;
  load();

  const search = document.getElementById("q-search");
  if (search) {
    let timer = null;
    search.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(load, 300);
    });
  }
  for (const id of ["q-favourites", "q-hidden", "q-downvoted"]) {
    const box = document.getElementById(id);
    if (box) box.addEventListener("change", load);
  }
});
})();
