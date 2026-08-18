const CATS = {
  length: { m: 1, km: 1000, cm: 0.01, mm: 0.001, in: 0.0254, ft: 0.3048, mi: 1609.344, yd: 0.9144 },
  mass: { kg: 1, g: 0.001, mg: 1e-6, lb: 0.45359237, ton: 1000, slug: 14.5939 },
  pressure: { Pa: 1, kPa: 1000, MPa: 1e6, bar: 1e5, atm: 101325, psi: 6894.757, "kg/cm²": 98066.5, mmHg: 133.322 },
  energy: { J: 1, kJ: 1000, MJ: 1e6, cal: 4.184, kcal: 4184, BTU: 1055.056, "kWh": 3.6e6, "ft·lb": 1.35582 },
  power: { W: 1, kW: 1000, MW: 1e6, hp: 745.7, "BTU/hr": 0.293071, "kcal/hr": 1.163 },
  force: { N: 1, kN: 1000, kgf: 9.80665, lbf: 4.448222, dyne: 1e-5 },
  volume: { m3: 1, L: 0.001, mL: 1e-6, gal: 0.00378541, "ft3": 0.0283168, in3: 1.63871e-5 },
};
const catSel = document.getElementById("u-cat");
const fromSel = document.getElementById("u-from");
const toSel = document.getElementById("u-to");
Object.keys(CATS).forEach(c => catSel.add(new Option(c, c)));
function fill() {
  fromSel.innerHTML = ""; toSel.innerHTML = "";
  Object.keys(CATS[catSel.value]).forEach(u => {
    fromSel.add(new Option(u, u)); toSel.add(new Option(u, u));
  });
  toSel.value = Object.keys(CATS[catSel.value])[1];
}
catSel.onchange = fill;
document.getElementById("u-convert").onclick = () => {
  const v = Number(document.getElementById("u-value").value);
  const m = CATS[catSel.value];
  const out = v * m[fromSel.value] / m[toSel.value];
  document.getElementById("u-result").innerHTML = `${v} ${fromSel.value} = <strong>${out.toLocaleString(undefined, { maximumFractionDigits: 6 })} ${toSel.value}</strong>`;
};
fill();
