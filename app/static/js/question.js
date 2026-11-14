/* The question's own page: the statement and choices, then the solutions. */
(function () {
"use strict";

const { api, apiJson, escapeHtml } = window.MELE_API;
const { card } = window.MELE_CARD;

const host = () => document.getElementById("q-detail");
let question = null;

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

function showUpload() {
  const section = document.getElementById("q-upload");
  const canAnswer = host().dataset.canAnswer === "1";
  if (section) section.hidden = !canAnswer;
  const remove = document.getElementById("solution-remove");
  const mine = (question.solutions || []).some((s) => s.author_uid === question.viewer_uid);
  if (remove) remove.hidden = !canAnswer;
}

async function load() {
  const list = host();
  if (!list) return;
  const id = list.dataset.question;
  try {
    question = await apiJson(`/api/questions/${id}`);
    const mine = (window.MELE && window.MELE.viewerUid) || null;
    question.viewer_uid = mine;
    list.innerHTML = "";
    list.appendChild(
      card(question, {
        canModerate: list.dataset.canModerate === "1",
        onChange: () => load(),
      })
    );
    const gate = document.getElementById("q-solutions-gate");
    if (gate) gate.hidden = false;
    showUpload();
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
      document.getElementById("q-solutions-gate").hidden = true;
      document.getElementById("q-solutions-panel").hidden = false;
      renderSolutions();
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
