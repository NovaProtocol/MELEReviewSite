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

/* The header row: avatar, @name, date.

   Both the avatar and the name go to that member's page. The page resolves by
   uid, which survives a rename, so the link is built from the uid and never goes
   stale when somebody changes their username. */
function profileHref(question) {
  const key = question.author_uid || question.author;
  return key ? `/users/${encodeURIComponent(key)}` : null;
}

function header(question) {
  const head = document.createElement("div");
  head.className = "q-head";
  const href = profileHref(question);

  const avatar = document.createElement(href ? "a" : "span");
  avatar.className = "q-head__avatar";
  if (href) {
    avatar.href = href;
    avatar.title = `@${question.author || "member"}`;
  }
  avatar.appendChild(avatarFor(question));

  const who = document.createElement("div");
  who.className = "q-head__who";

  const name = document.createElement(href ? "a" : "span");
  name.className = "q-head__name";
  if (href) name.href = href;
  name.textContent = `@${question.author || "unknown"}`;

  const date = document.createElement("span");
  date.className = "q-head__date";
  date.textContent = shortDate(question.date_created);

  who.appendChild(name);
  who.appendChild(date);
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

/* The statement and its choices.

   ``options.interactive`` is false in a list, and there a card is only the
   question and its choices: nothing is marked, nothing is selectable, and the
   previous answer is not replayed. A list is for finding something to work on,
   and the whole point is that you do not get to remember what you said last
   time by glancing at it. What you have answered is shown by the ANSWERED badge
   in the header instead.

   ``options.detail`` marks the question's own page, which is the only place the
   edit control appears. */
const STRIKE_HINT = "This choice has been marked out. Right click to remove the marking.";
const UNSTRIKE_HINT = "Right click to mark this choice out.";

function body(question, options) {
  const wrap = document.createElement("div");
  wrap.className = "q-body";

  // The server renders the Markdown and escapes the author's text first, so the
  // HTML here is the site's own markup and nothing the author typed.
  const text = document.createElement("div");
  text.className = "q-body__text md";
  if (question.body_html) text.innerHTML = question.body_html;
  else text.textContent = question.body;
  // The card is built after the page's own scripts have run, so formulas are
  // typeset here rather than on load.
  if (window.MELE_MATH) window.MELE_MATH.render(text);
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

  /* Crossing a choice out is a note to yourself: it survives the visit, and a
     right click takes it back. It is a flag on the member's row, not an answer,
     so it works before the question has been attempted. */
  const struck = new Set((question.struck || "").split(""));
  function paintStrikes() {
    for (const button of buttons) {
      const isOut = struck.has(button.dataset.letter);
      button.classList.toggle("is-struck", isOut);
      button.title = isOut ? STRIKE_HINT : UNSTRIKE_HINT;
      button.setAttribute("aria-pressed", isOut ? "true" : "false");
    }
  }

  async function toggleStrike(event, button) {
    event.preventDefault();
    const letter = button.dataset.letter;
    const next = struck.has(letter) ? 0 : 1;
    try {
      const state = await apiJson(`/api/questions/${question.id}/strike`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ letter, value: next }),
      });
      question.struck = state.struck;
      struck.clear();
      for (const character of state.struck) struck.add(character);
      paintStrikes();
    } catch (error) {
      /* offline is not worth a dialog: the next click tries again */
    }
  }

  for (const button of buttons) {
    button.addEventListener("contextmenu", (event) => toggleStrike(event, button));
  }
  paintStrikes();

  /* Locking is earned only by a right answer. A wrong one marks the pick and
     leaves the rest live, because the next try is the point. The right letter is
     never shown to somebody who has not found it: that would end the exercise. */
  function reveal(attempt) {
    const solved = Boolean(attempt && attempt.is_correct);
    if (solved) {
      for (const button of buttons) {
        button.disabled = true;
        if (button.dataset.letter === question.correct_choice) {
          button.classList.add("is-correct");
        }
      }
      feedback.hidden = false;
      feedback.className = "q-feedback is-correct";
      feedback.textContent = "Correct.";
      return;
    }
    for (const button of buttons) {
      button.classList.remove("is-wrong");
      if (attempt && button.dataset.letter === attempt.chosen) {
        button.classList.add("is-wrong");
      }
    }
    if (attempt) {
      feedback.hidden = false;
      feedback.className = "q-feedback is-wrong";
      feedback.textContent =
        "Not this one. Read the problem again and try another choice.";
    }
  }

  if (!options.interactive) {
    for (const button of buttons) {
      button.classList.add("is-static");
      button.tabIndex = -1;
    }
    // The feedback line belongs to answering, and nothing is answered here.
    feedback.remove();
    return wrap;
  }

  if (question.attempt) reveal(question.attempt);

  for (const button of buttons) {
    button.addEventListener("click", () => options.onAnswer(button.dataset.letter));
  }

  if (question.explanation) {
    const details = document.createElement("details");
    details.className = "q-explain";
    const summary = document.createElement("summary");
    summary.textContent = "Note";
    const paragraph = document.createElement("div");
    paragraph.className = "md";
    if (question.note_html) paragraph.innerHTML = question.note_html;
    else paragraph.textContent = question.explanation;
    if (window.MELE_MATH) window.MELE_MATH.render(paragraph);
    details.appendChild(summary);
    details.appendChild(paragraph);
    wrap.appendChild(details);
  }

  return wrap;
}

/* Tags, as links. A tag is a way to gather questions from different topics, so
   clicking one has to be the obvious thing to do with it. */
function tagRow(question) {
  const tags = question.tags || [];
  if (!tags.length) return null;
  const row = document.createElement("div");
  row.className = "q-tags";
  for (const name of tags) {
    const link = document.createElement("a");
    link.className = "tag-pill tag-pill--sm";
    link.href = `/tags/${encodeURIComponent(name)}`;
    link.textContent = name;
    row.appendChild(link);
  }
  return row;
}

/* The footer link into the question's own page. On that page itself the link
   would point at the page you are already on, so it is left out.

   It used to read "3 solutions" when others had posted working and "Open
   question" otherwise, which looked like two different states of the question.
   It is one thing: the way in. */
function openLink(question) {
  const here = window.location.pathname.replace(/\/$/, "");
  if (here === `/topics/${question.topic_id}/${question.id}`) return null;
  const link = document.createElement("a");
  link.className = "q-open";
  link.href = `/topics/${question.topic_id}/${question.id}`;
  link.innerHTML = `<svg class="icon"><use href="#i-open"/></svg> Open`;
  return link;
}

function card(question, options) {
  const article = document.createElement("article");
  article.className = "q-card" + (question.is_hidden_by_me ? " is-mine-hidden" : "");
  article.dataset.id = question.id;

  const inner = document.createElement("div");
  inner.className = "q-card__main";

  const head = header(question);
  if (!options.detail && question.attempt) {
    const answered = document.createElement("span");
    answered.className = "q-answered";
    answered.textContent = "ANSWERED";
    head.appendChild(answered);
  }
  head.appendChild(personalActions(question, options.onChange));
  inner.appendChild(head);
  inner.appendChild(body(question, options));

  const tags = tagRow(question);
  if (tags) inner.appendChild(tags);

  const foot = document.createElement("div");
  foot.className = "q-foot";
  const link = openLink(question);
  if (link) foot.appendChild(link);
  // Editing is a decision about one question, so the control belongs on that
  // question's page, next to what it changes. A list is for scanning.
  if (question.can_edit && options.detail) {
    const edit = document.createElement("a");
    edit.className = "q-edit icon-btn";
    edit.href = `/questions/${question.id}/edit`;
    edit.title = "Edit";
    edit.setAttribute("aria-label", "Edit question");
    edit.innerHTML = `<svg class="icon"><use href="#i-pencil"/></svg>`;
    foot.appendChild(edit);
  }
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
