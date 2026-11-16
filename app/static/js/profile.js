/* The member page: three tabs over one set of numbers.

   Tabs are display only. Every panel is in the document, so the page works with
   the script off and nothing is fetched to switch. */
(function () {
"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const tabs = [...document.querySelectorAll(".tab[data-tab]")];
  if (!tabs.length) return;

  function show(name) {
    for (const tab of tabs) {
      const active = tab.dataset.tab === name;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    }
    for (const panel of document.querySelectorAll(".tab-panel[data-panel]")) {
      panel.classList.toggle("is-active", panel.dataset.panel === name);
    }
  }

  for (const tab of tabs) {
    tab.addEventListener("click", () => show(tab.dataset.tab));
  }
});
})();
