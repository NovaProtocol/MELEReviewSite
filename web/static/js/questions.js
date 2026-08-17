const LETTERS = ["A", "B", "C", "D", "E"];

let questions = [];
let mySolutions = {};

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function esc(s) { return (s || "").replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c])); }

async function loadTags() {
  const res = await api("/api/tags");
  const tags = await res.json();
  const sel = document.getElementById("q-tag");
  for (const t of tags) {
    const opt = document.createElement("option");
    opt.value = t.name;
    opt.textContent = t.name;
    sel.appendChild(opt);
  }
}

async function loadQuestions() {
  const params = new URLSearchParams();
  const search = document.getElementById("q-search").value.trim();
  const tag = document.getElementById("q-tag").value;
  const inactive = document.getElementById("q-inactive").checked;
  if (search) params.set("search", search);
  if (tag) params.set("tag", tag);
  if (inactive) params.set("include_inactive", "true");

  document.getElementById("q-loading").textContent = "Loading...";
  const qres = await api("/api/questions?" + params.toString());
  questions = await qres.json();

  // saved answers are only available to a logged-in account
  mySolutions = {};
  if (window.currentUser) {
    const sres = await api("/api/my/solutions", {}, true);
    if (sres.ok) {
      const sols = await sres.json();
      for (const s of sols) mySolutions[s.question_id] = s;
    }
  }
  document.getElementById("q-count").textContent = `${questions.length} questions`;
  render();
  document.getElementById("q-loading").textContent = "";
}

function render() {
  const list = document.getElementById("q-list");
  list.innerHTML = "";
  if (!questions.length) {
    list.appendChild(el("p", "muted", "No questions found."));
    return;
  }
  for (const q of questions) renderQuestion(list, q);
}

function renderQuestion(list, q) {
  const card = el("div", "q-card" + (q.active ? "" : " inactive"));
  card.appendChild(el("h3", "q-text", q.question_text));

  if (q.tags.length) {
    const tagWrap = el("div", "q-tags");
    for (const t of q.tags) tagWrap.appendChild(el("span", "q-tag", t));
    card.appendChild(tagWrap);
  }

  const choices = [q.choice_a, q.choice_b, q.choice_c, q.choice_d, q.choice_e].filter(Boolean);
  const answerBtns = el("div", "q-choices");
  choices.forEach((text, i) => {
    const btn = el("button", "q-choice", `${LETTERS[i]}. ${text}`);
    btn.dataset.idx = i;
    answerBtns.appendChild(btn);
  });
  card.appendChild(answerBtns);

  if (!window.currentUser) {
    card.appendChild(el("p", "login-hint", "Log in to save your answers."));
  }

  const feedback = el("div", "q-feedback");
  card.appendChild(feedback);

  const othersWrap = el("div", "q-others");
  const othersToggle = el("button", "btn btn-secondary btn-sm", "Others' solutions");
  const othersList = el("div", "q-others-list");
  othersList.hidden = true;
  othersWrap.appendChild(othersToggle);
  othersWrap.appendChild(othersList);
  card.appendChild(othersWrap);

  othersToggle.onclick = async () => {
    if (!othersList.hidden) { othersList.hidden = true; return; }
    othersList.hidden = false;
    othersList.innerHTML = "Loading...";
    const res = await api(`/api/questions/${q.id}/solutions`, {}, true);
    if (!res.ok) { othersList.textContent = "Failed to load."; return; }
    const sols = await res.json();
    othersList.innerHTML = "";
    if (!sols.length) { othersList.appendChild(el("p", "muted", "No solutions yet.")); return; }
    for (const s of sols) {
      let answerIdx = null;
      try {
        const parsed = JSON.parse(s.blocks);
        if (Array.isArray(parsed) && parsed[0] && typeof parsed[0].answer === "number") answerIdx = parsed[0].answer;
      } catch (e) { /* ignore */ }
      const label = answerIdx !== null ? ` — ${LETTERS[answerIdx]}` : "";
      othersList.appendChild(el("div", "q-other-item", `${s.account_name}${label}`));
    }
  };

  const saved = mySolutions[q.id];
  let savedAnswer = null;
  if (saved) {
    try {
      const parsed = JSON.parse(saved.blocks);
      if (Array.isArray(parsed) && parsed[0] && typeof parsed[0].answer === "number") savedAnswer = parsed[0].answer;
    } catch (e) { /* ignore malformed */ }
  }

  const actions = el("div", "q-actions");
  if (window.currentUser && window.currentUser.id === q.account_id) {
    const edit = el("a", "btn btn-secondary btn-sm", "Edit");
    edit.href = `/questions/${q.id}/edit`;
    actions.appendChild(edit);
  }
  if (!q.active) actions.appendChild(el("span", "badge", "hidden"));
  card.appendChild(actions);

  const apply = async (btn) => {
    const idx = Number(btn.dataset.idx);
    const res = await api(`/api/questions/${q.id}/solution`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ convention: "metric", blocks: JSON.stringify([{ answer: idx }]) }),
    });
    await res.json();
    showResult(q, idx, feedback);
    answerBtns.querySelectorAll("button").forEach(b => b.classList.remove("chosen"));
    btn.classList.add("chosen");
  };

  answerBtns.querySelectorAll("button").forEach(btn => {
    btn.onclick = () => apply(btn);
    if (savedAnswer !== null && Number(btn.dataset.idx) === savedAnswer) btn.classList.add("chosen");
  });

  if (!window.currentUser) {
    // read mode: show the correct answer and solution directly
    showResult(q, q.answer, feedback, true);
  } else if (savedAnswer !== null) {
    showResult(q, savedAnswer, feedback);
  }
}

function showResult(q, chosen, feedback, revealAnyway) {
  feedback.innerHTML = "";
  const answered = chosen !== null && q.answer !== null;
  if (revealAnyway) {
    const badge = el("span", "badge", "Answer");
    feedback.appendChild(badge);
  } else {
    const correct = chosen === q.answer;
    const badge = el("span", "badge " + (correct ? "ok" : "bad"), correct ? "Correct" : "Incorrect");
    feedback.appendChild(badge);
  }
  if (q.answer !== null) {
    const reveal = el("p", "reveal", `Answer: ${LETTERS[q.answer]}`);
    feedback.appendChild(reveal);
  }
  if (q.solution) {
    feedback.appendChild(el("div", "q-solution", q.solution));
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  await refreshLogin();  // resolve currentUser before deciding read vs answer mode
  await loadTags();
  await loadQuestions();
  document.getElementById("q-search").addEventListener("input", debounce(loadQuestions, 300));
  document.getElementById("q-tag").addEventListener("change", loadQuestions);
  document.getElementById("q-inactive").addEventListener("change", loadQuestions);
});

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}
