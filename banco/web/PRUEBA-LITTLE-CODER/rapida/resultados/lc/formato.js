function formatoCLP(n) {
  const signo = n < 0 ? "-" : "";
  return signo + "$" + String(Math.abs(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

module.exports = { formatoCLP };
