function satP(T) { return 0.61094 * Math.exp(17.625 * T / (T + 243.04)); }
function dew(T, rh) { const a = 17.625, b = 243.04; const gamma = Math.log(rh / 100) + a * T / (b + T); return b * gamma / (a - gamma); }
document.getElementById("p-calc").onclick = () => {
  const T = +document.getElementById("p-t").value;
  const rh = +document.getElementById("p-rh").value;
  const P = +document.getElementById("p-p").value;
  const ps = satP(T);
  const w = 0.622 * ps / (P - ps);
  const dp = dew(T, rh);
  const w_actual = w * rh / 100;
  document.getElementById("p-result").innerHTML = `
    <table class="out-table">
      <tr><td>Saturation pressure</td><td>${ps.toFixed(3)} kPa</td></tr>
      <tr><td>Humidity ratio (sat)</td><td>${w.toFixed(4)} kg/kg</td></tr>
      <tr><td>Humidity ratio (actual)</td><td>${w_actual.toFixed(4)} kg/kg</td></tr>
      <tr><td>Dew point</td><td>${dp.toFixed(2)} °C</td></tr>
    </table>`;
};
document.getElementById("p-mix").onclick = () => {
  const [m1, T1] = document.getElementById("m1").value.split(",").map(Number);
  const [m2, T2] = document.getElementById("m2").value.split(",").map(Number);
  const T = (m1 * T1 + m2 * T2) / (m1 + m2);
  document.getElementById("p-mix-out").innerHTML =
    `Mixed temperature = <strong>${T.toFixed(2)} °C</strong> (mass-weighted)`;
};
