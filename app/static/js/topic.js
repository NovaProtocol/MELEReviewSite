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
  if (value("f-kind")) count += 1;
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
  if (value("f-kind")) params.set("kind", value("f-kind"));
  if (sort) params.set("sort", sort);

  // The address bar is the record: a filtered list can be linked, reloaded, and is
  // what decides the order of the next and previous buttons on a question.
  const url = new URL(window.location.href);
  url.search = params.toString();
  history.replaceState(null, "", url);

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

/* A link to a filtered list has to arrive filtered. */
function applyUrl() {
  const params = new URLSearchParams(window.location.search);
  const set = (id, value) => {
    const field = document.getElementById(id);
    if (field && value) field.value = value;
  };
  const check = (id, on) => {
    const field = document.getElementById(id);
    if (field && on) field.checked = true;
  };
  set("q-search", params.get("search") || "");
  set("q-sort", params.get("sort") || "newest");
  set("f-answered", params.get("answer_state") || "all");
  set("f-kind", params.get("kind") || "");
  check("f-favourites", params.get("favourites") === "true");
  check("f-hidden", params.get("show_hidden") === "true");
  check("f-downvoted", params.get("show_downvoted") === "true");
  check("f-solution", params.get("has_solution") === "true");
  check("f-mine", params.get("mine") === "true");
}

document.addEventListener("DOMContentLoaded", () => {
  if (!host()) return;
  applyUrl();
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

  for (const id of ["f-answered", "f-kind", ...CHECKS]) {
    const node = document.getElementById(id);
    if (node) node.addEventListener("change", load);
  }

  const reset = document.getElementById("filter-reset");
  if (reset) {
    reset.addEventListener("click", () => {
      const answered = document.getElementById("f-answered");
      if (answered) answered.value = "all";
      const kind = document.getElementById("f-kind");
      if (kind) kind.value = "";
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
