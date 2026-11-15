/* Topic page: the list of question cards, and one filter menu above it.

   Every filter is independent: a question can be starred, hidden, unanswered and
   written by you at the same time, so each control adds its own condition rather
   than replacing another. The menu only decides what to ask for; the server does
   the filtering. */
(function () {
"use strict";

const { apiJson, escapeHtml } = window.MELE_API;
const { card } = window.MELE_CARD;

const host = () => document.getElementById("q-list");

const CHECKS = ["f-favourites", "f-hidden", "f-downvoted", "f-solution", "f-mine"];

function value(id) {
  const node = document.getElementById(id);
  return node ? node.value : "";
}

function checked(id) {
  const node = document.getElementById(id);
  return Boolean(node && node.checked);
}

function activeFilters() {
  let count = 0;
  if (value("f-answered") && value("f-answered") !== "all") count += 1;
  for (const id of CHECKS) if (checked(id)) count += 1;
  return count;
}

function syncCount() {
  const badge = document.getElementById("filter-count");
  if (!badge) return;
  const count = activeFilters();
  badge.textContent = String(count);
  badge.hidden = count === 0;
}

async function load() {
  const list = host();
  if (!list) return;
  const topicId = list.dataset.topic;
  const params = new URLSearchParams();
  const search = document.getElementById("q-search")?.value.trim();
  const sort = document.getElementById("q-sort")?.value;

  if (search) params.set("search", search);
  if (checked("f-favourites")) params.set("favourites", "true");
  if (checked("f-hidden")) params.set("show_hidden", "true");
  if (checked("f-downvoted")) params.set("show_downvoted", "true");
  if (checked("f-solution")) params.set("has_solution", "true");
  if (checked("f-mine")) params.set("mine", "true");
  if (value("f-answered") && value("f-answered") !== "all") {
    params.set("answer_state", value("f-answered"));
  }
  if (sort) params.set("sort", sort);

  list.innerHTML = '<p class="muted">Loading questions...</p>';
  try {
    const questions = await apiJson(`/api/topics/${topicId}/questions?${params}`);
    list.innerHTML = "";
    const count = document.getElementById("q-count");
    if (count) {
      count.textContent = `${questions.length} question${questions.length === 1 ? "" : "s"}`;
    }
    if (!questions.length) {
      list.innerHTML = '<div class="empty"><p>Nothing matches those filters.</p></div>';
      return;
    }
    const options = {
      canModerate: list.dataset.canModerate === "1",
      // A list shows the question and its choices, and nothing else.
      interactive: false,
      onChange: () => load(),
    };
    for (const question of questions) list.appendChild(card(question, options));
  } catch (error) {
    list.innerHTML = `<div class="empty"><p>${escapeHtml(error.message)}</p></div>`;
  }
  syncCount();
}

function openMenu(open) {
  const panel = document.getElementById("filter-panel");
  const toggle = document.getElementById("filter-toggle");
  if (!panel || !toggle) return;
  panel.hidden = !open;
  toggle.setAttribute("aria-expanded", open ? "true" : "false");
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

  const sort = document.getElementById("q-sort");
  if (sort) sort.addEventListener("change", load);

  const toggle = document.getElementById("filter-toggle");
  if (toggle) {
    toggle.addEventListener("click", () => {
      openMenu(document.getElementById("filter-panel").hidden);
    });
  }

  for (const id of ["f-answered", ...CHECKS]) {
    const node = document.getElementById(id);
    if (node) node.addEventListener("change", load);
  }

  const reset = document.getElementById("filter-reset");
  if (reset) {
    reset.addEventListener("click", () => {
      const answered = document.getElementById("f-answered");
      if (answered) answered.value = "all";
      for (const id of CHECKS) {
        const box = document.getElementById(id);
        if (box) box.checked = false;
      }
      load();
    });
  }

  // Clicking away or pressing Escape closes the menu, as a menu should.
  document.addEventListener("click", (event) => {
    const menu = document.getElementById("filter-menu");
    if (menu && !menu.contains(event.target)) openMenu(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") openMenu(false);
  });
});
})();
