/* Topic page: question list, answer check, bookmarks, solution images, uploads. */

/* Shared helpers come from app.js; this file stays inside its own scope so two
   page scripts can load together without redeclaring the same binding. */
(function () {
"use strict";


const { api, apiJson, escapeHtml } = window.MELE_API;

const LETTERS = ["A", "B", "C", "D", "E"];

const listNode = () => document.getElementById("q-list");

function questionCard(question, options) {
  const card = document.createElement("article");
  card.className = "q-card" + (question.is_hidden ? " is-hidden" : "");
  card.dataset.id = question.id;

  const head = document.createElement("div");
  head.className = "q-card__head";
  const body = document.createElement("p");
  body.className = "q-card__body";
  body.textContent = question.body;
  head.appendChild(body);
  card.appendChild(head);

  const meta = document.createElement("div");
  meta.className = "q-card__meta";
  meta.innerHTML = `<span>@${escapeHtml(question.author || "unknown")}</span>`;
  if (question.is_hidden) meta.innerHTML += '<span class="badge badge--bad">hidden</span>';
  card.appendChild(meta);

  const choices = document.createElement("div");
  choices.className = "q-choices";
  const buttons = [];
  for (const letter of LETTERS) {
    const text = question.choices[letter];
    if (!text) continue;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "q-choice";
    button.dataset.letter = letter;
    button.innerHTML = `<span class="q-choice__letter">${letter}</span><span>${escapeHtml(text)}</span>`;
    choices.appendChild(button);
    buttons.push(button);
  }
  card.appendChild(choices);

  const feedback = document.createElement("p");
  feedback.className = "q-feedback";
  feedback.hidden = true;
  card.appendChild(feedback);

  function lockTo(attempt) {
    for (const button of buttons) {
      button.disabled = true;
      if (button.dataset.letter === question.correct_choice) button.classList.add("is-correct");
      else if (attempt && button.dataset.letter === attempt.chosen) button.classList.add("is-wrong");
    }
    if (attempt) {
      feedback.hidden = false;
      feedback.className = "q-feedback " + (attempt.is_correct ? "is-correct" : "is-wrong");
      feedback.textContent = attempt.is_correct
        ? "Correct."
        : "Not this one. The answer is " + question.correct_choice + ".";
    }
  }

  if (question.attempt) lockTo(question.attempt);

  for (const button of buttons) {
    button.addEventListener("click", async () => {
      const letter = button.dataset.letter;
      try {
        const result = await apiJson(`/api/questions/${question.id}/attempt`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ chosen: letter }),
        });
        lockTo({ chosen: letter, is_correct: result.is_correct });
      } catch (error) {
        feedback.hidden = false;
        feedback.className = "q-feedback is-wrong";
        feedback.textContent = error.message;
      }
    });
  }

  const actions = document.createElement("div");
  actions.className = "q-actions";

  const bookmark = document.createElement("button");
  bookmark.type = "button";
  bookmark.className = "btn btn-sm" + (question.bookmarked ? " btn-outline" : "");
  bookmark.textContent = question.bookmarked ? "Bookmarked" : "Bookmark";
  bookmark.addEventListener("click", async () => {
    const result = await apiJson(`/api/questions/${question.id}/bookmark`, { method: "POST" });
    question.bookmarked = result.bookmarked;
    bookmark.textContent = result.bookmarked ? "Bookmarked" : "Bookmark";
    bookmark.classList.toggle("btn-outline", result.bookmarked);
  });
  actions.appendChild(bookmark);

  if (question.explanation) {
    const explain = document.createElement("details");
    explain.className = "q-explain";
    const summary = document.createElement("summary");
    summary.textContent = "Explanation";
    const text = document.createElement("p");
    text.textContent = question.explanation;
    explain.appendChild(summary);
    explain.appendChild(text);
    actions.appendChild(explain);
  }

  if (options.canModerate && !question.is_hidden) {
    const hide = document.createElement("button");
    hide.type = "button";
    hide.className = "btn btn-sm";
    hide.textContent = "Hide";
    hide.addEventListener("click", async () => {
      if (!window.confirm("Hide this question from members?")) return;
      await apiJson(`/api/questions/${question.id}/hide`, { method: "POST" });
      load();
    });
    actions.appendChild(hide);
  }

  card.appendChild(actions);

  const solutionSection = document.createElement("section");
  solutionSection.className = "q-solution";
  const title = document.createElement("div");
  title.className = "q-solution__title";
  title.textContent = "Worked solutions";
  solutionSection.appendChild(title);

  if (question.solutions.length) {
    const grid = document.createElement("div");
    grid.className = "solution-grid";
    for (const solution of question.solutions) {
      const item = document.createElement("figure");
      item.className = "solution-item";
      const link = document.createElement("a");
      link.href = solution.image_url;
      link.target = "_blank";
      link.rel = "noopener";
      const image = document.createElement("img");
      image.src = solution.image_url;
      image.loading = "lazy";
      image.alt = `Solution by ${solution.author}`;
      link.appendChild(image);
      item.appendChild(link);
      const caption = document.createElement("figcaption");
      caption.className = "solution-item__meta";
      caption.innerHTML = `<span>@${escapeHtml(solution.author)}</span>` +
        (options.canModerate
          ? `<button type="button" class="q-hide-solution" data-solution="${solution.id}">hide</button>`
          : "");
      item.appendChild(caption);
      grid.appendChild(item);
    }
    solutionSection.appendChild(grid);
    if (options.canModerate) {
      for (const button of grid.querySelectorAll(".q-hide-solution")) {
        button.addEventListener("click", async () => {
          if (!window.confirm("Hide this solution?")) return;
          await apiJson(`/api/solutions/${button.dataset.solution}/hide`, { method: "POST" });
          load();
        });
      }
    }
  } else {
    const empty = document.createElement("p");
    empty.className = "solution-empty";
    empty.textContent = "Nobody has uploaded a solution yet.";
    solutionSection.appendChild(empty);
  }

  if (options.canAnswer) {
    const row = document.createElement("div");
    row.className = "upload-row";
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/png,image/jpeg,image/webp";
    const upload = document.createElement("button");
    upload.type = "button";
    upload.className = "btn btn-sm btn-primary";
    upload.textContent = "Upload my solution";
    upload.addEventListener("click", async () => {
      if (!input.files.length) {
        upload.textContent = "Choose an image first";
        return;
      }
      const data = new FormData();
      data.append("file", input.files[0]);
      upload.disabled = true;
      upload.textContent = "Uploading...";
      try {
        await api(`/api/questions/${question.id}/solution`, { method: "POST", body: data });
        load();
      } catch (error) {
        upload.textContent = error.message;
        upload.disabled = false;
      }
    });
    row.appendChild(input);
    row.appendChild(upload);
    solutionSection.appendChild(row);
  }

  card.appendChild(solutionSection);
  return card;
}

async function load() {
  const host = listNode();
  if (!host) return;
  const topicId = host.dataset.topic;
  const options = {
    canAnswer: host.dataset.canAnswer === "1",
    canModerate: host.dataset.canModerate === "1",
  };
  const params = new URLSearchParams();
  const search = document.getElementById("q-search")?.value.trim();
  const bookmarked = document.getElementById("q-bookmarks")?.checked;
  if (search) params.set("search", search);
  if (bookmarked) params.set("bookmarked", "true");

  host.innerHTML = '<p class="muted">Loading questions...</p>';
  try {
    const questions = await apiJson(`/api/topics/${topicId}/questions?${params.toString()}`);
    host.innerHTML = "";
    const count = document.getElementById("q-count");
    if (count) count.textContent = `${questions.length} question${questions.length === 1 ? "" : "s"}`;
    if (!questions.length) {
      host.innerHTML = '<div class="empty"><p>No questions here yet.</p></div>';
      return;
    }
    for (const question of questions) host.appendChild(questionCard(question, options));
  } catch (error) {
    host.innerHTML = `<div class="empty"><p>${escapeHtml(error.message)}</p></div>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  if (!listNode()) return;
  load();
  const search = document.getElementById("q-search");
  if (search) {
    let timer = null;
    search.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(load, 300);
    });
  }
  const bookmarks = document.getElementById("q-bookmarks");
  if (bookmarks) bookmarks.addEventListener("change", load);
});
})();
