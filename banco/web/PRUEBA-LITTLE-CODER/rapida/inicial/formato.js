function formatoCLP(n) {
  return "$" + String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

module.exports = { formatoCLP };
