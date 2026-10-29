// Oráculo oculto de la tarea 005-utilidades. Uso: QWENGAME_DIR=/ruta node --test oraculo.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import { join } from "node:path";
const DIR = process.env.QWENGAME_DIR ?? "/run/media/xaski/7c0ba586-7758-4419-b3de-f524b9c9a1fb/!GitHub/!Obsedium/QwenGame";
const imp = (r) => import(pathToFileURL(join(DIR, r)).href);
const cerca = (a, b, msg, tol = 1e-9) => assert.ok(Math.abs(a - b) <= tol, `${msg}: ${a} ≠ ${b}`);

test("e01 siguiente", async () => {
  const { crearRng, siguiente } = await imp("src/sim/rng.js");
  const r0 = crearRng(1);
  assert.deepEqual(r0, { estado: 1 });
  let r = r0; const v = [];
  for (let i = 0; i < 3; i++) { const s = siguiente(r); v.push(s.valor); r = s.rng; }
  assert.deepEqual(v, [0.6270739405881613, 0.002735721180215478, 0.5274470399599522]);
  assert.deepEqual(r, { estado: 1199730144 });
  assert.deepEqual(r0, { estado: 1 });
});

test("e02 entero", async () => {
  const { crearRng, entero } = await imp("src/sim/rng.js");
  let r = crearRng(42); const v = [];
  for (let i = 0; i < 5; i++) { const s = entero(r, 1, 6); v.push(s.valor); r = s.rng; }
  assert.deepEqual(v, [4, 3, 6, 5, 2]);
});

test("e04 crearEstatica y constante", async () => {
  const { ESTATICA, crearEstatica } = await imp("src/sim/estatica.js");
  assert.deepEqual(crearEstatica(), { valor: 0 });
  cerca(ESTATICA.pasivoPorSegundo, 1 / 6, "pasivo"); assert.deepEqual(ESTATICA.umbrales, [25, 50, 75, 100]);
});

test("e05 pasoEstatica", async () => {
  const { pasoEstatica } = await imp("src/sim/estatica.js");
  cerca(pasoEstatica({ valor: 0 }, 6, 0).valor, 1, "pasivo");
  cerca(pasoEstatica({ valor: 10 }, 1, 3).valor, 13 + 1 / 6, "ruido");
  assert.equal(pasoEstatica({ valor: 99 }, 1, 5).valor, 100);
  const e = { valor: 5 }; pasoEstatica(e, 1, 1); assert.equal(e.valor, 5);
});

test("e06 umbral y colapso", async () => {
  const { umbral, colapso } = await imp("src/sim/estatica.js");
  const u = [0, 24.9, 25, 49.9, 50, 75, 99.9, 100].map((valor) => umbral({ valor }));
  assert.deepEqual(u, [0, 0, 1, 1, 2, 3, 3, 4]);
  assert.equal(colapso({ valor: 99.9 }), false); assert.equal(colapso({ valor: 100 }), true);
});

test("e08 economia base", async () => {
  const e = await imp("src/sim/economia.js");
  assert.deepEqual(e.MOCHILAS, [{ ancho: 5, alto: 4, pesoMax: 25 }, { ancho: 6, alto: 5, pesoMax: 40 }]);
  assert.deepEqual(e.MEJORAS, { mochila_n2: { costo: 600 } });
  assert.deepEqual(e.crearEconomia(), { creditos: 0, bodega: [], mejoras: [] });
});

const eco = (extra = {}) => ({ creditos: 100, bodega: [{ uid: 1, valor: 30 }, { uid: 2, valor: 25 }, { uid: 3, valor: 5 }], mejoras: [], ...extra });

test("e09 vender", async () => {
  const { venderTodo, vender } = await imp("src/sim/economia.js");
  const base = eco();
  const r = venderTodo(base);
  assert.equal(r.total, 60); assert.equal(r.economia.creditos, 160); assert.deepEqual(r.economia.bodega, []);
  assert.equal(base.bodega.length, 3, "no muta");
  const v = vender(base, 2);
  assert.equal(v.creditos, 125); assert.deepEqual(v.bodega.map((i) => i.uid), [1, 3]);
  assert.equal(vender(base, 99), null);
});

test("e10 comprarMejora y mochilaDe", async () => {
  const { comprarMejora, mochilaDe, MOCHILAS } = await imp("src/sim/economia.js");
  assert.equal(comprarMejora(eco({ creditos: 599 }), "mochila_n2"), null);
  const c = comprarMejora(eco({ creditos: 600 }), "mochila_n2");
  assert.equal(c.creditos, 0); assert.deepEqual(c.mejoras, ["mochila_n2"]);
  assert.equal(comprarMejora(c, "mochila_n2"), null);
  assert.equal(comprarMejora(eco({ creditos: 900 }), "nada"), null);
  assert.equal(mochilaDe(eco()), MOCHILAS[0]); assert.equal(mochilaDe(c), MOCHILAS[1]);
  assert.deepEqual(eco().mejoras, []);
});
