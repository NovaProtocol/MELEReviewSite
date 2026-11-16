/* Administration: tabs, permission toggles, the ban/revoke confirmation, content restore. */

/* Shared helpers come from app.js; this file stays inside its own scope so two
   page scripts can load together without redeclaring the same binding. */
(function () {
"use strict";


const { api, apiJson, escapeHtml } = window.MELE_API;

const modal = () => document.getElementById("confirm-modal");

function openModal({ title, html, requireCode, confirmLabel, onConfirm }) {
  const shell = modal();
  document.getElementById("confirm-title").textContent = title;
  document.getElementById("confirm-body").innerHTML = html;
  const field = document.getElementById("confirm-code-field");
  const input = document.getElementById("confirm-code");
  const execute = document.getElementById("confirm-execute");
  const error = document.getElementById("confirm-error");
  error.hidden = true;
  execute.textContent = confirmLabel || "Confirm";
  execute.disabled = true;
  field.hidden = !requireCode;
  input.value = "";
  if (requireCode) {
    input.addEventListener("input", () => {
      execute.disabled = input.value.trim() !== requireCode;
    });
    setTimeout(() => input.focus(), 30);
  } else {
    execute.disabled = false;
  }
  shell.hidden = false;
  execute.onclick = async () => {
    execute.disabled = true;
    try {
      await onConfirm();
      shell.hidden = true;
      window.location.reload();
    } catch (failure) {
      error.textContent = failure.message;
      error.hidden = false;
      execute.disabled = false;
    }
  };
}

function closeModal() {
  modal().hidden = true;
}

document.addEventListener("DOMContentLoaded", () => {
  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => {
      for (const other of document.querySelectorAll(".tab")) {
        other.classList.remove("is-active");
        other.setAttribute("aria-selected", "false");
      }
      tab.classList.add("is-active");
      tab.setAttribute("aria-selected", "true");
      for (const panel of document.querySelectorAll(".tab-panel")) {
        panel.classList.toggle("is-active", panel.dataset.panel === tab.dataset.tab);
      }
      if (tab.dataset.tab === "reports") loadReports();
    });
  }

  const cancel = document.getElementById("confirm-cancel");
  if (cancel) cancel.addEventListener("click", closeModal);
  const shell = modal();
  if (shell) {
    shell.addEventListener("click", (event) => {
      if (event.target === shell) closeModal();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !shell.hidden) closeModal();
    });
  }

  const table = document.getElementById("user-table");
  if (!table) return;

  for (const row of table.querySelectorAll("tr[data-user-id]")) {
    const userId = row.dataset.userId;
    const username = row.dataset.username;
    const permissions = Number(row.dataset.permissions || 0);

    const toggles = row.querySelectorAll("input[data-perm]");
    for (const toggle of toggles) {
      toggle.addEventListener("change", async () => {
        const bit = Number(toggle.dataset.perm);
        const next = toggle.checked
          ? Number(row.dataset.permissions) | bit
          : Number(row.dataset.permissions) & ~bit;
        try {
          const updated = await apiJson(`/api/admin/users/${userId}/permissions`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ permissions: next }),
          });
          row.dataset.permissions = String(updated.permissions);
          toggle.closest(".perm-chip").classList.toggle("is-on", toggle.checked);
        } catch (error) {
          toggle.checked = !toggle.checked;
          window.alert(error.message);
        }
      });
    }

    const chainButton = row.querySelector('[data-action="chain"]');
    if (chainButton) {
      chainButton.addEventListener("click", async () => {
        const chain = await apiJson(`/api/admin/users/${userId}/chain`);
        const descendants = chain.descendants.length
          ? `<ul>${chain.descendants.map((member) =>
              `<li>@${escapeHtml(member.username)} · ${escapeHtml(member.status)}</li>`).join("")}</ul>`
          : "<p>No one was invited by this account.</p>";
        openModal({
          title: `Chain under @${chain.user.username}`,
          html: `<p>Invited by: <strong>${escapeHtml(chain.invited_by || "nobody, this is a root account")}</strong></p>${descendants}`,
          requireCode: null,
          confirmLabel: "Close",
          onConfirm: async () => {},
        });
      });
    }

    const banButton = row.querySelector('[data-action="ban"]');
    if (banButton) {
      banButton.addEventListener("click", async () => {
        const preview = await apiJson(`/api/admin/users/${userId}/ban-preview`);
        openModal({
          title: `Ban @${preview.user.username}?`,
          html: `
            <p>Banning this account also revokes everyone invited beneath it, all the way down.</p>
            <ul>
              <li><strong>${preview.total_descendants}</strong> account${preview.total_descendants === 1 ? "" : "s"} will be revoked (${preview.direct_invitees} invited directly)</li>
              <li><strong>${preview.questions}</strong> question${preview.questions === 1 ? "" : "s"} and <strong>${preview.solutions}</strong> solution${preview.solutions === 1 ? "" : "s"} will stop appearing</li>
              <li><strong>${preview.open_invites}</strong> unused invitation${preview.open_invites === 1 ? "" : "s"} will be cancelled</li>
            </ul>
            <p>Nothing is deleted. Revoked accounts can come back with a new invitation from someone else.</p>`,
          requireCode: preview.user.username,
          confirmLabel: "Ban and revoke",
          onConfirm: () => apiJson(`/api/admin/users/${userId}/ban`, { method: "POST" }),
        });
      });
    }

    const revokeButton = row.querySelector('[data-action="revoke"]');
    if (revokeButton) {
      revokeButton.addEventListener("click", async () => {
        const preview = await apiJson(`/api/admin/users/${userId}/ban-preview`);
        openModal({
          title: `Revoke the invitations under @${preview.user.username}?`,
          html: `
            <p>The account itself keeps its access. Everyone it invited loses theirs.</p>
            <ul>
              <li><strong>${preview.total_descendants}</strong> account${preview.total_descendants === 1 ? "" : "s"} will be revoked</li>
              <li><strong>${preview.questions}</strong> question${preview.questions === 1 ? "" : "s"} and <strong>${preview.solutions}</strong> solution${preview.solutions === 1 ? "" : "s"} will stop appearing</li>
              <li><strong>${preview.open_invites}</strong> unused invitation${preview.open_invites === 1 ? "" : "s"} will be cancelled</li>
            </ul>
            <p>Use this when an account was compromised and invited people it should not have.</p>`,
          requireCode: preview.user.username,
          confirmLabel: "Revoke invitations",
          onConfirm: () => apiJson(`/api/admin/users/${userId}/revoke-subtree`, { method: "POST" }),
        });
      });
    }

    const reactivateButton = row.querySelector('[data-action="reactivate"]');
    if (reactivateButton) {
      reactivateButton.addEventListener("click", async () => {
        openModal({
          title: `Reactivate @${username}?`,
          html: "<p>The account gets its access back. Accounts revoked because of it stay revoked, and need a new invitation.</p>",
          requireCode: null,
          confirmLabel: "Reactivate",
          onConfirm: () => apiJson(`/api/admin/users/${userId}/reactivate`, { method: "POST" }),
        });
      });
    }
  }

  for (const button of document.querySelectorAll("[data-invite-revoke]")) {
    button.addEventListener("click", async () => {
      openModal({
        title: "Revoke this invitation?",
        html: "<p>The code stops working immediately. Anyone who already used it is unaffected.</p>",
        requireCode: null,
        confirmLabel: "Revoke",
        onConfirm: () => api(`/api/admin/invites/${button.dataset.inviteRevoke}`, { method: "DELETE" }).then((response) => {
          if (!response.ok) throw new Error("Could not revoke that invitation");
        }),
      });
    });
  }

  for (const button of document.querySelectorAll("[data-restore]")) {
    button.addEventListener("click", async () => {
      const kind = button.dataset.restore;
      const id = button.dataset.id;
      try {
        await apiJson(`/api/admin/content/${kind}/${id}/restore`, { method: "POST" });
        window.location.reload();
      } catch (error) {
        window.alert(error.message);
      }
    });
  }

  const subjectForm = document.getElementById("subject-form");
  if (subjectForm) {
    subjectForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await apiJson("/api/admin/subjects", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: document.getElementById("new-subject").value.trim() }),
        });
        window.location.reload();
      } catch (error) {
        window.alert(error.message);
      }
    });
  }

  const topicForm = document.getElementById("topic-form");
  if (topicForm) {
    topicForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await apiJson("/api/admin/topics", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            subject_id: Number(document.getElementById("new-topic-subject").value),
            name: document.getElementById("new-topic").value.trim(),
          }),
        });
        window.location.reload();
      } catch (error) {
        window.alert(error.message);
      }
    });
  }

  const search = document.getElementById("user-search");
  const statusFilter = document.getElementById("user-status");
  const applyFilter = () => {
    const term = (search?.value || "").trim().toLowerCase();
    const status = statusFilter?.value || "";
    let shown = 0;
    for (const row of table.querySelectorAll("tr[data-user-id]")) {
      const haystack = row.textContent.toLowerCase();
      const matchesTerm = !term || haystack.includes(term);
      const matchesStatus = !status || row.dataset.status === status;
      const visible = matchesTerm && matchesStatus;
      row.hidden = !visible;
      if (visible) shown += 1;
    }
    const count = document.getElementById("user-count");
    if (count) count.textContent = `${shown} shown`;
  };
  if (search) search.addEventListener("input", applyFilter);
  if (statusFilter) statusFilter.addEventListener("change", applyFilter);
  applyFilter();

  wireQuestionList();
});

/* The questions tab: live search, subject -> topic cascade, filters and sorting.
   Live is fine here because there are a handful of administrators; the member
   search is submitted for the same reason in reverse. */
/* The report queue: read the complaint, then say what was done about it. */
async function loadReports() {
  const list = document.getElementById("report-list");
  if (!list) return;
  let reports = [];
  try {
    reports = (await apiJson("/api/admin/reports")).reports;
  } catch (error) {
    list.innerHTML = `<li class="muted">${escapeHtml(error.message)}</li>`;
    return;
  }

  const badge = document.querySelector('.tab[data-tab="reports"]');
  if (badge) badge.textContent = reports.length ? `Reports (${reports.length})` : "Reports";

  if (!reports.length) {
    list.innerHTML = '<li class="muted">Nothing reported.</li>';
    return;
  }

  list.innerHTML = "";
  for (const item of reports) {
    const row = document.createElement("li");
    row.innerHTML =
      `<div>` +
      `<span class="cell-strong">${escapeHtml(item.question.slice(0, 140))}</span>` +
      `<span class="cell-sub">${escapeHtml(item.subject)} / ${escapeHtml(item.topic)} · ` +
      `reported by ${escapeHtml(item.reporter)}</span>` +
      `<span class="cell-sub report-reason">${escapeHtml(item.reason)}</span>` +
      `</div>` +
      `<div class="report-actions">` +
      `<a class="btn btn-sm" href="/topics/${item.topic_id}/${item.question_id}">Open</a>` +
      `<button class="btn btn-sm" data-settle="resolve" data-id="${item.id}">Resolve</button>` +
      `<button class="btn btn-sm" data-settle="dismiss" data-id="${item.id}">Dismiss</button>` +
      `</div>`;
    list.appendChild(row);
  }

  for (const button of list.querySelectorAll("[data-settle]")) {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await apiJson(`/api/admin/reports/${button.dataset.id}/${button.dataset.settle}`, {
          method: "POST",
        });
        await loadReports();
      } catch (error) {
        button.disabled = false;
        button.textContent = error.message;
      }
    });
  }
}

function wireQuestionList() {
  const table = document.getElementById("aq-table");
  if (!table) return;

  const search = document.getElementById("aq-search");
  const subject = document.getElementById("aq-subject");
  const topic = document.getElementById("aq-topic");
  const filter = document.getElementById("aq-filter");
  const sort = document.getElementById("aq-sort");
  const count = document.getElementById("aq-count");
  const tagHost = document.getElementById("aq-tags");
  const J = window.MELE_API;
  let activeTags = new Set();
  let timer = null;
  let requestId = 0;

  // Supplied by the template as a JSON script block, because this file is static.
  let subjects = [];
  const source = document.getElementById("aq-subjects-data");
  if (source) {
    try {
      subjects = JSON.parse(source.textContent || "[]");
    } catch (error) {
      subjects = [];
    }
  }

  function fillTopics() {
    const chosen = subjects.find((s) => String(s.id) === subject.value);
    topic.innerHTML = '<option value="">All topics</option>';
    topic.disabled = !chosen;
    if (chosen) {
      for (const item of chosen.topics) {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = item.name;
        topic.appendChild(option);
      }
    }
  }

  async function renderTags() {
    try {
      const tags = await J.apiJson("/api/tags?counts=true");
      tagHost.innerHTML = "";
      for (const tag of tags) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "tag-pill tag-pill--toggle" + (activeTags.has(tag.name) ? " is-on" : "");
        button.innerHTML =
          J.escapeHtml(tag.name) + `<span class="tag-pill__count">${tag.questions}</span>`;
        button.addEventListener("click", () => {
          if (activeTags.has(tag.name)) activeTags.delete(tag.name);
          else activeTags.add(tag.name);
          button.classList.toggle("is-on", activeTags.has(tag.name));
          load();
        });
        tagHost.appendChild(button);
      }
    } catch (error) {
      tagHost.textContent = "";
    }
  }

  async function load() {
    const mine = ++requestId;
    const params = new URLSearchParams();
    if (search.value.trim()) params.set("q", search.value.trim());
    if (subject.value) params.set("subject", subject.value);
    if (topic.value) params.set("topic", topic.value);
    if (activeTags.size) params.set("tags", [...activeTags].join(","));
    params.set("filter", filter.value);
    params.set("sort", sort.value);

    try {
      const data = await J.apiJson(`/api/admin/questions?${params}`);
      if (mine !== requestId) return;  // a later keystroke already won
      const body = table.querySelector("tbody");
      body.innerHTML = "";
      if (count) {
        const filtered = subject.value || topic.value || search.value.trim() || activeTags.size;
        count.textContent =
          `${data.total} question${data.total === 1 ? "" : "s"}` +
          (filtered ? " matching" : "");
      }
      if (!data.items.length) {
        body.innerHTML = '<tr><td colspan="5" class="muted">Nothing matches those filters.</td></tr>';
        return;
      }
      for (const item of data.items) body.appendChild(row(item));
    } catch (error) {
      table.querySelector("tbody").innerHTML =
        `<tr><td colspan="5" class="muted">${J.escapeHtml(error.message)}</td></tr>`;
    }
  }

  function row(item) {
    const tr = document.createElement("tr");
    tr.dataset.questionId = item.id;
    const state = item.is_deleted
      ? '<span class="badge badge--bad">deleted</span>'
      : item.is_hidden
        ? '<span class="badge badge--warn">hidden</span>'
        : '<span class="badge badge--ok">visible</span>';
    const tags = (item.tags || []).map((tag) => `<span class="tag-pill tag-pill--sm">${J.escapeHtml(tag)}</span>`).join(" ");
    tr.innerHTML = `
      <td>
        <span class="cell-strong">${J.escapeHtml(item.body.slice(0, 120))}${item.body.length > 120 ? "…" : ""}</span>
        ${tags ? `<span class="aq-tags">${tags}</span>` : ""}
      </td>
      <td><span class="cell-sub">${J.escapeHtml(item.subject || "")} / ${J.escapeHtml(item.topic || "")}</span></td>
      <td><span class="cell-sub">${item.attempters} answered · ${item.solve_rate}% solved · ${item.average_attempts} avg · score ${item.score}</span></td>
      <td>${state}</td>
      <td class="col-actions">
        <a class="btn btn-sm btn-outline" href="/topics/${item.topic_id}/${item.id}" target="_blank" rel="noopener">Open</a>
        ${item.is_deleted
          ? `<button class="btn btn-sm" data-admin="restore-question" data-id="${item.id}">Restore</button>`
          : `<button class="btn btn-sm btn-danger" data-admin="delete-question" data-id="${item.id}">Delete</button>`}
      </td>`;
    return tr;
  }

  table.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-admin]");
    if (!button) return;
    const id = button.dataset.id;
    const action = button.dataset.admin;
    if (action === "delete-question") {
      if (!window.confirm("Delete this question? It leaves everyone's metrics and stays visible to you.")) return;
      await J.apiJson(`/api/admin/questions/${id}/delete`, { method: "POST" });
    } else {
      await J.apiJson(`/api/admin/questions/${id}/restore`, { method: "POST" });
    }
    load();
  });

  subject.addEventListener("change", () => {
    fillTopics();
    load();
  });
  topic.addEventListener("change", load);
  filter.addEventListener("change", load);
  sort.addEventListener("change", load);
  search.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(load, 250);
  });

  fillTopics();
  renderTags();
  load();
}
})();
