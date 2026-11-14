document.getElementById("s-axial").onclick = () => {
  const P = +document.getElementById("s-f").value, A = +document.getElementById("s-a").value;
  const L = +document.getElementById("s-l").value, E = +document.getElementById("s-e").value;
  const sigma = P / A;
  const strain = sigma / E / 1000;
  const dL = strain * L;
  document.getElementById("s-axial-out").innerHTML = `
    <table class="out-table">
      <tr><td>Stress σ</td><td>${sigma.toFixed(2)} MPa</td></tr>
      <tr><td>Strain ε</td><td>${strain.toExponential(3)}</td></tr>
      <tr><td>Elongation δ</td><td>${dL.toFixed(4)} mm</td></tr>
    </table>`;
};
document.getElementById("b-beam").onclick = () => {
  const L = +document.getElementById("b-l").value, P = +document.getElementById("b-p").value * 1000;
  const E = +document.getElementById("b-e").value * 1e9, I = +document.getElementById("b-i").value * 1e-6;
  const R = P / 2;
  const M = P * L / 4;
  const dmax = P * Math.pow(L, 3) / (48 * E * I);
  const theta = P * L * L / (16 * E * I);
  document.getElementById("b-beam-out").innerHTML = `
    <table class="out-table">
      <tr><td>Reaction each</td><td>${(R / 1000).toFixed(1)} kN</td></tr>
      <tr><td>Max moment M = PL/4</td><td>${(M / 1000).toFixed(1)} kN·m</td></tr>
      <tr><td>Max deflection</td><td>${(dmax * 1000).toFixed(2)} mm</td></tr>
      <tr><td>End slope</td><td>${theta.toExponential(3)} rad</td></tr>
    </table>`;
};
document.getElementById("t-torsion").onclick = () => {
  const T = +document.getElementById("t-t").value, d = +document.getElementById("t-d").value;
  const L = +document.getElementById("t-l").value, G = +document.getElementById("t-g").value * 1e9;
  const J = Math.PI * Math.pow(d, 4) / 32;
  const tau = T * 1000 * (d / 2) / J;
  const theta = T * L / (G * J * 1e-12);
  document.getElementById("t-torsion-out").innerHTML = `
    <table class="out-table">
      <tr><td>Shear stress τ</td><td>${tau.toFixed(2)} MPa</td></tr>
      <tr><td>Angle of twist</td><td>${(theta * 180 / Math.PI).toFixed(4)}° (${theta.toExponential(3)} rad)</td></tr>
      <tr><td>Polar moment J</td><td>${J.toExponential(3)} mm⁴</td></tr>
    </table>`;
};
