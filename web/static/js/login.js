let selected = null;

async function loadAccounts() {
  const res = await fetch("/api/auth/accounts");
  const accounts = await res.json();
  const grid = document.getElementById("account-grid");
  grid.innerHTML = "";
  document.getElementById("empty-state").hidden = accounts.length > 0;
  for (const a of accounts) {
    const card = document.createElement("div");
    card.className = "account-card";
    card.innerHTML = `<span class="avatar">${a.name[0].toUpperCase()}</span><span class="aname">${escapeHtml(a.name)}</span>`;
    card.onclick = () => openPin(a);
    grid.appendChild(card);
  }
}

function openPin(a) {
  selected = a;
  document.getElementById("pin-account-name").textContent = a.name;
  document.getElementById("pin-error").hidden = true;
  document.getElementById("pin-input").value = "";
  document.getElementById("pin-overlay").hidden = false;
  document.getElementById("pin-input").focus();
}

async function submitPin() {
  const pin = document.getElementById("pin-input").value;
  const res = await fetch("/api/auth/login", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account_id: selected.id, pin }),
  });
  if (res.ok) {
    location.href = "/questions";
  } else {
    document.getElementById("pin-error").hidden = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadAccounts();
  document.getElementById("pin-submit").onclick = submitPin;
  document.getElementById("pin-cancel").onclick = () => { document.getElementById("pin-overlay").hidden = true; };
  document.getElementById("pin-input").addEventListener("keydown", e => { if (e.key === "Enter") submitPin(); });
});
