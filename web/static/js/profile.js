async function loadProfile() {
  await refreshLogin();
  if (!window.currentUser) {
    location.href = "/login";
    return;
  }
  const u = window.currentUser;
  document.getElementById("avatar").textContent = u.name[0].toUpperCase();
  document.getElementById("name").textContent = u.name;
  document.getElementById("joined").textContent = "Member since " + new Date(u.date_created).toLocaleDateString();

  const [solutionsRes, questionsRes] = await Promise.all([
    api("/api/my/solutions", {}, true),
    api("/api/questions", {}, true)
  ]);

  if (solutionsRes.ok) {
    const solutions = await solutionsRes.json();
    document.getElementById("stat-answers").textContent = solutions.length;
  }

  if (questionsRes.ok) {
    const allQuestions = await questionsRes.json();
    const myQuestions = allQuestions.filter(q => q.account_id === u.id);
    document.getElementById("stat-questions").textContent = myQuestions.length;
    renderQuestions(myQuestions);
  }
}

function renderQuestions(questions) {
  const list = document.getElementById("questions-list");
  const empty = document.getElementById("empty-state");
  if (questions.length === 0) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  list.innerHTML = "";
  for (const q of questions) {
    const item = document.createElement("div");
    item.className = "question-item";
    const text = q.question_text.length > 120 ? q.question_text.slice(0, 120) + "…" : q.question_text;
    item.innerHTML = `
      <div class="question-text">${escapeHtml(text)}</div>
      <div class="question-meta">
        ${q.tags.slice(0, 2).map(t => `<span class="question-tag">${escapeHtml(t)}</span>`).join("")}
        <a href="/questions/${q.id}/edit" class="question-edit">Edit</a>
      </div>
    `;
    list.appendChild(item);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadProfile();

  document.getElementById("pin-form").addEventListener("submit", async e => {
    e.preventDefault();
    const msg = document.getElementById("pin-message");
    msg.className = "";
    msg.textContent = "";
    msg.className = "pin-message error";
    msg.textContent = "PIN change not implemented yet";
    document.getElementById("new-pin").value = "";
  });

  document.getElementById("delete-btn").addEventListener("click", async () => {
    if (!confirm("Are you sure you want to delete your account? This cannot be undone.")) return;
    const res = await api("/api/auth/me", { method: "DELETE" });
    if (res.ok || res.status === 204) {
      await logout();
    } else {
      alert("Failed to delete account.");
    }
  });

  document.getElementById("logout-btn").addEventListener("click", () => logout());
});
