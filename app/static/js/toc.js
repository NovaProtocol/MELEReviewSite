/* The heading index beside a topic's notes.

   A chapter runs to thousands of words, so a reader needs a way in that is not
   "scroll until it looks familiar". The list is built from the page it sits next
   to, so it is always right: no editing step, no second copy of the headings to
   keep in step. */
(function () {
"use strict";

const MIN_HEADINGS = 3;

function slug(text, taken) {
  const base =
    text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 60) || "section";
  let id = base;
  let n = 2;
  while (taken.has(id)) id = `${base}-${n++}`;
  taken.add(id);
  return id;
}

function build(panel) {
  const nav = panel.querySelector(".topic-toc");
  const body = panel.querySelector(".topic-body");
  if (!nav || !body) return;

  const headings = [...body.querySelectorAll("h2, h3")];
  if (headings.length < MIN_HEADINGS) {
    nav.hidden = true;
    return;
  }

  const taken = new Set();
  const list = document.createElement("ol");
  list.className = "topic-toc__list";

  for (const heading of headings) {
    if (!heading.id) heading.id = slug(heading.textContent.trim(), taken);
    const item = document.createElement("li");
    item.className = `topic-toc__item is-${heading.tagName.toLowerCase()}`;
    const link = document.createElement("a");
    link.href = `#${heading.id}`;
    link.textContent = heading.textContent.trim();
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const offset = heading.getBoundingClientRect().top - panel.getBoundingClientRect().top;
      panel.scrollTop += offset - 8;
      heading.classList.add("is-flash");
      window.setTimeout(() => heading.classList.remove("is-flash"), 900);
      history.replaceState(null, "", `#${heading.id}`);
    });
    item.appendChild(link);
    list.appendChild(item);
  }

  nav.appendChild(list);
  nav.hidden = false;

  /* Which section is being read: the last heading that has crossed the top of the
     panel. Cheap, and it never picks the wrong one the way a ratio guess does. */
  let ticking = false;
  const mark = () => {
    ticking = false;
    const top = panel.getBoundingClientRect().top + 12;
    let current = headings[0];
    for (const heading of headings) {
      if (heading.getBoundingClientRect().top <= top) current = heading;
    }
    for (const link of list.querySelectorAll("a")) {
      const active = link.getAttribute("href") === `#${current.id}`;
      link.classList.toggle("is-active", active);
      if (active) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    }
  };
  panel.addEventListener("scroll", () => {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(mark);
  });
  mark();
}

function start() {
  for (const panel of document.querySelectorAll('.tab-panel[data-panel="resources"]')) {
    build(panel);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", start);
} else {
  start();
}
})();
