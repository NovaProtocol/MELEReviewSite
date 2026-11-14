/* Sign in, register, and the sign-out button the status page carries. */

/* Shared helpers come from app.js; this file stays inside its own scope so two
   page scripts can load together without redeclaring the same binding. */
(function () {
"use strict";


const { apiJson, signOut } = window.MELE_API;

function showError(id, message) {
  const node = document.getElementById(id);
  if (!node) return;
  node.textContent = message;
  node.hidden = !message;
}

function busy(button, label, working) {
  if (!button) return;
  if (working) {
    button.dataset.label = button.textContent;
    button.textContent = label;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.label || button.textContent;
    button.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const loginForm = document.getElementById("login-form");
  if (loginForm) {
    loginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      showError("login-error", "");
      const identifier = document.getElementById("login-identifier").value.trim();
      const password = document.getElementById("login-password").value;
      if (!identifier || !password) {
        showError("login-error", "Enter your username or email and your password.");
        return;
      }
      const button = document.getElementById("login-submit");
      busy(button, "Signing in...", true);
      try {
        await apiJson("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ identifier, password }),
        });
        window.location.href = "/library";
      } catch (error) {
        busy(button, "", false);
        if (error.message === "banned" || error.message === "revoked") {
          window.location.href = "/status";
          return;
        }
        showError("login-error", error.message);
      }
    });
  }

  const registerForm = document.getElementById("register-form");
  if (registerForm) {
    registerForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      showError("register-error", "");
      const payload = {
        invite_code: document.getElementById("register-code").value.trim(),
        username: document.getElementById("register-username").value.trim(),
        email: document.getElementById("register-email").value.trim(),
        password: document.getElementById("register-password").value,
      };
      if (!payload.invite_code) {
        showError("register-error", "An invitation code is required.");
        return;
      }
      const button = document.getElementById("register-submit");
      busy(button, "Creating...", true);
      try {
        await apiJson("/api/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        window.location.href = "/library";
      } catch (error) {
        busy(button, "", false);
        showError("register-error", error.message);
      }
    });
  }

  const signOutButton = document.getElementById("sign-out");
  if (signOutButton && !signOutButton.dataset.bound) {
    signOutButton.dataset.bound = "1";
    signOutButton.addEventListener("click", signOut);
  }
});
})();
