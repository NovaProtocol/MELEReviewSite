/* Quiz mode: build a paper from the bank, run it against a clock, and score it.

   The page holds no state the code does not: a quiz is a list of question ids and
   a few settings, so reopening a code produces the same paper. Answers live here
   until submit, then they become ordinary attempts. */
(function () {
"use strict";

const { apiJson, escapeHtml } = window.MELE_API;

const LETTERS = ["A", "B", "C", "D", "E"];
const STRIKE_HINT = "This choice has been marked out. Right click to remove the marking.";
const UNSTRIKE_HINT = "Right click to mark this choice out.";
const state = {
  code: "",
  settings: null,
  questions: [],
  answers: {},
  struck: {},
  index: 0,
  deadline: 0,
  ticker: null,
};

const $ = (id) => document.getElementById(id);

/* ---------- builder ---------- */

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
    let value = check.checked ? Math.max(0, Math.min(Number(count.value) || 0, bank)) : 0;
    if (check.checked && value === 0 && bank > 0) {
      // Ticking a topic with no number is a request for one question, which is
      // almost always what was meant.
      value = 1;
      count.value = "1";
    }
    count.disabled = !check.checked;
    if (!check.checked) count.value = "0";
    total += value;
    const subject = row.closest(".quiz-subject");
    if (subject) perSubject[subject.dataset.key] = (perSubject[subject.dataset.key] || 0) + value;
  }
  $("quiz-count").textContent = String(total);
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

function filters() {
  return {
    kind: $("quiz-kind").value,
    unanswered_only: $("quiz-unanswered").checked,
    favourites_only: $("quiz-favourites").checked,
    exclude_topics: [],
  };
}

async function start() {
  const picked = selections();
  const error = $("quiz-error");
  error.hidden = true;
  if (!Object.keys(picked).length) {
    error.textContent = "Pick at least one topic.";
    error.hidden = false;
    return;
  }
  const button = $("quiz-start");
  button.disabled = true;
  try {
    const built = await apiJson("/api/quiz/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selections: picked,
        timer_minutes: Number($("quiz-timer").value),
        group: $("quiz-group").value,
        title: $("quiz-title").value,
        filters: filters(),
      }),
    });
    begin(built);
  } catch (failure) {
    error.textContent = failure.message;
    error.hidden = false;
  } finally {
    button.disabled = false;
  }
}

/* ---------- runner ---------- */

function begin(payload) {
  state.code = payload.code;
  state.settings = payload.settings || {};
  state.questions = payload.questions || [];
  state.answers = {};
  state.struck = {};
  state.index = 0;

  $("quiz-builder").hidden = true;
  $("quiz-result").hidden = true;
  $("quiz-random").hidden = true;
  $("quiz-runner").hidden = false;
  $("quiz-run-title").textContent = state.settings.title || "Quiz";
  // The code is the whole paper, so it is shown, not hidden behind a menu.
  $("quiz-code").textContent = state.code;
  $("quiz-copied").hidden = true;

  startClock();
  renderQuestion();
  renderSheet();
}

function startClock() {
  const minutes = Number(state.settings.timer_minutes) || 0;
  const clock = $("quiz-clock");
  if (state.ticker) clearInterval(state.ticker);
  if (!minutes) {
    clock.hidden = true;
    return;
  }
  state.deadline = Date.now() + minutes * 60000;
  clock.hidden = false;
  const tick = () => {
    const left = Math.max(0, state.deadline - Date.now());
    const total = Math.ceil(left / 1000);
    const mm = String(Math.floor(total / 60)).padStart(2, "0");
    const ss = String(total % 60).padStart(2, "0");
    clock.textContent = `${mm}:${ss}`;
    clock.classList.toggle("is-low", left < 60000);
    if (left <= 0) {
      clearInterval(state.ticker);
      send(true);
    }
  };
  tick();
  state.ticker = setInterval(tick, 1000);
}

function answered(questionId) {
  return state.answers[questionId] || null;
}

function struckFor(questionId) {
  return state.struck[questionId] || new Set();
}

function toggleStrike(questionId, letter) {
  const set = struckFor(questionId);
  if (set.has(letter)) set.delete(letter);
  else set.add(letter);
  state.struck[questionId] = set;
  renderQuestion();
  renderSheet();
}

function renderQuestion() {
  const host = $("quiz-question");
  const question = state.questions[state.index];
  if (!question) return;
  host.innerHTML = "";

  const meta = document.createElement("p");
  meta.className = "quiz-question__meta";
  meta.textContent = `Question ${state.index + 1} of ${state.questions.length}`;
  host.appendChild(meta);

  const body = document.createElement("div");
  body.className = "md quiz-question__body";
  body.innerHTML = question.body_html || escapeHtml(question.body);
  if (window.MELE_MATH) window.MELE_MATH.render(body);
  host.appendChild(body);

  const choices = document.createElement("div");
  choices.className = "quiz-choices";
  for (const letter of LETTERS) {
    const value = question.choices && question.choices[letter];
    if (!value) continue;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "quiz-choice";
    const out = struckFor(question.id).has(letter);
    if (answered(question.id) === letter) button.classList.add("is-picked");
    if (out) button.classList.add("is-struck");
    button.title = out ? STRIKE_HINT : UNSTRIKE_HINT;
    button.innerHTML =
      `<span class="quiz-choice__letter">${letter}</span>` +
      `<span class="md">${escapeHtml(value)}</span>`;
    button.addEventListener("click", () => pick(question.id, letter));
    button.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      toggleStrike(question.id, letter);
    });
    choices.appendChild(button);
  }
  host.appendChild(choices);

  $("quiz-progress").textContent =
    `${Object.keys(state.answers).length} answered of ${state.questions.length}`;
  $("quiz-nav-label").textContent = `${state.index + 1} / ${state.questions.length}`;
  $("quiz-prev").disabled = state.index === 0;
  $("quiz-next").disabled = state.index >= state.questions.length - 1;
}

function pick(questionId, letter) {
  state.answers[questionId] = letter;
  renderQuestion();
  renderSheet();
  // Rapid-fire mode: answering moves on, unless this was the last one.
  if ($("quiz-auto").checked && state.index < state.questions.length - 1) {
    go(1);
  }
}

function renderSheet() {
  const list = $("quiz-sheet-list");
  list.innerHTML = "";
  state.questions.forEach((question, index) => {
    const row = document.createElement("li");
    row.className = "sheet-row" + (index === state.index ? " is-current" : "");
    row.dataset.index = String(index);

    const number = document.createElement("button");
    number.type = "button";
    number.className = "sheet-row__number";
    number.textContent = String(index + 1);
    number.addEventListener("click", () => {
      state.index = index;
      renderQuestion();
      renderSheet();
    });

    const bubbles = document.createElement("div");
    bubbles.className = "sheet-row__bubbles";
    for (const letter of LETTERS) {
      if (!question.choices || !question.choices[letter]) continue;
      const bubble = document.createElement("button");
      bubble.type = "button";
      bubble.className = "sheet-bubble";
      bubble.textContent = letter;
      bubble.setAttribute("aria-label", `Question ${index + 1}, answer ${letter}`);
      if (answered(question.id) === letter) bubble.classList.add("is-on");
      if (struckFor(question.id).has(letter)) bubble.classList.add("is-struck");
      bubble.addEventListener("click", () => {
        state.answers[question.id] = letter;
        state.index = index;
        renderQuestion();
        renderSheet();
      });
      bubble.title = struckFor(question.id).has(letter) ? STRIKE_HINT : UNSTRIKE_HINT;
      bubble.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        toggleStrike(question.id, letter);
      });
      bubbles.appendChild(bubble);
    }
    row.append(number, bubbles);
    list.appendChild(row);
  });
}

function go(delta) {
  const next = state.index + delta;
  if (next < 0 || next >= state.questions.length) return;
  state.index = next;
  renderQuestion();
  renderSheet();
}

function askSubmit() {
  const unanswered = state.questions.length - Object.keys(state.answers).length;
  $("submit-modal-body").textContent = unanswered
    ? `${unanswered} question${unanswered === 1 ? " is" : "s are"} still blank. Blank answers count as wrong.`
    : "Everything is answered. Submitting records these answers the same way answering on a question page does.";
  $("submit-modal").hidden = false;
  $("submit-confirm").focus();
}

async function send(forced) {
  if (state.ticker) clearInterval(state.ticker);
  const button = $("quiz-submit");
  button.disabled = true;
  try {
    const result = await apiJson("/api/quiz/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: state.code, answers: state.answers }),
    });
    showResult(result, forced);
  } catch (failure) {
    $("quiz-error").textContent = failure.message;
    $("quiz-error").hidden = false;
    button.disabled = false;
  }
}

function showResult(result, forced) {
  $("submit-modal").hidden = true;
  $("quiz-runner").hidden = true;
  $("quiz-result").hidden = false;
  $("result-score").textContent = `${result.score}%`;
  $("result-summary").textContent = forced
    ? `Time ran out. ${result.correct} of ${result.total} correct.`
    : `${result.correct} of ${result.total} correct.`;

  const review = $("result-review");
  review.innerHTML = "";
  for (const item of result.results) {
    const row = document.createElement("div");
    row.className = "review-row" + (item.correct ? " is-right" : " is-wrong");
    row.innerHTML =
      `<span class="review-row__mark">${item.correct ? "✓" : "✕"}</span>` +
      `<span class="review-row__body">${escapeHtml(item.body)}</span>` +
      `<span class="review-row__answer">you ${item.chosen} · key ${item.correct_choice}</span>` +
      `<a class="review-row__link" href="/topics/${item.topic_id}/${item.question_id}">Open</a>`;
    review.appendChild(row);
  }
}

/* ---------- random ---------- */

function randomFilters() {
  const subject = $("random-subject").value;
  const hidden = [...document.querySelectorAll("#random-hide input:checked")].map((node) =>
    Number(node.value)
  );
  return {
    kind: $("random-kind").value,
    unanswered_only: $("random-unanswered").checked,
    favourites_only: $("random-favourites").checked,
    exclude_topics: hidden,
    subject_id: subject ? Number(subject) : null,
  };
}

function renderRandomTopics() {
  const subject = $("random-subject").value;
  const host = $("random-hide");
  host.innerHTML = "";
  if (!subject) return;
  const block = [...document.querySelectorAll(".quiz-subject")].find(
    (node) => node.dataset.subjectId === subject
  );
  if (!block) return;
  const title = document.createElement("p");
  title.className = "muted quiz-hint";
  title.textContent = "Leave a topic unticked to keep it out of the random draw.";
  host.appendChild(title);
  for (const row of block.querySelectorAll(".quiz-topic")) {
    const label = document.createElement("label");
    label.className = "filter-check";
    label.innerHTML =
      `<input type="checkbox" value="${row.dataset.topic}" checked> ` +
      `<span>${escapeHtml(row.querySelector(".quiz-topic__name").textContent.trim())}</span>`;
    host.appendChild(label);
  }
}

async function randomQuestion() {
  const error = $("random-error");
  error.hidden = true;
  try {
    const found = await apiJson("/api/quiz/random", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(randomFilters()),
    });
    window.location.href = `/topics/${found.topic_id}/${found.question_id}`;
  } catch (failure) {
    error.textContent = failure.message;
    error.hidden = false;
  }
}

/* ---------- wiring ---------- */

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
      const check = row.querySelector(".quiz-topic__check");
      const bank = Number(row.dataset.bank) || 0;
      check.checked = bank > 0;
    }
    rebuildCount();
  });
  $("quiz-none").addEventListener("click", () => {
    for (const row of topicRows()) {
      row.querySelector(".quiz-topic__check").checked = false;
      row.querySelector(".quiz-topic__count").value = "0";
    }
    rebuildCount();
  });
  $("quiz-start").addEventListener("click", start);
  $("quiz-prev").addEventListener("click", () => go(-1));
  $("quiz-next").addEventListener("click", () => go(1));
  $("quiz-submit").addEventListener("click", askSubmit);
  $("submit-cancel").addEventListener("click", () => {
    $("submit-modal").hidden = true;
  });
  $("submit-confirm").addEventListener("click", () => send(false));
  $("result-again").addEventListener("click", () => {
    $("quiz-result").hidden = true;
    $("quiz-builder").hidden = false;
    $("quiz-random").hidden = false;
  });
  $("quiz-copy").addEventListener("click", async () => {
    const link = `${window.location.origin}/quiz?code=${encodeURIComponent(state.code)}`;
    // The clipboard API needs a secure context; the staging host is plain HTTP, so
    // there is a second way that works anywhere.
    let copied = false;
    try {
      await navigator.clipboard.writeText(link);
      copied = true;
    } catch (error) {
      const scratch = document.createElement("textarea");
      scratch.value = link;
      scratch.setAttribute("readonly", "");
      scratch.style.position = "fixed";
      scratch.style.opacity = "0";
      document.body.appendChild(scratch);
      scratch.select();
      try {
        copied = document.execCommand("copy");
      } catch (failure) {
        copied = false;
      }
      scratch.remove();
    }
    if (!copied) {
      window.prompt("Copy this link", link);
      return;
    }
    $("quiz-copied").hidden = false;
    setTimeout(() => {
      $("quiz-copied").hidden = true;
    }, 1600);
  });
  $("quiz-sheet-toggle").addEventListener("click", () => {
    const sheet = $("quiz-sheet");
    sheet.classList.toggle("is-collapsed");
    $("quiz-sheet-toggle").textContent = sheet.classList.contains("is-collapsed")
      ? "Show"
      : "Hide";
  });

  $("random-subject").addEventListener("change", renderRandomTopics);
  $("random-go").addEventListener("click", randomQuestion);

  document.addEventListener("keydown", (event) => {
    if ($("quiz-runner").hidden) return;
    if (event.target.matches("input, textarea, select")) return;
    if (event.key === "ArrowRight") go(1);
    if (event.key === "ArrowLeft") go(-1);
    const letter = event.key.toUpperCase();
    const question = state.questions[state.index];
    if (question && LETTERS.includes(letter) && question.choices && question.choices[letter]) {
      pick(question.id, letter);
    }
  });

  // A shared code in the address bar opens that paper directly.
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code");
  if (code) {
    apiJson(`/api/quiz/${encodeURIComponent(code)}`)
      .then(begin)
      .catch((failure) => {
        $("quiz-error").textContent = failure.message;
        $("quiz-error").hidden = false;
      });
  }

  rebuildCount();
});
})();
