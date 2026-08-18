document.getElementById("h-conduc").onclick = () => {
  const k = +document.getElementById("h-k").value, A = +document.getElementById("h-a").value;
  const L = +document.getElementById("h-l").value, dt = +document.getElementById("h-dt").value;
  const R = L / (k * A);
  const Q = dt / R;
  document.getElementById("h-conduc-out").innerHTML = `
    <table class="out-table">
      <tr><td>Thermal resistance</td><td>${R.toFixed(4)} K/W</td></tr>
      <tr><td>Heat transfer Q</td><td>${Q.toFixed(1)} W</td></tr>
    </table>`;
};
document.getElementById("cv-conv").onclick = () => {
  const h = +document.getElementById("cv-h").value, A = +document.getElementById("cv-a").value;
  const dt = +document.getElementById("cv-dt").value;
  const Q = h * A * dt;
  document.getElementById("cv-conv-out").innerHTML =
    `Q = h·A·ΔT = <strong>${Q.toFixed(1)} W</strong>`;
};
