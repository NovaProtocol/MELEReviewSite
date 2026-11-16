/* The question's own page: answer once, then the solutions unlock. */
(function () {
"use strict";

const { api, apiJson, escapeHtml } = window.MELE_API;
const { card } = window.MELE_CARD;

const host = () => document.getElementById("q-detail");
let question = null;
let revealed = false;

/* One order for the whole section. Reddit asks once and keeps it; so does this.
   The default is neither newest nor best: log10(votes) + age/12.5h means a fresh
   reply outranks everything, and an old reply has to earn real votes to climb
   back over the new ones. */
const SORT_KEY = "melereview:thread-sort";

function sortMode() {
  try {
    return localStorage.getItem(SORT_KEY) || "hot";
  } catch (error) {
    return "hot";
  }
}

function setSortMode(value) {
  try {
    localStorage.setItem(SORT_KEY, value);
  } catch (error) {
    /* a blocked store just means the default order each visit */
  }
}

function hot(item) {
  const votes = Math.max(Number(item.score) || 0, 1);
  const stamp = Date.parse(item.date_created) || 0;
  return Math.log10(votes) + stamp / 1000 / 45000;
}

function ordered(items) {
  const mode = sortMode();
  const list = [...items];
  if (mode === "new") {
    list.sort((a, b) => (Date.parse(b.date_created) || 0) - (Date.parse(a.date_created) || 0));
  } else if (mode === "top") {
    list.sort(
      (a, b) =>
        (b.score || 0) - (a.score || 0) ||
        (Date.parse(b.date_created) || 0) - (Date.parse(a.date_created) || 0)
    );
  } else {
    list.sort((a, b) => hot(b) - hot(a));
  }
  return list;
}

function when(value) {
  const stamp = Date.parse(value);
  if (!stamp) return "";
  return new Date(stamp).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/* Voting is the same control on a solution and on a reply, so it is written
   once. Clicking the arrow you already chose clears the vote, as Reddit does. */
function voteRail(item, path, onChange) {
  const rail = document.createElement("div");
  rail.className = "vote-mini";

  const score = document.createElement("span");
  score.className = "vote-mini__score";
  score.textContent = item.score || 0;
  let mine = item.my_vote || 0;

  async function cast(direction) {
    const value = mine === direction ? 0 : direction;
    try {
      const result = await apiJson(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ direction: value }),
      });
      mine = result.my_vote;
      score.textContent = result.score;
      up.classList.toggle("is-on", mine === 1);
      down.classList.toggle("is-on", mine === -1);
    } catch (error) {
      onChange();
    }
  }

  function arrow(direction, glyph, label) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "vote-mini__button";
    button.textContent = glyph;
    button.setAttribute("aria-label", label);
    if (mine === direction) button.classList.add("is-on");
    button.addEventListener("click", () => cast(direction));
    return button;
  }

  const up = arrow(1, "\u25B2", "Upvote");
  const down = arrow(-1, "\u25BC", "Downvote");
  rail.append(up, score, down);
  return rail;
}

function replyForm(solutionId, parentId, onDone, editing) {
  const form = document.createElement("form");
  form.className = "reply-form";
  form.hidden = true;

  const area = document.createElement("textarea");
  area.rows = 3;
  area.maxLength = 4000;
  area.placeholder = parentId ? "Reply to this" : "Reply to this solution";
  area.required = true;
  if (editing) area.value = editing.body || "";

  const actions = document.createElement("div");
  actions.className = "reply-form__actions";
  const send = document.createElement("button");
  send.type = "submit";
  send.className = "btn btn-sm btn-primary";
  send.textContent = editing ? "Save" : "Reply";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "btn btn-sm";
  cancel.textContent = "Cancel";
  actions.append(send, cancel);

  const error = document.createElement("p");
  error.className = "form-error";
  error.hidden = true;

  form.append(area, actions, error);
  cancel.addEventListener("click", () => {
    form.hidden = true;
    form.reset();
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    send.disabled = true;
    try {
      const path = editing ? `/api/replies/${editing.id}` : `/api/solutions/${solutionId}/replies`;
      const payload = editing
        ? { body: area.value }
        : { body: area.value, parent_id: parentId };
      await apiJson(path, {
        method: editing ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      form.reset();
      await onDone();
    } catch (failure) {
      error.textContent = failure.message;
      error.hidden = false;
    } finally {
      send.disabled = false;
    }
  });
  return form;
}

/* A reply renders itself and then its children. The indent stops growing after
   six levels so a long argument does not disappear off the right edge; the
   thread keeps going, it just stops moving. */
function replyNode(reply, depth, onDone) {
  const wrap = document.createElement("div");
  wrap.className = "reply";
  wrap.style.setProperty("--depth", Math.min(depth, 6));

  const head = document.createElement("div");
  head.className = "reply__head";

  const who = document.createElement("a");
  who.className = "reply__who";
  who.href = `/users/${reply.author_uid}`;
  who.textContent = `@${reply.author}`;

  const stamp = document.createElement("span");
  stamp.className = "reply__when";
  stamp.textContent = when(reply.date_created);

  const rail = voteRail(reply, `/api/replies/${reply.id}/vote`, onDone);

  head.append(who, stamp, rail);

  const actions = document.createElement("div");
  actions.className = "reply__actions";
  const react = document.createElement("button");
  react.type = "button";
  react.className = "reply__link";
  react.textContent = "Reply";
  actions.appendChild(react);
  // The box a reply is edited in replaces the reply box, and the next Edit must
  // replace whichever of the two is on screen.
  let currentForm = null;
  if (reply.can_edit) {
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "reply__link";
    edit.textContent = "Edit";
    edit.addEventListener("click", () => {
      const editForm = replyForm(reply.solution_id, reply.parent_id, onDone, reply);
      currentForm.replaceWith(editForm);
      currentForm = editForm;
      editForm.hidden = false;
      editForm.querySelector("textarea").focus();
    });
    actions.appendChild(edit);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "reply__link reply__link--danger";
    remove.textContent = "Delete";
    remove.addEventListener("click", async () => {
      if (!window.confirm("Delete this reply?")) return;
      await api(`/api/replies/${reply.id}`, { method: "DELETE" });
      await onDone();
    });
    actions.appendChild(remove);
  }
  head.appendChild(actions);

  const body = document.createElement("p");
  body.className = "reply__body";
  body.textContent = reply.body;

  const form = replyForm(reply.solution_id, reply.id, onDone);
  currentForm = form;
  react.addEventListener("click", () => {
    form.hidden = !form.hidden;
    if (!form.hidden) form.querySelector("textarea").focus();
  });

  wrap.append(head, body, form);

  const children = ordered(reply.replies || []);
  if (children.length) {
    const nest = document.createElement("div");
    nest.className = "reply__children";
    for (const child of children) nest.appendChild(replyNode(child, depth + 1, onDone));
    wrap.appendChild(nest);
  }
  return wrap;
}

function solutionCard(solution, onDone) {
  const article = document.createElement("article");
  article.className = "thread";

  const head = document.createElement("div");
  head.className = "thread__head";
  const who = document.createElement("a");
  who.className = "thread__who";
  who.href = `/users/${solution.author_uid}`;
  who.textContent = `@${solution.author}`;
  const stamp = document.createElement("span");
  stamp.className = "thread__when";
  stamp.textContent = when(solution.date_created);
  head.append(who, stamp, voteRail(solution, `/api/solutions/${solution.id}/vote`, onDone));

  article.appendChild(head);

  // Prose when there is prose, and the old photograph when there is only that.
  if (solution.body_html) {
    const prose = document.createElement("div");
    prose.className = "thread__body md";
    prose.innerHTML = solution.body_html;
    if (window.MELE_MATH) window.MELE_MATH.render(prose);
    article.appendChild(prose);
  } else if (solution.image_url) {
    const media = document.createElement("a");
    media.className = "thread__media";
    media.href = solution.image_url;
    media.target = "_blank";
    media.rel = "noopener";
    const image = document.createElement("img");
    image.src = solution.image_url;
    image.alt = `Solution by ${solution.author}`;
    image.loading = "lazy";
    media.appendChild(image);
    article.appendChild(media);
  }
  if (solution.note) {
    const note = document.createElement("p");
    note.className = "thread__note";
    note.textContent = solution.note;
    article.appendChild(note);
  }

  const actions = document.createElement("div");
  actions.className = "thread__actions";
  const react = document.createElement("button");
  react.type = "button";
  react.className = "reply__link";
  react.textContent = "Reply";
  actions.appendChild(react);
  if (solution.can_edit && editorApi()) {
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "reply__link";
    edit.textContent = "Edit";
    edit.addEventListener("click", () => beginEdit(solution));
    actions.appendChild(edit);
  }

  const form = replyForm(solution.id, null, onDone);
  react.addEventListener("click", () => {
    form.hidden = !form.hidden;
    if (!form.hidden) form.querySelector("textarea").focus();
  });
  article.append(actions, form);

  const replies = ordered(solution.replies || []);
  if (replies.length) {
    const nest = document.createElement("div");
    nest.className = "reply__children reply__children--root";
    for (const reply of replies) nest.appendChild(replyNode(reply, 0, onDone));
    article.appendChild(nest);
  }
  return article;
}

function renderSolutions() {
  const grid = document.getElementById("solution-grid");
  const empty = document.getElementById("solution-empty");
  if (!grid) return;
  grid.innerHTML = "";
  const solutions = ordered(question.solutions || []);
  empty.hidden = solutions.length > 0;
  for (const solution of solutions) grid.appendChild(solutionCard(solution, load));
}

/* ---- reporting a problem ---- */
function syncReport() {
  const section = document.getElementById("q-report");
  const open = document.getElementById("report-open");
  const form = document.getElementById("report-form");
  const done = document.getElementById("report-done");
  if (!section) return;
  section.hidden = false;
  const reported = Boolean(question && question.reported_by_me);
  if (open) open.hidden = reported || !form.hidden;
  if (done) done.hidden = !reported;
  if (reported && form) form.hidden = true;
}

async function sendReport(event) {
  event.preventDefault();
  const error = document.getElementById("report-error");
  const reason = document.getElementById("report-reason");
  const button = event.target.querySelector('button[type="submit"]');
  error.hidden = true;
  button.disabled = true;
  try {
    await apiJson(`/api/questions/${host().dataset.question}/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: reason.value }),
    });
    reason.value = "";
    await load();
  } catch (failure) {
    if (/already reported/i.test(failure.message)) {
      await load();
      return;
    }
    error.textContent = failure.message;
    error.hidden = false;
  } finally {
    button.disabled = false;
  }
}

/* ---- your solution ---- */
let editingId = null;
let manualEdit = false;
let editorOpen = false;

function editorApi() {
  return (window.MELE_EDITOR || {}).solution || null;
}

/* The panel is a single line until it is asked for: a way in, then the editor. */
function syncEditor() {
  const editor = editorApi();
  const saveButton = document.getElementById("solution-save");
  const removeButton = document.getElementById("solution-remove");
  const cancelButton = document.getElementById("solution-cancel-edit");
  const reportOpen = document.getElementById("report-open");
  const reportForm = document.getElementById("report-form");
  if (reportOpen && reportForm) {
    reportOpen.addEventListener("click", () => {
      reportForm.hidden = false;
      reportOpen.hidden = true;
      document.getElementById("report-reason").focus();
    });
  }
  const reportCancel = document.getElementById("report-cancel");
  if (reportCancel && reportForm) {
    reportCancel.addEventListener("click", () => {
      reportForm.hidden = true;
      document.getElementById("report-error").hidden = true;
      syncReport();
    });
  }
  if (reportForm) reportForm.addEventListener("submit", sendReport);

  const openButton = document.getElementById("solution-open");
  const wrap = document.getElementById("solution-editor-wrap");
  const title = document.getElementById("solution-editor-title");
  const mine = question && question.my_solution;

  if (wrap) wrap.hidden = !editorOpen;
  if (cancelButton) cancelButton.hidden = !editorOpen;
  if (openButton) openButton.hidden = editorOpen;

  if (!editorOpen) {
    if (title) title.textContent = "Your solution";
    if (openButton) {
      openButton.textContent = mine ? "Edit your solution" : "Add a solution";
    }
    return;
  }

  if (!editor || manualEdit) {
    if (title) title.textContent = editingId ? "Edit solution" : "Add your solution";
    if (removeButton) removeButton.hidden = !editingId;
    if (saveButton) saveButton.textContent = editingId ? "Save changes" : "Save solution";
    return;
  }

  editingId = mine ? mine.id : null;
  if (mine) editor.setValue(mine.body || "");
  if (title) title.textContent = mine ? "Edit your solution" : "Add your solution";
  if (saveButton) saveButton.textContent = mine ? "Save changes" : "Save solution";
  if (removeButton) removeButton.hidden = !mine;
}

/* Opening for yourself: the editor prefilled with what you already wrote, or
   blank when you have not written anything. */
function openOwnSolution() {
  const editor = editorApi();
  const mine = question && question.my_solution;
  manualEdit = false;
  editingId = mine ? mine.id : null;
  if (editor) editor.setValue(mine ? mine.body || "" : "");
  editorOpen = true;
  syncEditor();
  const panel = document.getElementById("q-upload");
  if (panel) panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function beginEdit(solution) {
  const editor = editorApi();
  if (!editor) return;
  manualEdit = true;
  editingId = solution.id;
  editorOpen = true;
  editor.setValue(solution.body || "");
  syncEditor();
  const panel = document.getElementById("q-upload");
  if (panel) {
    panel.hidden = false;
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

async function saveSolution() {
  const editor = editorApi();
  const error = document.getElementById("solution-error");
  const button = document.getElementById("solution-save");
  if (!editor || !error || !button) return;
  const body = editor.value();
  error.hidden = true;
  if (!body) {
    error.textContent = "Write something first.";
    error.hidden = false;
    return;
  }
  button.disabled = true;
  try {
    const path = editingId
      ? `/api/solutions/${editingId}`
      : `/api/questions/${host().dataset.question}/solution`;
    await apiJson(path, {
      method: editingId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body }),
    });
    manualEdit = false;
    editorOpen = false;
    await load();
  } catch (failure) {
    error.textContent = failure.message;
    error.hidden = false;
  } finally {
    button.disabled = false;
  }
}

async function removeSolution() {
  if (!editingId) return;
  if (!window.confirm("Remove this solution from the question?")) return;
  await api(`/api/solutions/${editingId}`, { method: "DELETE" });
  manualEdit = false;
  editorOpen = false;
  editingId = null;
  const editor = editorApi();
  if (editor) editor.setValue("");
  await load();
}

/* The gate, in one place, because three states decide it:
   unsolved, solved, or lost the privilege by never having had it. */
function syncGate() {
  const gate = document.getElementById("q-solutions-gate");
  const panel = document.getElementById("q-solutions-panel");
  const button = document.getElementById("show-solutions");
  const note = document.getElementById("gate-note");
  const upload = document.getElementById("q-upload");
  const remove = document.getElementById("solution-remove");

  // One of three states, decided once:
  //   solved and not yet revealed -> offer the button
  //   solved and revealed         -> the grid
  //   not solved                  -> the reason, and no way in
  if (question.may_see_solutions && revealed) {
    gate.hidden = true;
    panel.hidden = false;
    renderSolutions();
  } else if (question.may_see_solutions) {
    gate.hidden = false;
    panel.hidden = true;
    if (button) button.hidden = false;
    if (note) note.textContent = "Solved.";
  } else {
    gate.hidden = false;
    panel.hidden = true;
    if (button) button.hidden = true;
    if (note) {
      note.textContent = question.attempt
        ? "Wrong. Unlocks on a correct answer."
        : "Unlocks on a correct answer.";
    }
  }

  const canAnswer = host().dataset.canAnswer === "1";
  if (upload) upload.hidden = !canAnswer;
  if (!canAnswer && remove) remove.hidden = true;
}

function confirmation(letter) {
  const modal = document.getElementById("answer-modal");
  const text = document.getElementById("answer-modal-choice");
  text.textContent = letter;
  modal.hidden = false;
  document.getElementById("answer-confirm").focus();
  return new Promise((resolve) => {
    const confirmButton = document.getElementById("answer-confirm");
    const cancelButton = document.getElementById("answer-cancel");
    function finish(value) {
      modal.hidden = true;
      confirmButton.removeEventListener("click", onConfirm);
      cancelButton.removeEventListener("click", onCancel);
      document.removeEventListener("keydown", onKey);
      resolve(value);
    }
    function onConfirm() {
      finish(true);
    }
    function onCancel() {
      finish(false);
    }
    function onKey(event) {
      if (event.key === "Escape") finish(false);
    }
    confirmButton.addEventListener("click", onConfirm);
    cancelButton.addEventListener("click", onCancel);
    document.addEventListener("keydown", onKey);
  });
}

async function answer(letter) {
  if (!(await confirmation(letter))) return;
  try {
    const result = await apiJson(`/api/questions/${question.id}/attempt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chosen: letter }),
    });
    await load();
    const feedback = document.querySelector(".q-detail .q-feedback");
    if (feedback && result.is_correct) {
      feedback.hidden = false;
      feedback.className = "q-feedback is-correct";
      feedback.textContent = `Correct on try ${result.attempts}. The solutions are open below.`;
    } else if (feedback) {
      feedback.hidden = false;
      feedback.className = "q-feedback is-wrong";
      feedback.textContent = "Not this one. Read the problem again and try another choice.";
    }
  } catch (error) {
    const feedback = document.querySelector(".q-detail .q-feedback");
    if (feedback) {
      feedback.hidden = false;
      feedback.className = "q-feedback is-wrong";
      feedback.textContent = error.message;
    }
  }
}

async function load() {
  const list = host();
  if (!list) return;
  try {
    question = await apiJson(`/api/questions/${list.dataset.question}`);
    list.innerHTML = "";
    list.appendChild(
      card(question, {
        canModerate: list.dataset.canModerate === "1",
        detail: true,
        interactive: !question.attempt || !question.attempt.solved,
        onAnswer: answer,
        onChange: () => load(),
      })
    );
    syncGate();
    syncEditor();
    syncReport();
  } catch (error) {
    list.innerHTML = `<div class="empty"><p>${escapeHtml(error.message)}</p></div>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  if (!host()) return;
  load();

  const sort = document.getElementById("thread-sort");
  if (sort) {
    sort.value = sortMode();
    sort.addEventListener("change", () => {
      setSortMode(sort.value);
      if (question) renderSolutions();
    });
  }

  const show = document.getElementById("show-solutions");
  if (show) {
    show.addEventListener("click", () => {
      revealed = true;
      syncGate();
    });
  }

  const save = document.getElementById("solution-save");
  if (save) save.addEventListener("click", saveSolution);

  const remove = document.getElementById("solution-remove");
  if (remove) remove.addEventListener("click", removeSolution);

  const reportOpen = document.getElementById("report-open");
  const reportForm = document.getElementById("report-form");
  if (reportOpen && reportForm) {
    reportOpen.addEventListener("click", () => {
      reportForm.hidden = false;
      reportOpen.hidden = true;
      document.getElementById("report-reason").focus();
    });
  }
  const reportCancel = document.getElementById("report-cancel");
  if (reportCancel && reportForm) {
    reportCancel.addEventListener("click", () => {
      reportForm.hidden = true;
      document.getElementById("report-error").hidden = true;
      syncReport();
    });
  }
  if (reportForm) reportForm.addEventListener("submit", sendReport);

  const openButton = document.getElementById("solution-open");
  if (openButton) openButton.addEventListener("click", openOwnSolution);

  const cancelEdit = document.getElementById("solution-cancel-edit");
  if (cancelEdit) {
    cancelEdit.addEventListener("click", () => {
      manualEdit = false;
      editorOpen = false;
      editingId = null;
      const editor = editorApi();
      if (editor) editor.setValue("");
      syncEditor();
    });
  }
});
})();
