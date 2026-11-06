function formatoCLP(n) {
  const s = String(n);
  const signo = s.startsWith("-") ? "-" : "";
  const cuerpo = s.replace(/^-/, "").replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return signo + "$" + cuerpo;
}

module.exports = { formatoCLP };
