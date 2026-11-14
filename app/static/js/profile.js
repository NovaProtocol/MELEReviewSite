/* Profile: identity fields, password, avatar and invitations. */

/* Shared helpers come from app.js; this file stays inside its own scope so two
   page scripts can load together without redeclaring the same binding. */
(function () {
"use strict";


const { api, apiJson } = window.MELE_API;

function note(message, isError) {
  const node = document.getElementById("profile-note");
  if (!node) return;
  node.textContent = message;
  node.hidden = !message;
  node.className = isError ? "form-error" : "form-note";
  if (!isError && message) node.setAttribute("style", "color: var(--ui-success)");
}

function reloadWhenSaved() {
  window.location.reload();
}

document.addEventListener("DOMContentLoaded", () => {
  const usernameForm = document.getElementById("username-form");
  if (usernameForm) {
    usernameForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await apiJson("/api/auth/username", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: document.getElementById("p-username").value.trim() }),
        });
        note("Username saved.", false);
        setTimeout(reloadWhenSaved, 700);
      } catch (error) {
        note(error.message, true);
      }
    });
  }

  const emailForm = document.getElementById("email-form");
  if (emailForm) {
    emailForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await apiJson("/api/auth/email", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: document.getElementById("p-email").value.trim() }),
        });
        note("Email saved.", false);
      } catch (error) {
        note(error.message, true);
      }
    });
  }

  const bioForm = document.getElementById("bio-form");
  if (bioForm) {
    bioForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await apiJson("/api/auth/bio", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ bio: document.getElementById("p-bio").value }),
        });
        note("Bio saved.", false);
      } catch (error) {
        note(error.message, true);
      }
    });
  }

  const passwordForm = document.getElementById("password-form");
  if (passwordForm) {
    passwordForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const error = document.getElementById("password-error");
      error.hidden = true;
      try {
        await apiJson("/api/auth/password", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            current: document.getElementById("p-current").value,
            new: document.getElementById("p-new").value,
          }),
        });
        passwordForm.reset();
        note("Password changed.", false);
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
        const result = await api("/api/auth/avatar", { method: "POST", body: data });
        if (!result.ok) throw new Error("That image was not accepted.");
        note("Avatar updated.", false);
        setTimeout(reloadWhenSaved, 600);
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
});
})();
