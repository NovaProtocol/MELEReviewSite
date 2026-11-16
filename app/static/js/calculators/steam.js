/* Steam tables: a state from any two inputs, the saturation table, and the point
   drawn on the dome. The numbers come from the server, which has CoolProp; this
   file only asks, formats and draws. */
(function () {
"use strict";

const API = "/api/tools/steam";

function num(value, digits) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const size = Math.abs(value);
  if (size !== 0 && (size < 0.001 || size >= 10000)) return value.toExponential(3);
  let text = value.toFixed(digits === undefined ? 4 : digits);
  // Trailing zeros are only noise after a decimal point: "100" must stay "100".
  if (text.includes(".")) text = text.replace(/0+$/, "").replace(/\.$/, "");
  return text;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function getJson(path) {
  const response = await fetch(path, { credentials: "include" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error((body.error && body.error.message) || "That did not work");
  return body;
}

async function postJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error((body.error && body.error.message) || "That did not work");
  return body;
}

/* ---- state ---- */
const RESULT_ROWS = [
  ["P", "MPa", 4],
  ["T", "°C", 2],
  ["v", "m³/kg", 6],
  ["u", "kJ/kg", 1],
  ["h", "kJ/kg", 1],
  ["s", "kJ/kg·K", 4],
  ["x", "quality", 3],
];

function showResult(state) {
  const host = document.getElementById("s-result");
  host.innerHTML = "";
  host.hidden = false;

  const phase = el("p", "steam-phase", state.phase || "");
  host.appendChild(phase);

  const grid = el("div", "steam-grid");
  for (const [key, unit, digits] of RESULT_ROWS) {
    if (state[key] === undefined || state[key] === null) continue;
    grid.appendChild(el("span", "steam-grid__key", `${key} (${unit})`));
    grid.appendChild(el("span", "steam-grid__value", num(state[key], digits)));
  }
  host.appendChild(grid);
}

/* ---- chart ---- */
const CHARTS = {
  "t-s": { x: "s", y: "T", xLabel: "s (kJ/kg·K)", yLabel: "T (°C)", logY: false },
  "h-s": { x: "s", y: "h", xLabel: "s (kJ/kg·K)", yLabel: "h (kJ/kg)", logY: false },
  "p-h": { x: "h", y: "P", xLabel: "h (kJ/kg)", yLabel: "P (MPa)", logY: true },
};

let dome = null;
let lastPoint = null;

function drawChart(point) {
  const svg = document.getElementById("s-svg");
  const kind = document.getElementById("s-chart-kind").value;
  const spec = CHARTS[kind];
  const width = 320;
  const height = 230;
  const pad = { left: 40, right: 10, top: 12, bottom: 28 };
  svg.innerHTML = "";
  if (!dome || !dome[kind]) return;

  const series = dome[kind];
  const xs = series.liquid_x.concat(series.vapour_x, [point.x]);
  const ys = series.liquid_y.concat(series.vapour_y, [point.y]);
  const transform = (value) => (spec.logY ? Math.log10(Math.max(value, 1e-6)) : value);

  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(...ys.map(transform));
  const yMax = Math.max(...ys.map(transform));

  const px = (value) =>
    pad.left + ((value - xMin) / (xMax - xMin || 1)) * (width - pad.left - pad.right);
  const py = (value) =>
    height - pad.bottom - ((transform(value) - yMin) / (yMax - yMin || 1)) * (height - pad.top - pad.bottom);

  const ns = "http://www.w3.org/2000/svg";
  function node(tag, attrs) {
    const element = document.createElementNS(ns, tag);
    for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
    return element;
  }

  // Frame and ticks
  svg.appendChild(
    node("rect", {
      x: pad.left, y: pad.top, width: width - pad.left - pad.right,
      height: height - pad.top - pad.bottom, fill: "none",
      stroke: "currentColor", "stroke-opacity": "0.25",
    })
  );
  for (let i = 0; i <= 4; i += 1) {
    const xv = xMin + ((xMax - xMin) * i) / 4;
    const yv = yMin + ((yMax - yMin) * i) / 4;
    const horizontal = node("line", {
      x1: pad.left, y1: py(spec.logY ? 10 ** yv : yv),
      x2: width - pad.right, y2: py(spec.logY ? 10 ** yv : yv),
      stroke: "currentColor", "stroke-opacity": "0.08",
    });
    svg.appendChild(horizontal);
    const label = node("text", {
      x: width - pad.right, y: py(spec.logY ? 10 ** yv : yv) - 2,
      "text-anchor": "end", "font-size": "7", fill: "currentColor", "fill-opacity": "0.6",
    });
    label.textContent = num(spec.logY ? 10 ** yv : yv, spec.logY ? 4 : 0);
    svg.appendChild(label);

    const tick = node("text", {
      x: px(xv), y: height - pad.bottom + 10, "text-anchor": "middle",
      "font-size": "7", fill: "currentColor", "fill-opacity": "0.6",
    });
    tick.textContent = num(xv, 0);
    svg.appendChild(tick);
  }

  function polyline(list, xKey, yKey) {
    const points = list[xKey].map((value, index) => `${px(value)},${py(list[yKey][index])}`);
    svg.appendChild(
      node("polyline", {
        points: points.join(" "), fill: "none", stroke: "currentColor",
        "stroke-width": "1.2", "stroke-opacity": "0.55",
      })
    );
  }
  polyline(series, "liquid_x", "liquid_y");
  polyline(series, "vapour_x", "vapour_y");

  // The point, and guides to the axes so it can be read off.
  const cx = px(point.x);
  const cy = py(point.y);
  svg.appendChild(node("line", {
    x1: pad.left, y1: cy, x2: cx, y2: cy,
    stroke: "var(--ui-primary, #2f9e8f)", "stroke-dasharray": "3 3", "stroke-width": "0.8",
  }));
  svg.appendChild(node("line", {
    x1: cx, y1: cy, x2: cx, y2: height - pad.bottom,
    stroke: "var(--ui-primary, #2f9e8f)", "stroke-dasharray": "3 3", "stroke-width": "0.8",
  }));
  svg.appendChild(node("circle", {
    cx, cy, r: "3.4", fill: "var(--ui-primary, #2f9e8f)", stroke: "white", "stroke-width": "1",
  }));

  const xLabel = node("text", {
    x: (pad.left + width - pad.right) / 2, y: height - 6, "text-anchor": "middle",
    "font-size": "8", fill: "currentColor", "fill-opacity": "0.75",
  });
  xLabel.textContent = spec.xLabel;
  svg.appendChild(xLabel);

  const yLabel = node("text", {
    x: 10, y: pad.top + 4, "font-size": "8", fill: "currentColor", "fill-opacity": "0.75",
  });
  yLabel.textContent = spec.yLabel;
  svg.appendChild(yLabel);
}

/* ---- table ---- */
const COLUMNS = [
  ["T_sat", "T °C", 2],
  ["P_sat", "P MPa", 4],
  ["v_f", "vf", 6],
  ["v_g", "vg", 4],
  ["u_f", "uf", 1],
  ["u_g", "ug", 1],
  ["h_f", "hf", 1],
  ["h_fg", "hfg", 1],
  ["h_g", "hg", 1],
  ["s_f", "sf", 4],
  ["s_g", "sg", 4],
];

function showTable(rows, basis) {
  const table = document.getElementById("t-table");
  table.innerHTML = "";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const [, label] of COLUMNS) headRow.appendChild(el("th", null, label));
  head.appendChild(headRow);
  table.appendChild(head);

  const body = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const [key, , digits] of COLUMNS) tr.appendChild(el("td", null, num(row[key], digits)));
    body.appendChild(tr);
  }
  table.appendChild(body);
  document.getElementById("t-wrap").hidden = false;
  document.getElementById("t-basis").dataset.basis = basis;
}

/* ---- wiring ---- */
function syncMode() {
  const mode = document.getElementById("s-mode").value;
  for (const field of document.querySelectorAll('[data-for="p"], [data-for="t"], [data-for="x"]')) {
    const key = field.dataset.for;
    const needed =
      (mode === "pt" && (key === "p" || key === "t")) ||
      (mode === "px" && (key === "p" || key === "x")) ||
      (mode === "tx" && (key === "t" || key === "x"));
    field.hidden = !needed;
  }
}

function syncRangeLabels() {
  const basis = document.getElementById("t-basis").value;
  const start = document.getElementById("t-start");
  const stop = document.getElementById("t-stop");
  const temperature = basis === "temperature";
  start.closest(".steam-input").querySelector("label").textContent = temperature
    ? "From °C"
    : "From MPa";
  stop.closest(".steam-input").querySelector("label").textContent = temperature
    ? "To °C"
    : "To MPa";
  // Water and the refrigerants live in different ranges, so the defaults follow
  // the fluid rather than making the user discover the critical point by error.
  const isWater = document.getElementById("s-fluid").value === "Water";
  if (temperature) {
    start.value = isWater ? "0" : "-30";
    stop.value = isWater ? "100" : "40";
  } else {
    start.value = isWater ? "0.001" : "0.1";
    stop.value = isWater ? "0.1" : "2";
  }
}

function fluid() {
  const node = document.getElementById("s-fluid");
  return node ? node.value : "Water";
}

async function solve() {
  const mode = document.getElementById("s-mode").value;
  const error = document.getElementById("s-error");
  error.hidden = true;
  const payload = { fluid: fluid() };
  if (mode === "pt") {
    payload.pressure = Number(document.getElementById("s-p").value);
    payload.temperature = Number(document.getElementById("s-t").value);
  } else if (mode === "px") {
    payload.pressure = Number(document.getElementById("s-p").value);
    payload.quality = Number(document.getElementById("s-x").value);
  } else {
    payload.temperature = Number(document.getElementById("s-t").value);
    payload.quality = Number(document.getElementById("s-x").value);
  }

  try {
    const result = await postJson(`${API}/state`, payload);
    showResult(result.state);
    if (!dome) dome = (await getJson(`${API}/dome?fluid=${encodeURIComponent(fluid())}`)).dome;
    lastPoint = result.charts[document.getElementById("s-chart-kind").value];
    document.getElementById("s-chart").hidden = false;
    drawChart(lastPoint);
  } catch (failure) {
    document.getElementById("s-result").hidden = true;
    document.getElementById("s-chart").hidden = true;
    error.textContent = failure.message;
    error.hidden = false;
  }
}

async function buildTable() {
  const basis = document.getElementById("t-basis").value;
  const error = document.getElementById("t-error");
  error.hidden = true;
  const start = Number(document.getElementById("t-start").value);
  const stop = Number(document.getElementById("t-stop").value);
  const count = Number(document.getElementById("t-count").value);
  const query = new URLSearchParams({ basis, start, stop, count, fluid: fluid() });
  try {
    const result = await getJson(`${API}/table?${query}`);
    showTable(result.rows, basis);
    const notes = [];
    if (result.clamped) notes.push("Started at the triple point, the lowest saturated state.");
    if (result.truncated) {
      notes.push("Stopped at the critical point: above it there is no liquid and vapour to list.");
    }
    const note = document.getElementById("t-note");
    note.textContent = notes.join(" ");
    note.hidden = notes.length === 0;
  } catch (failure) {
    document.getElementById("t-wrap").hidden = true;
    error.textContent = failure.message;
    error.hidden = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  for (const tab of document.querySelectorAll(".steam-tab")) {
    tab.addEventListener("click", () => {
      for (const other of document.querySelectorAll(".steam-tab")) {
        other.classList.toggle("is-active", other === tab);
      }
      for (const panel of document.querySelectorAll("[data-panel]")) {
        panel.hidden = panel.dataset.panel !== tab.dataset.tab;
      }
      if (tab.dataset.tab === "tables" && document.getElementById("t-wrap").hidden) {
        buildTable();
      }
    });
  }

  document.getElementById("s-mode").addEventListener("change", syncMode);
  document.getElementById("s-fluid").addEventListener("change", () => {
    // A new fluid has a new dome, and whichever range was on screen may not exist
    // for it: start from the defaults it does have.
    dome = null;
    lastPoint = null;
    document.getElementById("s-result").hidden = true;
    document.getElementById("s-chart").hidden = true;
    document.getElementById("t-wrap").hidden = true;
    syncRangeLabels();
  });
  document.getElementById("s-solve").addEventListener("click", solve);
  document.getElementById("t-build").addEventListener("click", buildTable);
  document.getElementById("t-basis").addEventListener("change", syncRangeLabels);
  // The point is kept in each pair's coordinates, so changing the axes redraws
  // without asking the server again.
  document.getElementById("s-chart-kind").addEventListener("change", () => {
    if (!dome || document.getElementById("s-result").hidden) return;
    solve();
  });

  syncMode();
  syncRangeLabels();
});
})();
