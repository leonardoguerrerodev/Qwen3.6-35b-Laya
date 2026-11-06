// oraculo.js <carpeta> — corrige el proyecto sin que el agente lo vea. Imprime JSON {ok, total, fallos}.
const path = require("path");
const dir = path.resolve(process.argv[2]);
const fallos = []; let ok = 0, total = 0;
function prueba(nombre, fn) {
  total++;
  try { if (fn() === true) ok++; else fallos.push(nombre); } catch (e) { fallos.push(`${nombre} (${e.message})`); }
}
const cargar = (f) => { try { return require(path.join(dir, f)); } catch (e) { fallos.push(`${f} no carga: ${e.message}`); return {}; } };
const c = cargar("carrito.js"), f = cargar("formato.js");
const lanza = (fn, txt) => { try { fn(); return false; } catch (e) { return e instanceof Error && e.message === txt; } };
const igual = (a, b) => JSON.stringify(a) === JSON.stringify(b);
prueba("subtotal ids número y texto", () => c.subtotal([{ id: 1, cantidad: 2 }, { id: "3", cantidad: 1 }]) === 9990);
prueba("subtotal vacío", () => c.subtotal([]) === 0);
prueba("subtotal id desconocido", () => lanza(() => c.subtotal([{ id: 9, cantidad: 1 }]), "producto desconocido: 9"));
prueba("subtotal cantidad 0", () => lanza(() => c.subtotal([{ id: 1, cantidad: 0 }]), "cantidad inválida"));
prueba("subtotal cantidad 1.5", () => lanza(() => c.subtotal([{ id: 1, cantidad: 1.5 }]), "cantidad inválida"));
prueba("desglose 11900", () => igual(c.desglose(11900), { neto: 10000, iva: 1900 }));
prueba("desglose 9990", () => igual(c.desglose(9990), { neto: 8395, iva: 1595 }));
prueba("desglose 0", () => igual(c.desglose(0), { neto: 0, iva: 0 }));
prueba("formatoCLP 0", () => f.formatoCLP(0) === "$0");
prueba("formatoCLP 999", () => f.formatoCLP(999) === "$999");
prueba("formatoCLP millones", () => f.formatoCLP(1234567) === "$1.234.567");
prueba("formatoCLP negativo", () => f.formatoCLP(-1500) === "-$1.500");
prueba("boleta", () => c.boleta([{ id: 2, cantidad: 1 }]) === "Neto $2.689 · IVA $511 · Total $3.200");
prueba("dividirCuenta 10000/3", () => igual(c.dividirCuenta(10000, 3), [3334, 3333, 3333]));
prueba("dividirCuenta exacta", () => igual(c.dividirCuenta(10, 5), [2, 2, 2, 2, 2]));
prueba("dividirCuenta 2/3", () => igual(c.dividirCuenta(2, 3), [1, 1, 0]));
prueba("dividirCuenta 10/4", () => igual(c.dividirCuenta(10, 4), [3, 3, 2, 2]));
prueba("dividirCuenta n 0", () => lanza(() => c.dividirCuenta(100, 0), "n inválido"));
prueba("dividirCuenta n 2.5", () => lanza(() => c.dividirCuenta(100, 2.5), "n inválido"));
console.log(JSON.stringify({ ok, total, fallos }));
