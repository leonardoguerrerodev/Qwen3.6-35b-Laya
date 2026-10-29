// Oráculo oculto de la tarea 003-mochila. Uso: QWENGAME_DIR=/ruta node --test oraculo.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import { join } from "node:path";
const DIR = process.env.QWENGAME_DIR ?? "/run/media/xaski/7c0ba586-7758-4419-b3de-f524b9c9a1fb/!GitHub/!Obsedium/QwenGame";
const imp = (r) => import(pathToFileURL(join(DIR, r)).href);
const cerca = (a, b, msg, tol = 1e-9) => assert.ok(Math.abs(a - b) <= tol, `${msg}: ${a} ≠ ${b}`);
const it = (uid, ancho, alto, peso = 1, valor = 10) => ({ uid, id: "i" + uid, ancho, alto, peso, valor });

test("e01 crearMochila", async () => {
  const { crearMochila } = await imp("src/sim/mochila.js");
  assert.deepEqual(crearMochila(5, 4, 25), { ancho: 5, alto: 4, pesoMax: 25, items: [] });
});

test("e02 peso, carga y valor", async () => {
  const { crearMochila, pesoTotal, carga, valorTotal } = await imp("src/sim/mochila.js");
  const v = crearMochila(5, 4, 25);
  assert.equal(pesoTotal(v), 0); assert.equal(carga(v), 0); assert.equal(valorTotal(v), 0);
  const m = { ...v, items: [{ ...it(1, 1, 1, 5, 10), x: 0, y: 0, rotado: false }, { ...it(2, 1, 2, 7.5, 20), x: 1, y: 0, rotado: false }] };
  cerca(pesoTotal(m), 12.5, "peso"); cerca(carga(m), 0.5, "carga"); assert.equal(valorTotal(m), 30);
});

test("e03 hayHueco", async () => {
  const { crearMochila, hayHueco } = await imp("src/sim/mochila.js");
  const v = crearMochila(5, 4, 25);
  assert.equal(hayHueco(v, 0, 0, 5, 4), true);
  assert.equal(hayHueco(v, 4, 0, 2, 1), false);
  assert.equal(hayHueco(v, -1, 0, 1, 1), false);
  assert.equal(hayHueco(v, 0, 3, 1, 2), false);
  const m = { ...v, items: [{ ...it(1, 2, 2), x: 0, y: 0, rotado: false }] };
  assert.equal(hayHueco(m, 0, 0, 1, 1), false);
  assert.equal(hayHueco(m, 1, 1, 1, 1), false);
  assert.equal(hayHueco(m, 2, 0, 1, 2), true); // toca el borde, no solapa
  assert.equal(hayHueco(m, 1, 2, 2, 2), true);
});

test("e04 colocar sin rotar", async () => {
  const { crearMochila, colocar } = await imp("src/sim/mochila.js");
  const v = crearMochila(3, 2, 100);
  const a = colocar(v, it(1, 2, 2));
  assert.equal(v.items.length, 0, "no muta");
  assert.deepEqual(a.items[0], { uid: 1, id: "i1", ancho: 2, alto: 2, peso: 1, valor: 10, x: 0, y: 0, rotado: false });
  const b = colocar(a, it(2, 1, 2));
  assert.equal(b.items[1].x, 2); assert.equal(b.items[1].y, 0);
  assert.equal(colocar(b, it(3, 1, 1)), null, "llena");
  const p = crearMochila(5, 5, 2);
  assert.equal(colocar(p, it(1, 1, 1, 3)), null, "peso");
  assert.notEqual(colocar(p, it(1, 1, 1, 2)), null, "peso justo cabe");
  const q = colocar(colocar(crearMochila(3, 3, 100), it(1, 3, 1)), it(2, 1, 1));
  assert.equal(q.items[1].y, 1, "recorre por filas");
});

test("e05 colocar rotando", async () => {
  const { crearMochila, colocar } = await imp("src/sim/mochila.js");
  const m = colocar(crearMochila(4, 1, 100), it(1, 1, 3));
  assert.equal(m.items[0].rotado, true); assert.equal(m.items[0].ancho, 3); assert.equal(m.items[0].alto, 1);
  assert.equal(colocar(crearMochila(2, 2, 100), it(1, 1, 3)), null);
  // prefiere sin rotar aunque más lejos: hueco sin rotar en fila 1 vs rotado en fila 0
  let g = crearMochila(3, 2, 100);
  g = colocar(g, it(1, 1, 1)); // x0 y0
  const r = colocar(g, it(2, 1, 2)); // sin rotar: x1,y0 (cabe 1x2)
  assert.equal(r.items[1].rotado, false); assert.equal(r.items[1].x, 1);
  const cuad = colocar(crearMochila(3, 3, 100), it(1, 2, 2));
  assert.equal(cuad.items[0].rotado, false);
});

test("e06 quitar", async () => {
  const { crearMochila, colocar, quitar } = await imp("src/sim/mochila.js");
  const m = colocar(colocar(crearMochila(3, 2, 100), it(1, 1, 1)), it(2, 1, 1));
  const q = quitar(m, 1);
  assert.deepEqual(q.items.map((i) => i.uid), [2]);
  assert.equal(m.items.length, 2, "no muta");
  assert.equal(quitar(m, 99), m);
});

test("e07 celdas", async () => {
  const { crearMochila, colocar, celdas, quitar } = await imp("src/sim/mochila.js");
  let m = colocar(colocar(crearMochila(3, 2, 100), it(1, 2, 2)), it(2, 1, 2));
  assert.deepEqual(celdas(m), [[1, 1, 2], [1, 1, 2]]);
  assert.deepEqual(celdas(quitar(m, 1)), [[null, null, 2], [null, null, 2]]);
  assert.deepEqual(celdas(crearMochila(2, 1, 5)), [[null, null]]);
});
