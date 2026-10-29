// Oráculo oculto de la tarea 004-catalogo. Uso: QWENGAME_DIR=/ruta node --test oraculo.test.js
import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import { join } from "node:path";
const DIR = process.env.QWENGAME_DIR ?? "/run/media/xaski/7c0ba586-7758-4419-b3de-f524b9c9a1fb/!GitHub/!Obsedium/QwenGame";
const imp = (r) => import(pathToFileURL(join(DIR, r)).href);
const cerca = (a, b, msg, tol = 1e-9) => assert.ok(Math.abs(a - b) <= tol, `${msg}: ${a} ≠ ${b}`);
const ESPERADO = JSON.parse(readFileSync(new URL("./esperado.json", import.meta.url), "utf8"));
const leer = () => JSON.parse(readFileSync(join(DIR, "datos/objetos.json"), "utf8"));
const grupo = (cat) => ESPERADO.filter((o) => o.categoria === cat);
const iguales = (cat) => {
  const real = leer().filter((o) => o.categoria === cat);
  assert.deepEqual(real, grupo(cat));
};

test("e01 chatarra", () => { const l = leer(); assert.equal(l.length >= 6, true); iguales("chatarra"); });
test("e02 componentes", () => { iguales("componente"); });
test("e03 estructurales", () => { iguales("estructural"); });
test("e04 biologicos y artefactos", () => {
  iguales("biologico"); iguales("artefacto");
  assert.deepEqual(leer(), ESPERADO); // orden y contenido exactos
});

test("e05 cargarCatalogo", async () => {
  const { cargarCatalogo } = await imp("src/sim/catalogo.js");
  const cat = cargarCatalogo(ESPERADO);
  assert.equal(Object.keys(cat).length, 23);
  assert.ok(Object.isFrozen(cat));
  assert.notEqual(cat.cable, ESPERADO[1], "copia, no la misma referencia");
  assert.throws(() => cargarCatalogo({}), { message: "catálogo inválido: no es una lista" });
  const base = ESPERADO[0];
  const con = (campo, v) => [{ ...base, id: "x", [campo]: v }];
  assert.throws(() => cargarCatalogo(con("ancho", 0)), { message: "objeto inválido: x: ancho" });
  assert.throws(() => cargarCatalogo(con("alto", 1.5)), { message: "objeto inválido: x: alto" });
  assert.throws(() => cargarCatalogo(con("peso", 0)), { message: "objeto inválido: x: peso" });
  assert.throws(() => cargarCatalogo(con("valor", -1)), { message: "objeto inválido: x: valor" });
  assert.throws(() => cargarCatalogo(con("categoria", "otra")), { message: "objeto inválido: x: categoria" });
  assert.throws(() => cargarCatalogo(con("recicla", null)), { message: "objeto inválido: x: recicla" });
  assert.throws(() => cargarCatalogo(con("desarme", 0)), { message: "objeto inválido: x: desarme" });
  assert.throws(() => cargarCatalogo(con("corte", 0)), { message: "objeto inválido: x: corte" });
  assert.throws(() => cargarCatalogo(con("nombre", "")), { message: "objeto inválido: x: nombre" });
  assert.throws(() => cargarCatalogo([{ ...base, id: "x" }, { ...base, id: "x" }]), { message: "objeto inválido: x: id repetido" });
});

test("e06 obtener y crearItem", async () => {
  const { cargarCatalogo, obtener, crearItem } = await imp("src/sim/catalogo.js");
  const cat = cargarCatalogo(ESPERADO);
  assert.equal(obtener(cat, "servomotor").valor, 35);
  assert.throws(() => obtener(cat, "nada"), { message: "objeto desconocido: nada" });
  assert.deepEqual(crearItem(cat, "placa_circuitos", 7), { uid: 7, id: "placa_circuitos", ancho: 2, alto: 1, peso: 0.5, valor: 30 });
});
