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
});
})();
