const PRECIOS = require("./precios");
const { formatoCLP } = require("./formato");

// lineas: [{ id, cantidad }]
function subtotal(lineas) {
  let total = 0;
  for (const l of lineas) {
    const p = PRECIOS.find((x) => x.id === l.id);
    total += p.precio * l.cantidad;
  }
  return total;
}

function desglose(total) {
  const iva = Math.round(total * 0.19);
  return { neto: total - iva, iva };
}

function boleta(lineas) {
  const t = subtotal(lineas);
  const { neto, iva } = desglose(t);
  return `Neto ${formatoCLP(neto)} · IVA ${formatoCLP(iva)} · Total ${formatoCLP(t)}`;
}

module.exports = { subtotal, desglose, boleta };
