/* Account: identity fields, password, avatar and invitations.

   Every call names the account it changes, so the member editing themselves and
   the administrator editing someone else take the same path. */

(function () {
"use strict";

const { api, apiJson } = window.MELE_API;

const host = document.getElementById("account");
if (!host) return;

const uid = host.dataset.uid;
const isSelf = host.dataset.self === "1";
const base = `/api/users/${encodeURIComponent(uid)}`;

function note(message, isError) {
  const node = document.getElementById("profile-note");
  if (!node) return;
  node.textContent = message;
  node.hidden = !message;
  node.className = isError ? "form-error" : "form-note";
  if (!isError && message) node.setAttribute("style", "color: var(--ui-success)");
}

function field(id) {
  const node = document.getElementById(id);
  return node ? node.value : "";
}

function wire(formId, path, build, message) {
  const form = document.getElementById(formId);
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await apiJson(`${base}/${path}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(build()),
      });
      note(message, false);
      if (path === "username") setTimeout(() => window.location.reload(), 700);
    } catch (error) {
      note(error.message, true);
    }
  });
}

wire("username-form", "username", () => ({ username: field("p-username").trim() }), "Username saved.");
wire("email-form", "email", () => ({ email: field("p-email").trim() }), "Email saved.");
wire("bio-form", "bio", () => ({ bio: field("p-bio") }), "Bio saved.");

const passwordForm = document.getElementById("password-form");
if (passwordForm) {
  passwordForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const error = document.getElementById("password-error");
    error.hidden = true;
    try {
      await apiJson(`${base}/password`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current: isSelf ? field("p-current") : "",
          new: field("p-new"),
        }),
      });
      passwordForm.reset();
      note(isSelf ? "Password changed." : "Password reset.", false);
    } catch (failure) {
      error.textContent = failure.message;
      error.hidden = false;
    }
  });
}

const avatarInput = document.getElementById("avatar-input");
if (avatarInput) {
  avatarInput.addEventListener("change", async () => {
    if (!avatarInput.files.length) return;
    const data = new FormData();
    data.append("file", avatarInput.files[0]);
    try {
      const result = await api(`${base}/avatar`, { method: "POST", body: data });
      if (!result.ok) throw new Error("That image was not accepted.");
      note("Avatar updated.", false);
      setTimeout(() => window.location.reload(), 600);
    } catch (failure) {
      note(failure.message, true);
    }
  });
}

const inviteButton = document.getElementById("new-invite");
if (inviteButton) {
  inviteButton.addEventListener("click", async () => {
    try {
      const invite = await apiJson("/api/invites", { method: "POST" });
      const list = document.getElementById("invite-list");
      const item = document.createElement("li");
      const code = document.createElement("code");
      code.textContent = invite.code;
      const state = document.createElement("span");
      state.className = "invite-state invite-state--open";
      state.textContent = "open";
      item.appendChild(code);
      item.appendChild(state);
      const placeholder = list.querySelector("li.muted");
      if (placeholder) placeholder.remove();
      list.prepend(item);
    } catch (error) {
      note(error.message, true);
    }
  });
}

const dangerSignOut = document.getElementById("sign-out-danger");
if (dangerSignOut) dangerSignOut.addEventListener("click", window.MELE_API.signOut);
})();
