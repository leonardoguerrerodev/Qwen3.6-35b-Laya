const PRECIOS = require("./precios");
const { formatoCLP } = require("./formato");

// lineas: [{ id, cantidad }] — el id puede venir como número o como texto
function subtotal(lineas) {
  let total = 0;
  for (const l of lineas) {
    const p = PRECIOS.find((x) => String(x.id) === String(l.id));
    if (!p) throw new Error("producto desconocido: " + l.id);
    if (!Number.isInteger(l.cantidad) || l.cantidad < 1) throw new Error("cantidad inválida");
    total += p.precio * l.cantidad;
  }
  return total;
}

function desglose(total) {
  const neto = Math.round(total / 1.19);
  return { neto, iva: total - neto };
}

function boleta(lineas) {
  const t = subtotal(lineas);
  const { neto, iva } = desglose(t);
  return `Neto ${formatoCLP(neto)} · IVA ${formatoCLP(iva)} · Total ${formatoCLP(t)}`;
}

function dividirCuenta(total, n) {
  if (!Number.isInteger(n) || n < 1) throw new Error("n inválido");
  const base = Math.floor(total / n);
  const sobra = total - base * n;
  const montos = [];
  for (let i = 0; i < n; i++) montos.push(i < sobra ? base + 1 : base);
  return montos;
}

module.exports = { subtotal, desglose, boleta, dividirCuenta };
