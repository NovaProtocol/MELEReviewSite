/* Library: reorder the topic cards without a page load.

   The cards are already in the document, so the sort reads each card's data
   attributes and re-appends them. No request, no flicker, and the syllabus order
   is restorable because that is the document order.
*/
(function () {
"use strict";

const order = new Map();
let selected = "syllabus";

/* The data lives on the anchor inside each list item, because that is the card.
   Reading it off the `<li>` silently yields empty strings, which is how the sort
   appeared to do nothing. */
const cardOf = (item) => item.querySelector(".topic-card") || item;

document.addEventListener("DOMContentLoaded", () => {
  const control = document.getElementById("lib-sort");
  const lists = [...document.querySelectorAll(".topic-grid")];
  if (!control || !lists.length) return;

  lists.forEach((list) => {
    [...list.children].forEach((card, index) => order.set(card, index));
  });

  const value = (item, name) => Number(cardOf(item).dataset[name] || 0);

  function sortList(list) {
    const cards = [...list.children];
    const comparators = {
      syllabus: (a, b) => order.get(a) - order.get(b),
      newest: (a, b) => value(b, "newest") - value(a, "newest"),
      questions: (a, b) => value(b, "questions") - value(a, "questions"),
      answers: (a, b) => value(b, "answers") - value(a, "answers"),
      name: (a, b) =>
        (cardOf(a).dataset.name || "").localeCompare(cardOf(b).dataset.name || ""),
    };
    cards.sort(comparators[selected] || comparators.syllabus);
    for (const card of cards) list.appendChild(card);
  }

  control.addEventListener("change", () => {
    selected = control.value;
    lists.forEach(sortList);
    try {
      localStorage.setItem("melereview.library.sort", selected);
    } catch (error) {
      /* storage is optional */
    }
  });

  try {
    const saved = localStorage.getItem("melereview.library.sort");
    if (saved && [...control.options].some((option) => option.value === saved)) {
      control.value = saved;
      selected = saved;
      lists.forEach(sortList);
    }
  } catch (error) {
    /* storage is optional */
  }
});
})();
