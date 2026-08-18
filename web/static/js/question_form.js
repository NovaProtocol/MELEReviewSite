async function load() {
  if (QUESTION_ID === null) return;
  const res = await api(`/api/questions/${QUESTION_ID}`);
  const q = await res.json();
  document.getElementById("f-question").value = q.question_text;
  document.getElementById("f-choice-a").value = q.choice_a;
  document.getElementById("f-choice-b").value = q.choice_b;
  document.getElementById("f-choice-c").value = q.choice_c;
  document.getElementById("f-choice-d").value = q.choice_d;
  document.getElementById("f-choice-e").value = q.choice_e || "";
  document.getElementById("f-answer").value = q.answer === null ? "" : String(q.answer);
  document.getElementById("f-solution").value = q.solution || "";
  document.getElementById("f-tags").value = (q.tags || []).join(", ");
  document.getElementById("f-active").checked = q.active;
}

function collect() {
  return {
    question_text: document.getElementById("f-question").value,
    choice_a: document.getElementById("f-choice-a").value,
    choice_b: document.getElementById("f-choice-b").value,
    choice_c: document.getElementById("f-choice-c").value,
    choice_d: document.getElementById("f-choice-d").value,
    choice_e: document.getElementById("f-choice-e").value || null,
    answer: document.getElementById("f-answer").value === "" ? null : Number(document.getElementById("f-answer").value),
    solution: document.getElementById("f-solution").value || null,
    active: document.getElementById("f-active").checked,
    tags: document.getElementById("f-tags").value.split(",").map(s => s.trim()).filter(Boolean),
  };
}

function showError(msg) {
  const el = document.getElementById("f-error");
  el.textContent = msg;
  el.hidden = false;
}

document.addEventListener("DOMContentLoaded", () => {
  load();
  document.getElementById("question-form").addEventListener("submit", async e => {
    e.preventDefault();
    const body = collect();
    const res = QUESTION_ID === null
      ? await api("/api/questions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      : await api(`/api/questions/${QUESTION_ID}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (res.ok) { location.href = "/questions"; }
    else {
      const d = await res.json().catch(() => ({}));
      showError(d.detail || "Failed to save");
    }
  });
  const del = document.getElementById("f-delete");
  if (del) del.onclick = async () => {
    if (!confirm("Delete this question and all its solutions?")) return;
    await api(`/api/questions/${QUESTION_ID}`, { method: "DELETE" });
    location.href = "/questions";
  };
});
