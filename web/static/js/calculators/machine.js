document.getElementById("g-gear").onclick = () => {
  const d1 = +document.getElementById("g-driver").value, d2 = +document.getElementById("g-driven").value;
  const rpm = +document.getElementById("g-rpm").value;
  const gr = d2 / d1;
  const out = rpm / gr;
  document.getElementById("g-gear-out").innerHTML = `
    <table class="out-table">
      <tr><td>Gear ratio</td><td>${gr.toFixed(3)} : 1</td></tr>
      <tr><td>Driven speed</td><td>${out.toFixed(1)} rpm</td></tr>
    </table>`;
};
document.getElementById("bt-belt").onclick = () => {
  const d1 = +document.getElementById("bt-d1").value, d2 = +document.getElementById("bt-d2").value;
  const rpm = +document.getElementById("bt-rpm").value;
  const v = Math.PI * d1 / 1000 * rpm / 60;
  const n2 = rpm * d1 / d2;
  document.getElementById("bt-belt-out").innerHTML = `
    <table class="out-table">
      <tr><td>Belt speed</td><td>${v.toFixed(2)} m/s</td></tr>
      <tr><td>Driven speed</td><td>${n2.toFixed(1)} rpm</td></tr>
    </table>`;
};
document.getElementById("pw-power").onclick = () => {
  const T = +document.getElementById("pw-t").value, rpm = +document.getElementById("pw-rpm").value;
  const kW = 2 * Math.PI * T * rpm / 60000;
  const hp = kW / 0.7457;
  document.getElementById("pw-power-out").innerHTML = `
    <table class="out-table">
      <tr><td>Power</td><td>${kW.toFixed(2)} kW (${hp.toFixed(2)} hp)</td></tr>
    </table>`;
};
