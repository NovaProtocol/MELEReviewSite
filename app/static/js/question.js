/* The question's own page: answer once, then the solutions unlock. */
(function () {
"use strict";

const { api, apiJson, escapeHtml } = window.MELE_API;
const { card } = window.MELE_CARD;

const host = () => document.getElementById("q-detail");
let question = null;
let revealed = false;

function renderSolutions() {
  const grid = document.getElementById("solution-grid");
  const empty = document.getElementById("solution-empty");
  if (!grid) return;
  grid.innerHTML = "";
  const solutions = question.solutions || [];
  empty.hidden = solutions.length > 0;
  for (const solution of solutions) {
    const item = document.createElement("figure");
    item.className = "solution-item";
    item.innerHTML =
      `<a href="${solution.image_url}" target="_blank" rel="noopener">` +
      `<img src="${solution.image_url}" alt="Solution by ${escapeHtml(solution.author)}" loading="lazy">` +
      `</a>` +
      `<figcaption class="solution-item__meta"><span>@${escapeHtml(solution.author)}</span></figcaption>`;
    grid.appendChild(item);
  }
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
    if (note) note.textContent = "You answered this one. Their working is a click away.";
  } else {
    gate.hidden = false;
    panel.hidden = true;
    if (button) button.hidden = true;
    if (note) {
      note.textContent = question.attempt
        ? "You got this one wrong. The solutions stay closed until you answer it correctly."
        : "Answer this question first. Getting it right unlocks everyone else's working.";
    }
  }

  const canAnswer = host().dataset.canAnswer === "1";
  if (upload) upload.hidden = !canAnswer;
  if (remove) remove.hidden = !canAnswer || !(question.solutions || []).length;
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
  } catch (error) {
    list.innerHTML = `<div class="empty"><p>${escapeHtml(error.message)}</p></div>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  if (!host()) return;
  load();

  const show = document.getElementById("show-solutions");
  if (show) {
    show.addEventListener("click", () => {
      revealed = true;
      syncGate();
    });
  }

  const upload = document.getElementById("solution-upload");
  if (upload) {
    upload.addEventListener("click", async () => {
      const input = document.getElementById("solution-file");
      const error = document.getElementById("solution-error");
      error.hidden = true;
      if (!input.files.length) {
        error.textContent = "Choose an image first.";
        error.hidden = false;
        return;
      }
      const data = new FormData();
      data.append("file", input.files[0]);
      upload.disabled = true;
      upload.textContent = "Uploading...";
      try {
        const response = await api(`/api/questions/${host().dataset.question}/solution`, {
          method: "POST",
          body: data,
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error((body.error && body.error.message) || "Upload failed");
        }
        await load();
      } catch (failure) {
        error.textContent = failure.message;
        error.hidden = false;
      } finally {
        upload.disabled = false;
        upload.textContent = "Upload";
      }
    });
  }

  const remove = document.getElementById("solution-remove");
  if (remove) {
    remove.addEventListener("click", async () => {
      if (!window.confirm("Remove your solution from this question?")) return;
      await api(`/api/questions/${host().dataset.question}/solution`, { method: "DELETE" });
      await load();
    });
  }
});
})();
