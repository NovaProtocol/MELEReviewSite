document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("register-form").addEventListener("submit", async e => {
    e.preventDefault();
    document.getElementById("add-error").hidden = true;
    const res = await fetch("/api/auth/accounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: document.getElementById("new-name").value,
        pin: document.getElementById("new-pin").value,
      }),
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      document.getElementById("add-error").textContent = d.detail || "Could not create account";
      document.getElementById("add-error").hidden = false;
      return;
    }
    location.href = "/login";
  });
});
