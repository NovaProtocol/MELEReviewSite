/* One saved quiz: the landing page, the sitting, and the result.

   Opening the link never starts the clock. The paper is read from the server, the
   first take is read back if it exists, and only Start begins a sitting. Answers
   are saved as they are picked, so a closed tab still scores. */
(function () {
"use strict";

const { apiJson, api } = window.MELE_API;

const LETTERS = ["A", "B", "C", "D", "E"];
const STRIKE_HINT = "This choice has been marked out. Right click to remove the marking.";
const UNSTRIKE_HINT = "Right click to mark this choice out.";

const $ = (id) => document.getElementById(id);
const root = $("quiz-root");
const uid = root ? root.dataset.uid : "";

const state = {
  quiz: null,
  questions: [],
  answers: {},
  struck: {},
  index: 0,
  practice: false,
  deadline: 0,
  ticker: null,
  savedTimer: null,
  startedAt: 0,
};

function num(value) {
  return Number.isFinite(value) ? value : 0;
}

function clock(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  if (value < 60) return `${value.toFixed(1)}s`;
  const total = Math.round(value);
  return `${Math.floor(total / 60)}m ${String(total % 60).padStart(2, "0")}s`;
}

/* ---------- landing ---------- */

function renderLanding() {
  const quiz = state.quiz;
  const settings = quiz.settings || {};
  $("landing-title").textContent = quiz.title;

  const bits = [
    `${quiz.questions.length} question${quiz.questions.length === 1 ? "" : "s"}`,
    settings.timer_minutes ? `${settings.timer_minutes} minute timer` : "no timer",
    `by ${quiz.owner}`,
  ];
  if (quiz.is_private) bits.push("unlisted");
  $("landing-meta").textContent = bits.join(" · ");

  if (quiz.description_html) {
    const desc = $("landing-desc");
    desc.innerHTML = quiz.description_html;
    if (window.MELE_MATH) window.MELE_MATH.render(desc);
    desc.hidden = false;
  }

  if (quiz.locked) {
    const lock = $("landing-lock");
    lock.textContent = quiz.locked;
    lock.hidden = false;
  }

  const first = quiz.my_first;
  const startFirst = $("start-first");
  const startPractice = $("start-practice");
  const hint = $("landing-hint");

  if (first && first.submitted) {
    startFirst.hidden = true;
    startPractice.hidden = Boolean(quiz.locked);
    hint.textContent = "Your first take is recorded. Practice runs do not change it.";
    showScorecard(first);
  } else if (first) {
    startFirst.textContent = "Continue your first take";
    startFirst.hidden = Boolean(quiz.locked);
    hint.textContent = "You have a first take in progress. The clock restarts if you continue.";
    showScorecard(first);
  } else {
    startFirst.hidden = Boolean(quiz.locked);
    hint.textContent = quiz.locked
      ? "This quiz cannot be taken."
      : "The clock starts when you press start, not when you open the link.";
  }

  renderBoard(quiz.leaderboard || [], quiz.scores_public);
  renderSubmissions(quiz.submissions || []);
}

function showScorecard(first) {
  const host = $("landing-score");
  host.hidden = false;
  host.innerHTML =
    `<span class="quiz-scorecard__score">${first.submitted ? `${num(first.score)}%` : "—"}</span>` +
    `<span class="quiz-scorecard__meta">` +
    (first.submitted
      ? `${num(first.correct)} of ${num(first.total)} correct · ${clock(num(first.duration_seconds))}`
      : "in progress") +
    `</span>`;
}

function renderBoard(rows, isPublic) {
  const board = $("landing-board");
  const note = $("landing-board-note");
  board.innerHTML = "";
  if (!isPublic) {
    note.hidden = false;
    board.hidden = true;
    return;
  }
  note.hidden = true;
  board.hidden = false;
  if (!rows.length) {
    board.innerHTML = '<li class="muted">Nobody has finished it yet.</li>';
    return;
  }
  rows.forEach((row, index) => {
    const li = document.createElement("li");
    li.innerHTML =
      `<span class="quiz-board__place">${index + 1}</span>` +
      `<span class="quiz-board__name">${row.user}</span>` +
      `<span class="quiz-board__score">${num(row.score)}%</span>` +
      `<span class="quiz-board__time">${clock(num(row.duration_seconds))}</span>`;
    board.appendChild(li);
  });
}

function renderSubmissions(rows) {
  if (!rows.length) return;
  $("landing-owner").hidden = false;
  const table = $("landing-subs");
  table.innerHTML =
    "<thead><tr><th>Member</th><th>Take</th><th>Score</th><th>Time</th><th>State</th></tr></thead>";
  const body = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td><a href="/users/${row.user_uid}">${row.user}</a></td>` +
      `<td>${row.is_first_take ? "first" : "practice"}</td>` +
      `<td>${row.score === null ? "—" : `${row.score}%`}</td>` +
      `<td>${row.duration_seconds === null ? "—" : clock(row.duration_seconds)}</td>` +
      `<td>${row.submitted ? "submitted" : "in progress"}</td>`;
    body.appendChild(tr);
  }
  table.appendChild(body);
}

/* ---------- runner ---------- */

function renderQuestion() {
  const host = $("run-question");
  const question = state.questions[state.index];
  if (!question) return;
  host.innerHTML = "";

  const meta = document.createElement("p");
  meta.className = "quiz-question__meta";
  meta.textContent = `Question ${state.index + 1} of ${state.questions.length}`;
  host.appendChild(meta);

  const body = document.createElement("div");
  body.className = "md quiz-question__body";
  body.innerHTML = question.body_html || question.body;
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
    const out = (state.struck[question.id] || new Set()).has(letter);
    if (state.answers[question.id] === letter) button.classList.add("is-picked");
    if (out) button.classList.add("is-struck");
    button.title = out ? STRIKE_HINT : UNSTRIKE_HINT;
    button.innerHTML =
      `<span class="quiz-choice__letter">${letter}</span>` +
      `<span class="md">${value}</span>`;
    button.addEventListener("click", () => pick(question.id, letter));
    button.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      toggleStrike(question.id, letter);
    });
    choices.appendChild(button);
  }
  host.appendChild(choices);

  $("run-progress").textContent =
    `${Object.keys(state.answers).length} answered of ${state.questions.length}`;
  $("run-nav").textContent = `${state.index + 1} / ${state.questions.length}`;
  $("run-prev").disabled = state.index === 0;
  $("run-next").disabled = state.index >= state.questions.length - 1;
}

function renderSheet() {
  const list = $("run-sheet");
  list.innerHTML = "";
  state.questions.forEach((question, index) => {
    const row = document.createElement("li");
    row.className = "sheet-row" + (index === state.index ? " is-current" : "");
    const number = document.createElement("button");
    number.type = "button";
    number.className = "sheet-row__number";
    number.textContent = String(index + 1);
    number.addEventListener("click", () => jump(index));

    const bubbles = document.createElement("div");
    bubbles.className = "sheet-row__bubbles";
    for (const letter of LETTERS) {
      if (!question.choices || !question.choices[letter]) continue;
      const bubble = document.createElement("button");
      bubble.type = "button";
      bubble.className = "sheet-bubble";
      bubble.textContent = letter;
      if (state.answers[question.id] === letter) bubble.classList.add("is-on");
      if ((state.struck[question.id] || new Set()).has(letter)) {
        bubble.classList.add("is-struck");
      }
      bubble.addEventListener("click", () => {
        state.index = index;
        pick(question.id, letter);
      });
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

function jump(index) {
  state.index = index;
  renderQuestion();
  renderSheet();
}

function toggleStrike(questionId, letter) {
  const set = state.struck[questionId] || new Set();
  if (set.has(letter)) set.delete(letter);
  else set.add(letter);
  state.struck[questionId] = set;
  renderQuestion();
  renderSheet();
}

function pick(questionId, letter) {
  state.answers[questionId] = letter;
  renderQuestion();
  renderSheet();
  queueProgress();
  if ($("run-auto").checked && state.index < state.questions.length - 1) jump(state.index + 1);
}

function queueProgress() {
  if (state.practice) return; // a practice run is not kept
  clearTimeout(state.savedTimer);
  state.savedTimer = setTimeout(async () => {
    try {
      await apiJson(`/api/quizzes/${uid}/progress`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answers: state.answers }),
      });
    } catch (error) {
      /* a dropped save is retried on the next answer, and submit sends everything */
    }
  }, 600);
}

function startClock(minutes) {
  const node = $("run-clock");
  if (state.ticker) clearInterval(state.ticker);
  if (!minutes) {
    node.hidden = true;
    return;
  }
  state.deadline = Date.now() + minutes * 60000;
  node.hidden = false;
  const tick = () => {
    const left = Math.max(0, state.deadline - Date.now());
    const total = Math.ceil(left / 1000);
    node.textContent = `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
    node.classList.toggle("is-low", left < 60000);
    if (left <= 0) {
      clearInterval(state.ticker);
      submit(true);
    }
  };
  tick();
  state.ticker = setInterval(tick, 1000);
}

async function begin(practice) {
  const error = $("landing-lock");
  try {
    const sitting = await apiJson(`/api/quizzes/${uid}/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ practice }),
    });
    state.practice = practice;
    state.answers = practice ? {} : sitting.answers || {};
    state.struck = {};
    state.index = 0;
    state.startedAt = Date.now();
    $("quiz-landing").hidden = true;
    $("quiz-result").hidden = true;
    $("quiz-runner").hidden = false;
    $("run-practice").hidden = !practice;
    startClock(Number(state.quiz.settings.timer_minutes) || 0);
    renderQuestion();
    renderSheet();
  } catch (failure) {
    error.textContent = failure.message;
    error.hidden = false;
  }
}

function askSubmit() {
  const blank = state.questions.length - Object.keys(state.answers).length;
  $("submit-body").textContent = blank
    ? `${blank} question${blank === 1 ? " is" : "s are"} still blank. Blank answers count as wrong, but the quiz still submits.`
    : "Everything is answered. This is your first take, so the score is kept and cannot be replaced.";
  $("submit-modal").hidden = false;
  $("submit-confirm").focus();
}

async function submit(forced) {
  if (state.ticker) clearInterval(state.ticker);
  const button = $("run-submit");
  button.disabled = true;
  try {
    const result = await apiJson(`/api/quizzes/${uid}/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers: state.answers, practice: state.practice }),
    });
    showResult(result, forced);
  } catch (failure) {
    button.disabled = false;
    const body = $("submit-body");
    $("submit-modal").hidden = false;
    body.textContent = failure.message;
  }
}

/* ---------- result ---------- */

function showResult(result, forced) {
  $("submit-modal").hidden = true;
  $("quiz-runner").hidden = true;
  $("quiz-result").hidden = false;
  $("result-eyebrow").textContent = state.practice ? "Practice run" : "Your first take";
  $("result-score").textContent = `${num(result.score)}%`;
  $("result-correct").textContent = `${num(result.correct)} of ${num(result.total)}`;
  $("result-time").textContent = clock(num(result.duration_seconds));
  $("result-average").textContent = result.total
    ? clock(num(result.duration_seconds) / num(result.total))
    : "—";
  $("result-answered").textContent = `${num(result.total)} of ${state.questions.length}`;
  $("result-practice").hidden = state.practice || Boolean(state.quiz.locked);

  const review = $("result-review");
  review.innerHTML = "";
  for (const question of state.questions) {
    const chosen = state.answers[question.id];
    const entry = (result.results || []).find((item) => item.question_id === question.id);
    const right = entry ? entry.correct : false;
    const row = document.createElement("div");
    row.className = "review-row" + (right ? " is-right" : " is-wrong");
    row.innerHTML =
      `<span class="review-row__mark">${right ? "✓" : "✕"}</span>` +
      `<span class="review-row__body">${question.preview || question.body.slice(0, 140)}</span>` +
      `<span class="review-row__answer">you ${chosen || "—"}` +
      (entry && entry.correct_choice ? ` · key ${entry.correct_choice}` : "") +
      `</span>` +
      `<a class="review-row__link" href="/library/${question.topic_id}/${question.id}">Open</a>`;
    review.appendChild(row);
  }

  drawSignature(uid);
  if (forced) $("result-eyebrow").textContent += " · time ran out";
}

/* A deterministic mark: the same quiz id always draws the same grid. It looks
   like a QR code and is not one; nothing is generated or stored on the server. */
function drawSignature(seedText) {
  const svg = $("signature");
  let hash = 2166136261;
  for (const character of seedText || "quiz") {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  let state32 = hash || 1;
  const random = () => {
    state32 ^= state32 << 13;
    state32 ^= state32 >>> 17;
    state32 ^= state32 << 5;
    state32 >>>= 0;
    return state32 / 4294967296;
  };

  const size = 21;
  const cells = [];
  const finder = (x, y) =>
    (x < 7 && y < 7) || (x >= size - 7 && y < 7) || (x < 7 && y >= size - 7);

  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      let filled;
      if (finder(x, y)) {
        const fx = x >= size - 7 ? x - (size - 7) : x;
        const fy = y >= size - 7 ? y - (size - 7) : y;
        const ring = Math.max(Math.abs(fx - 3), Math.abs(fy - 3));
        filled = ring !== 2;
      } else {
        filled = random() > 0.52;
      }
      if (filled) cells.push(`<rect x="${x}" y="${y}" width="1" height="1" rx="0.18"/>`);
    }
  }
  svg.innerHTML =
    `<rect width="${size}" height="${size}" fill="none"/>` +
    `<g fill="currentColor">${cells.join("")}</g>`;
  const label = $("signature-id");
  if (label) label.textContent = seedText ? seedText.slice(0, 12) : "";
}

/* ---------- wiring ---------- */

async function load() {
  try {
    state.quiz = await apiJson(`/api/quizzes/${uid}`);
    state.questions = state.quiz.questions || [];
    renderLanding();
  } catch (failure) {
    $("landing-meta").textContent = failure.message;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  if (!root) return;
  load();

  $("start-first").addEventListener("click", () => begin(false));
  $("start-practice").addEventListener("click", () => begin(true));
  $("result-practice").addEventListener("click", () => begin(true));

  $("run-prev").addEventListener("click", () => jump(Math.max(0, state.index - 1)));
  $("run-next").addEventListener("click", () =>
    jump(Math.min(state.questions.length - 1, state.index + 1))
  );
  $("run-submit").addEventListener("click", askSubmit);
  $("submit-cancel").addEventListener("click", () => {
    $("submit-modal").hidden = true;
  });
  $("submit-confirm").addEventListener("click", () => submit(false));

  $("copy-link").addEventListener("click", async () => {
    const link = `${window.location.origin}/quiz/${uid}`;
    try {
      await navigator.clipboard.writeText(link);
    } catch (error) {
      const scratch = document.createElement("textarea");
      scratch.value = link;
      document.body.appendChild(scratch);
      scratch.select();
      document.execCommand("copy");
      scratch.remove();
    }
    $("copy-link").textContent = "Link copied";
    setTimeout(() => {
      $("copy-link").textContent = "Copy link";
    }, 1600);
  });

  const remove = $("delete-quiz");
  if (remove) {
    remove.addEventListener("click", () => {
      $("delete-modal").hidden = false;
    });
    $("delete-cancel").addEventListener("click", () => {
      $("delete-modal").hidden = true;
    });
    $("delete-confirm").addEventListener("click", async () => {
      await api(`/api/quizzes/${uid}`, { method: "DELETE" });
      window.location.href = "/quiz";
    });
  }

  document.addEventListener("keydown", (event) => {
    if ($("quiz-runner").hidden) return;
    if (event.target.matches("input, textarea, select")) return;
    if (event.key === "ArrowRight") jump(Math.min(state.questions.length - 1, state.index + 1));
    if (event.key === "ArrowLeft") jump(Math.max(0, state.index - 1));
    const question = state.questions[state.index];
    const letter = event.key.toUpperCase();
    if (question && LETTERS.includes(letter) && question.choices && question.choices[letter]) {
      pick(question.id, letter);
    }
  });
});
})();
