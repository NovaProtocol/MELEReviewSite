document.getElementById("cycle-select").addEventListener("change", e => {
  location.href = "/calculators/thermo?cycle=" + e.target.value;
});
