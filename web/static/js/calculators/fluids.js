function fric(f, Re, eps, D) {
  return 0.25 / Math.pow(Math.log10(eps / (3.7 * D) + 5.74 / Math.pow(Re, 0.9)), 2);
}
document.getElementById("f-calc").onclick = () => {
  const Q = +document.getElementById("f-q").value;
  const D = +document.getElementById("f-d").value;
  const rho = +document.getElementById("f-rho").value;
  const mu = +document.getElementById("f-mu").value;
  const L = +document.getElementById("f-l").value;
  const eps = +document.getElementById("f-eps").value;
  const eff = +document.getElementById("f-eff").value;

  const A = Math.PI * D * D / 4;
  const V = Q / A;
  const Re = rho * V * D / mu;
  const f = Re > 2000 ? fric(f, Re, eps, D) : 64 / Re;
  const hl = f * L / D * V * V / (2 * 9.81);
  const hpump = (hl + V * V / (2 * 9.81)) / eff;
  const P = rho * 9.81 * Q * hpump;

  document.getElementById("f-result").innerHTML = `
    <table class="out-table">
      <tr><td>Velocity</td><td>${V.toFixed(3)} m/s</td></tr>
      <tr><td>Reynolds number</td><td>${Re.toFixed(0)} (${Re < 2300 ? "laminar" : Re < 4000 ? "transition" : "turbulent"})</td></tr>
      <tr><td>Friction factor f</td><td>${f.toFixed(4)}</td></tr>
      <tr><td>Head loss</td><td>${hl.toFixed(3)} m</td></tr>
      <tr><td>Pump power</td><td>${P.toFixed(1)} W (${(P / 745.7).toFixed(3)} hp)</td></tr>
    </table>`;
};
