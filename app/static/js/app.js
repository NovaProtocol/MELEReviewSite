/* Shared behaviour: the tool rail, and a fetch wrapper that carries the CSRF token. */

const CSRF_COOKIE = "melereview_csrf";

function readCookie(name) {
  const prefix = name + "=";
  for (const part of document.cookie.split(";")) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) return decodeURIComponent(trimmed.slice(prefix.length));
  }
  return null;
}

function csrf() {
  return (window.MELE && window.MELE.csrf) || readCookie(CSRF_COOKIE) || "";
}

async function api(path, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  const method = (options.method || "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD") headers["X-CSRF-Token"] = csrf();
  const response = await fetch(path, Object.assign({}, options, { headers, credentials: "include" }));
  if (response.status === 401 && !path.startsWith("/api/auth/login")) {
    window.location.href = "/";
    throw new Error("signed out");
  }
  return response;
}

async function apiJson(path, options = {}) {
  const response = await api(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = (body.error && body.error.message) || body.detail || "Something went wrong";
    throw new Error(detail);
  }
  return body;
}

function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (character) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]
  ));
}

async function signOut() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } finally {
    window.location.href = "/";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const signOutButton = document.getElementById("sign-out");
  if (signOutButton) signOutButton.addEventListener("click", signOut);

  const rail = document.getElementById("tools-rail");
  const backdrop = document.getElementById("rail-backdrop");
  const toggle = document.getElementById("rail-toggle");
  const close = document.getElementById("rail-close");
  const list = document.getElementById("rail-list");
  const search = document.getElementById("rail-search");
  const frameWrap = document.getElementById("rail-frame-wrap");
  const frame = document.getElementById("rail-frame");
  const frameTitle = document.getElementById("rail-frame-title");
  const frameClose = document.getElementById("rail-frame-close");
  const shell = document.getElementById("app-shell");

  if (!rail || !list) return;

  let tools = [];
  let activeSlug = null;

  try {
    tools = JSON.parse(document.querySelector('meta[name="mele-tools"]')?.content || "[]");
  } catch (error) {
    tools = [];
  }

  function openRail() {
    rail.classList.add("is-open");
    if (backdrop) backdrop.hidden = false;
    if (shell) shell.classList.add("rail-open");
    if (toggle) toggle.setAttribute("aria-expanded", "true");
  }

  function closeRail() {
    rail.classList.remove("is-open");
    if (backdrop) backdrop.hidden = true;
    if (shell) shell.classList.remove("rail-open");
    if (toggle) toggle.setAttribute("aria-expanded", "false");
  }

  function renderList() {
    const term = (search?.value || "").trim().toLowerCase();
    const matches = tools.filter((tool) => {
      if (!term) return true;
      return (tool.name + " " + tool.keywords + " " + tool.group).toLowerCase().includes(term);
    });
    list.innerHTML = "";
    if (!matches.length) {
      const empty = document.createElement("li");
      empty.className = "rail-none";
      empty.textContent = "Nothing matches that.";
      list.appendChild(empty);
      return;
    }
    let group = null;
    for (const tool of matches) {
      if (tool.group !== group) {
        group = tool.group;
        const heading = document.createElement("li");
        heading.className = "rail-group";
        heading.textContent = group;
        list.appendChild(heading);
      }
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = tool.name;
      button.className = tool.slug === activeSlug ? "is-active" : "";
      button.addEventListener("click", () => openTool(tool));
      item.appendChild(button);
      list.appendChild(item);
    }
  }

  function openTool(tool) {
    activeSlug = tool.slug;
    frame.src = "/tools/" + tool.slug;
    frameTitle.textContent = tool.name;
    frameWrap.hidden = false;
    rail.classList.add("has-tool");
    renderList();
    openRail();
  }

  if (search) search.addEventListener("input", renderList);
  if (toggle) toggle.addEventListener("click", () => {
    if (rail.classList.contains("is-open")) closeRail();
    else openRail();
  });
  if (close) close.addEventListener("click", closeRail);
  if (backdrop) backdrop.addEventListener("click", closeRail);
  if (frameClose) frameClose.addEventListener("click", () => {
    frameWrap.hidden = true;
    frame.src = "about:blank";
    rail.classList.remove("has-tool");
    activeSlug = null;
    renderList();
    if (search) search.focus();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && rail.classList.contains("is-open")) closeRail();
  });

  renderList();
});

// The same symbol set the templates use, so JS-built controls match.
function icon(name, className) {
  return `<svg class="icon${className ? ` ${className}` : ""}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
}

/* Any page with `.tab[data-tab]` and `.tab-panel[data-panel]` gets tabs. The
   panels are all in the document, so switching costs no request. */
function wireTabs() {
  const tabs = [...document.querySelectorAll(".tab[data-tab]")];
  if (!tabs.length) return;

  /* Each panel is its own scroll window, and the place you were reading is kept
     per panel: answering a problem must not lose your place in the notes. */
  const places = new Map();
  const panels = [...document.querySelectorAll(".tab-panel[data-panel]")];

  function activePanel() {
    return panels.find((panel) => panel.classList.contains("is-active")) || null;
  }

  for (const panel of panels) {
    panel.addEventListener("scroll", () => {
      places.set(panel.dataset.scrollKey || panel.dataset.panel, panel.scrollTop);
    });
  }

  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      const leaving = activePanel();
      if (leaving) places.set(leaving.dataset.scrollKey || leaving.dataset.panel, leaving.scrollTop);
      for (const other of tabs) {
        const active = other === tab;
        other.classList.toggle("is-active", active);
        other.setAttribute("aria-selected", active ? "true" : "false");
      }
      for (const panel of panels) {
        panel.classList.toggle("is-active", panel.dataset.panel === tab.dataset.tab);
      }
      const entering = activePanel();
      if (entering) {
        const saved = places.get(entering.dataset.scrollKey || entering.dataset.panel) || 0;
        entering.scrollTop = saved;
      }
    });
  }
}

document.addEventListener("DOMContentLoaded", wireTabs);

window.MELE_API = { api, apiJson, escapeHtml, signOut, csrf, icon };
window.MELE_ICON = icon;

/* The library strip swaps between two lists without a page load. */
document.addEventListener("DOMContentLoaded", () => {
  const tabs = document.querySelectorAll(".strip__tab");
  if (!tabs.length) return;
  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      for (const other of tabs) other.classList.remove("is-active");
      tab.classList.add("is-active");
      for (const panel of document.querySelectorAll("[data-strip-panel]")) {
        panel.hidden = panel.dataset.stripPanel !== tab.dataset.strip;
      }
    });
  }
});
