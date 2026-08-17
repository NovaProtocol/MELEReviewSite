const CYCLE_PARAMS = {
  carnot: ["T_high", "T_low", "P1", "r_exp"],
  otto: ["r", "T1", "P1", "T3"],
  diesel: ["r", "rc", "T1", "P1"],
  dual: ["r", "rc", "rp", "T1", "P1"],
  rankine: ["P_boiler", "P_cond", "T_turbine"],
  brayton: ["rp", "T1", "P1", "T3"],
  "vapor-compression": ["P_evap", "P_cond", "T_comp"],
};

const CYCLE_DEFAULTS = {
  carnot: { T_high: 600, T_low: 300, P1: 101325, r_exp: 2 },
  otto: { r: 8, T1: 300, P1: 101325 },
  diesel: { r: 18, rc: 2.5, T1: 300, P1: 101325 },
  dual: { r: 14, rc: 2.0, rp: 2.5, T1: 300, P1: 101325 },
  rankine: { P_boiler: 3000000, P_cond: 10000, T_turbine: 600 },
  brayton: { rp: 10, T1: 300, P1: 101325 },
  "vapor-compression": { P_evap: 200000, P_cond: 1000000, T_comp: 280 },
};

const PARAM_LABELS = {
  T_high: "Hot reservoir temp (K)", T_low: "Cold reservoir temp (K)", P1: "P1 (Pa)", r_exp: "Isothermal exp. ratio",
  r: "Compression ratio (r)", T1: "T1 (K)", T3: "T3 (K, heat add)",
  rc: "Cutoff ratio (rc)", rp: "Pressure ratio (rp)",
  P_boiler: "Boiler pressure (Pa)", P_cond: "Condenser pressure (Pa)", T_turbine: "Turbine inlet temp (K)",
  P_evap: "Evaporator pressure (Pa)", T_comp: "Compressor inlet temp (K)",
};

const CYCLE_STATES = {
  carnot: 4,
  otto: 4,
  diesel: 4,
  dual: 5,
  rankine: 4,
  brayton: 4,
  "vapor-compression": 4,
};

const STATE_PROPS = ["P", "T", "h", "s"];

const PROCESS_COLORS = {
  isothermal: "#d62828", isentropic: "#2563eb", isobaric: "#16a34a",
  isochoric: "#f59e0b", isenthalpic: "#7c3aed",
};
const PROPERTY_LABELS = {
  T: "Temperature (K)", P: "Pressure (Pa)", v: "Specific Volume (m\u00b3/kg)",
  h: "Enthalpy (J/kg)", s: "Entropy (J/kg\u00b7K)",
};

let showGrid = true;
let showTicks = true;
let lastPlotData = null;

function buildInputs() {
  const container = document.getElementById("params");
  const params = CYCLE_PARAMS[window.CYCLE_NAME] || [];
  const defaults = CYCLE_DEFAULTS[window.CYCLE_NAME] || {};
  container.innerHTML = params.map(p => `
    <div class="form-group">
      <label>${PARAM_LABELS[p] || p}</label>
      <input type="number" id="${p}" step="any" value="${defaults[p] ?? ""}" />
    </div>
  `).join("");
}

function buildManualInputs() {
  const container = document.getElementById("manual-inputs");
  const n = CYCLE_STATES[window.CYCLE_NAME] || 0;
  const rows = [];
  for (let i = 1; i <= n; i++) {
    const cells = STATE_PROPS.map(p => `
      <div class="state-cell">
        <label>${p}</label>
        <input type="number" step="any" id="s${i}_${p}" />
      </div>
    `).join("");
    rows.push(`<fieldset class="state-slot"><legend>State ${i}</legend><div class="state-grid">${cells}</div></fieldset>`);
  }
  container.innerHTML = rows.join("");
}

function getParams() {
  const params = {};
  for (const id of CYCLE_PARAMS[window.CYCLE_NAME] || []) {
    const el = document.getElementById(id);
    if (el && el.value) params[id] = parseFloat(el.value);
  }
  return params;
}

function getManualStates() {
  const n = CYCLE_STATES[window.CYCLE_NAME] || 0;
  const states = [];
  for (let i = 1; i <= n; i++) {
    const props = {};
    for (const p of STATE_PROPS) {
      const el = document.getElementById(`s${i}_${p}`);
      if (el && el.value) props[p] = parseFloat(el.value);
    }
    states.push(props);
  }
  return states;
}

function inputMode() {
  return document.getElementById("input-mode").value;
}

function setStatus(msg, error) {
  const el = document.getElementById("status");
  el.textContent = msg || "";
  el.classList.toggle("error", !!error);
}

function themeColors() {
  const cs = getComputedStyle(document.body);
  return {
    paper: cs.getPropertyValue("--graph-bg").trim() || "#0a0a0f",
    ink: cs.getPropertyValue("--graph-ink").trim() || "#eee",
    grid: cs.getPropertyValue("--graph-grid").trim() || "#333",
    accent: cs.getPropertyValue("--accent").trim() || "#ffd200",
    blue: cs.getPropertyValue("--blue").trim() || "#4d7cff",
  };
}

function renderPlot(pd, diagram) {
  lastPlotData = pd;
  const el = document.getElementById("diagram");
  const c = themeColors();
  const traces = [];
  if (pd.dome) {
    traces.push({ x: pd.dome.liquid_x, y: pd.dome.liquid_y, mode: "lines", line: { color: c.grid, width: 1.5 }, hoverinfo: "skip", showlegend: false });
    traces.push({ x: pd.dome.vapor_x, y: pd.dome.vapor_y, mode: "lines", line: { color: c.grid, width: 1.5 }, hoverinfo: "skip", showlegend: false });
    for (const q of pd.dome.quality) {
      traces.push({ x: q.x, y: q.y, mode: "lines", line: { color: c.grid, width: 1, dash: "dot" }, hoverinfo: "skip", showlegend: false });
    }
  }
  for (const seg of pd.segments) {
    traces.push({
      x: seg.x, y: seg.y, mode: "lines",
      name: seg.process,
      line: { color: PROCESS_COLORS[seg.process] || c.accent, width: 2 },
      hoverinfo: "name+x+y",
    });
  }
  traces.push({
    x: pd.states.map((s) => s.x), y: pd.states.map((s) => s.y),
    mode: "markers+text", text: pd.states.map((s) => s.label),
    textposition: "top center", textfont: { color: c.accent, size: 11 },
    marker: { color: c.accent, size: 8, line: { color: c.ink, width: 1 } }, hoverinfo: "skip", showlegend: false,
  });

  const layout = {
    paper_bgcolor: c.paper, plot_bgcolor: c.paper,
    font: { color: c.ink },
    margin: { l: 60, r: 20, t: 20, b: 45 },
    xaxis: {
      title: { text: PROPERTY_LABELS[diagram.x] || diagram.x },
      showgrid: showGrid, gridcolor: c.grid, zeroline: false,
      showticklabels: showTicks, tickcolor: c.grid,
    },
    yaxis: {
      title: { text: PROPERTY_LABELS[diagram.y] || diagram.y },
      showgrid: showGrid, gridcolor: c.grid, zeroline: false,
      showticklabels: showTicks, tickcolor: c.grid,
    },
    showlegend: false,
    dragmode: "pan",
  };
  Plotly.react(el, traces, layout, { responsive: true, displaylogo: false, scrollZoom: true });
}

function renderStateTable(states) {
  const tbody = document.querySelector("#state-table tbody");
  tbody.innerHTML = states.map((s, i) =>
    `<tr><td>${i + 1}</td><td>${s.P.toFixed(1)}</td><td>${s.T.toFixed(2)}</td><td>${s.h.toFixed(1)}</td><td>${s.s.toFixed(4)}</td><td>${s.v.toFixed(6)}</td></tr>`
  ).join("");
}

function backendToPlot(data, xAxis, yAxis) {
  const segments = (data.segments || []).map(seg => ({
    process: seg.process,
    x: seg.points.map(p => p[xAxis]),
    y: seg.points.map(p => p[yAxis]),
  }));
  const states = data.states.map(s => ({ x: s[xAxis], y: s[yAxis], label: String(s.point) }));
  return { segments, states, dome: data.dome || null };
}

async function calculate() {
  const body = {
    cycle: window.CYCLE_NAME,
    fluid: document.getElementById("fluid").value,
    format: "data",
    diagram: {
      x: document.getElementById("axis-x").value,
      y: document.getElementById("axis-y").value,
    },
  };
  if (inputMode() === "manual") {
    body.input_mode = "manual";
    body.states = getManualStates();
  } else {
    body.input_mode = "fluid";
    body.parameters = getParams();
  }

  const btn = document.getElementById("calc-btn");
  btn.disabled = true;
  btn.textContent = "Calculating...";
  try {
    const resp = await fetch("/api/cycle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json();

    if (data.solved) {
      const pd = backendToPlot(data, body.diagram.x, body.diagram.y);
      renderPlot(pd, body.diagram);
      renderStateTable(data.states);
      setStatus("", false);
    } else {
      Plotly.purge(document.getElementById("diagram"));
      document.querySelector("#state-table tbody").innerHTML = "";
      const reasons = (data.missing || []).map(m => PARAM_LABELS[m] || m).join(", ");
      setStatus("Enter the required inputs: " + reasons, true);
    }
  } catch (e) {
    console.error("calc error:", e);
    setStatus("Calculation failed. Check the server.", true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Calculate";
  }
}

function switchMode() {
  const manual = inputMode() === "manual";
  document.getElementById("fluid-inputs").classList.toggle("hidden", manual);
  document.getElementById("manual-inputs").classList.toggle("hidden", !manual);
}

document.addEventListener("DOMContentLoaded", () => {
  buildInputs();
  buildManualInputs();
  calculate();
  document.getElementById("input-mode").addEventListener("change", switchMode);
  document.getElementById("calc-btn").addEventListener("click", calculate);
  document.getElementById("toggle-grid").addEventListener("click", () => {
    showGrid = !showGrid;
    document.getElementById("toggle-grid").classList.toggle("active", showGrid);
    if (lastPlotData) renderPlot(lastPlotData, {
      x: document.getElementById("axis-x").value,
      y: document.getElementById("axis-y").value,
    });
  });
  document.getElementById("toggle-ticks").addEventListener("click", () => {
    showTicks = !showTicks;
    document.getElementById("toggle-ticks").classList.toggle("active", showTicks);
    if (lastPlotData) renderPlot(lastPlotData, {
      x: document.getElementById("axis-x").value,
      y: document.getElementById("axis-y").value,
    });
  });
  document.addEventListener("themeChanged", () => {
    if (lastPlotData) renderPlot(lastPlotData, {
      x: document.getElementById("axis-x").value,
      y: document.getElementById("axis-y").value,
    });
  });
});
