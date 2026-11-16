/* The quiz list: a page of papers, and the random draw. */
(function () {
"use strict";

const { apiJson } = window.MELE_API;

document.addEventListener("DOMContentLoaded", () => {
  const go = document.getElementById("random-go");
  if (!go) return;
  go.addEventListener("click", async () => {
    const error = document.getElementById("random-error");
    error.hidden = true;
    try {
      const found = await apiJson("/api/quiz/random", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: document.getElementById("random-kind").value,
          unanswered_only: document.getElementById("random-unanswered").checked,
          favourites_only: document.getElementById("random-favourites").checked,
        }),
      });
      window.location.href = `/topics/${found.topic_id}/${found.question_id}`;
    } catch (failure) {
      error.textContent = failure.message;
      error.hidden = false;
    }
  });
});
})();
