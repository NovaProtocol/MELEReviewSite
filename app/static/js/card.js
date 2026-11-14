/* One question card, shared by the topic list and the question page.

   Two ideas are borrowed deliberately:
   - a post header (avatar, @name, date) so a question reads as somebody's post;
   - a vote rail with a running score, so the group can push bad questions out
     of view without a moderator.
   Favourite (star) and hide (eye) are independent personal flags.
*/
(function () {
"use strict";

const { api, apiJson, escapeHtml } = window.MELE_API;

const LETTERS = ["A", "B", "C", "D", "E"];

function initials(name) {
  return (name || "?").slice(0, 1).toUpperCase();
}

function shortDate(value) {
  const date = value ? new Date(value) : new Date();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${month}-${day}-${date.getFullYear()}`;
}

function avatarFor(question) {
  if (question.author_avatar) {
    const image = document.createElement("img");
    image.src = question.author_avatar;
    image.alt = "";
    return image;
  }
  return document.createTextNode(initials(question.author));
}

/* The header row: avatar, @name, date. */
function header(question) {
  const head = document.createElement("div");
  head.className = "q-head";

  const avatar = document.createElement("span");
  avatar.className = "q-head__avatar";
  avatar.appendChild(avatarFor(question));

  const who = document.createElement("div");
  who.className = "q-head__who";
  who.innerHTML =
    `<a class="q-head__name" href="#">@${escapeHtml(question.author || "unknown")}</a>` +
    `<span class="q-head__date">${shortDate(question.date_created)}</span>`;

  head.appendChild(avatar);
  head.appendChild(who);
  return head;
}

/* Star and eye: personal, instant, no confirmation. */
function personalActions(question, onChange) {
  const wrap = document.createElement("div");
  wrap.className = "q-personal";

  const star = document.createElement("button");
  star.type = "button";
  star.className = "icon-btn" + (question.is_favourite ? " is-on" : "");
  star.title = question.is_favourite ? "Remove from favourites" : "Favourite";
  star.setAttribute("aria-label", star.title);
  star.setAttribute("aria-pressed", question.is_favourite ? "true" : "false");
  star.innerHTML = "&#9733;";
  star.addEventListener("click", async (event) => {
    event.preventDefault();
    event.stopPropagation();
    const state = await apiJson(`/api/questions/${question.id}/favourite`, { method: "POST" });
    question.is_favourite = state.is_favourite;
    star.classList.toggle("is-on", state.is_favourite);
    star.setAttribute("aria-pressed", state.is_favourite ? "true" : "false");
    star.title = state.is_favourite ? "Remove from favourites" : "Favourite";
    if (onChange) onChange(state);
  });

  const eye = document.createElement("button");
  eye.type = "button";
  eye.className = "icon-btn" + (question.is_hidden_by_me ? " is-on" : "");
  eye.title = question.is_hidden_by_me ? "Show this question again" : "Hide this question";
  eye.setAttribute("aria-label", eye.title);
  eye.setAttribute("aria-pressed", question.is_hidden_by_me ? "true" : "false");
  eye.innerHTML = "&#128065;";
  eye.addEventListener("click", async (event) => {
    event.preventDefault();
    event.stopPropagation();
    const state = await apiJson(`/api/questions/${question.id}/hide-for-me`, { method: "POST" });
    question.is_hidden_by_me = state.is_hidden_by_me;
    eye.classList.toggle("is-on", state.is_hidden_by_me);
    eye.setAttribute("aria-pressed", state.is_hidden_by_me ? "true" : "false");
    eye.title = state.is_hidden_by_me ? "Show this question again" : "Hide this question";
    if (onChange) onChange(state);
  });

  wrap.appendChild(star);
  wrap.appendChild(eye);
  return wrap;
}

/* The vote rail. Voting the same way twice clears the vote. */
function voteRail(question, onChange) {
  const rail = document.createElement("div");
  rail.className = "q-vote";

  const up = document.createElement("button");
  up.type = "button";
  up.className = "vote-btn" + (question.vote === 1 ? " is-on" : "");
  up.title = "Upvote";
  up.setAttribute("aria-label", "Upvote");
  up.innerHTML = "&#9650;";

  const score = document.createElement("span");
  score.className = "vote-score";
  score.textContent = question.score;
  if (question.score < 0) score.classList.add("is-negative");

  const down = document.createElement("button");
  down.type = "button";
  down.className = "vote-btn" + (question.vote === -1 ? " is-on" : "");
  down.title = "Downvote";
  down.setAttribute("aria-label", "Downvote");
  down.innerHTML = "&#9660;";

  async function send(direction, event) {
    event.preventDefault();
    event.stopPropagation();
    const state = await apiJson(`/api/questions/${question.id}/vote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ direction }),
    });
    question.vote = state.vote;
    question.score = state.score;
    score.textContent = state.score;
    score.classList.toggle("is-negative", state.score < 0);
    up.classList.toggle("is-on", state.vote === 1);
    down.classList.toggle("is-on", state.vote === -1);
    if (onChange) onChange(state);
  }

  up.addEventListener("click", (event) => send(1, event));
  down.addEventListener("click", (event) => send(-1, event));

  rail.appendChild(up);
  rail.appendChild(score);
  rail.appendChild(down);
  return rail;
}

/* The statement and its choices. `answer` is filled once an attempt exists. */
function body(question, options) {
  const wrap = document.createElement("div");
  wrap.className = "q-body";

  const text = document.createElement("p");
  text.className = "q-body__text";
  text.textContent = question.body;
  wrap.appendChild(text);

  const choices = document.createElement("div");
  choices.className = "q-choices";
  const buttons = [];
  for (const letter of LETTERS) {
    const value = question.choices[letter];
    if (!value) continue;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "q-choice";
    button.dataset.letter = letter;
    button.innerHTML =
      `<span class="q-choice__letter">${letter}</span><span>${escapeHtml(value)}</span>`;
    choices.appendChild(button);
    buttons.push(button);
  }
  wrap.appendChild(choices);

  const feedback = document.createElement("p");
  feedback.className = "q-feedback";
  feedback.hidden = true;
  wrap.appendChild(feedback);

  function reveal(attempt) {
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

  if (question.attempt) reveal(question.attempt);

  for (const button of buttons) {
    button.addEventListener("click", async () => {
      try {
        const result = await apiJson(`/api/questions/${question.id}/attempt`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ chosen: button.dataset.letter }),
        });
        reveal({ chosen: button.dataset.letter, is_correct: result.is_correct });
      } catch (error) {
        feedback.hidden = false;
        feedback.className = "q-feedback is-wrong";
        feedback.textContent = error.message;
      }
    });
  }

  if (question.explanation) {
    const details = document.createElement("details");
    details.className = "q-explain";
    const summary = document.createElement("summary");
    summary.textContent = "Explanation";
    const paragraph = document.createElement("p");
    paragraph.textContent = question.explanation;
    details.appendChild(summary);
    details.appendChild(paragraph);
    wrap.appendChild(details);
  }

  return wrap;
}

/* The footer link into the question's own page. On that page itself the link
   would point at the page you are already on, so it is left out. */
function openLink(question) {
  const here = window.location.pathname.replace(/\/$/, "");
  if (here === `/topics/${question.topic_id}/${question.id}`) return null;
  const link = document.createElement("a");
  link.className = "q-open";
  link.href = `/topics/${question.topic_id}/${question.id}`;
  const label = question.solution_count
    ? `${question.solution_count} solution${question.solution_count === 1 ? "" : "s"}`
    : "Open question";
  link.textContent = label;
  return link;
}

function card(question, options) {
  const article = document.createElement("article");
  article.className = "q-card" + (question.is_hidden_by_me ? " is-mine-hidden" : "");
  article.dataset.id = question.id;

  const inner = document.createElement("div");
  inner.className = "q-card__main";

  const head = header(question);
  head.appendChild(personalActions(question, options.onChange));
  inner.appendChild(head);
  inner.appendChild(body(question, options));

  const foot = document.createElement("div");
  foot.className = "q-foot";
  const link = openLink(question);
  if (link) foot.appendChild(link);
  if (question.is_hidden || question.is_hidden_by_me) {
    const badge = document.createElement("span");
    badge.className = "badge badge--bad";
    badge.textContent = question.is_hidden ? "hidden by a moderator" : "hidden for you";
    foot.appendChild(badge);
  }
  if (question.is_hidden && options.canModerate) {
    const restore = document.createElement("button");
    restore.type = "button";
    restore.className = "btn btn-sm";
    restore.textContent = "Restore";
    restore.addEventListener("click", async () => {
      await apiJson(`/api/admin/content/question/${question.id}/restore`, { method: "POST" });
      options.onChange();
    });
    foot.appendChild(restore);
  }
  inner.appendChild(foot);

  article.appendChild(voteRail(question, options.onChange));
  article.appendChild(inner);
  return article;
}

window.MELE_CARD = { card, header, body, voteRail, personalActions, shortDate, initials };
})();
