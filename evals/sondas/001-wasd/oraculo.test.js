// Oráculo oculto de la tarea 001-wasd (Qwen no lo ve).
// Uso: QWENGAME_DIR=/ruta/al/proyecto node --test oraculo.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { join } from "node:path";

const DIR = process.env.QWENGAME_DIR
  ?? "/run/media/xaski/7c0ba586-7758-4419-b3de-f524b9c9a1fb/!GitHub/!Obsedium/QwenGame";
const RUTA = join(DIR, "src/mundo.js");
const m = await import(pathToFileURL(RUTA).href);

const MAPA = [
  "#####",
  "#.\"~#",
  "#.@.#",
  "#####",
].join("\n");

test("crearMundo: dimensiones, celdas y jugador", () => {
  const w = m.crearMundo(MAPA);
  assert.equal(w.ancho, 5);
  assert.equal(w.alto, 4);
  assert.deepEqual(w.jugador, { x: 2, y: 2 });
  assert.equal(w.celdas[2][2], ".");
  assert.equal(w.celdas[1][3], "~");
  assert.equal(w.celdas[0][0], "#");
  assert.ok(Array.isArray(w.celdas[0]));
});

test("crearMundo: sin @ lanza el error exacto", () => {
  assert.throws(() => m.crearMundo("###\n#.#\n###"), { message: "El mapa no tiene @" });
});

test("esCaminable: tipos de celda y fuera del mapa", () => {
  const w = m.crearMundo(MAPA);
  assert.equal(m.esCaminable(w, 1, 1), true);   // .
  assert.equal(m.esCaminable(w, 2, 1), true);   // "
  assert.equal(m.esCaminable(w, 2, 2), true);   // donde estaba @
  assert.equal(m.esCaminable(w, 3, 1), false);  // ~
  assert.equal(m.esCaminable(w, 0, 0), false);  // #
  for (const [x, y] of [[-1, 1], [1, -1], [5, 1], [1, 4]]) {
    assert.equal(m.esCaminable(w, x, y), false, `(${x},${y})`);
  }
});

test("mover: las cuatro direcciones", () => {
  const w = m.crearMundo(MAPA);
  assert.equal(m.mover(w, "izquierda"), true);
  assert.deepEqual(w.jugador, { x: 1, y: 2 });
  assert.equal(m.mover(w, "arriba"), true);
  assert.deepEqual(w.jugador, { x: 1, y: 1 });
  assert.equal(m.mover(w, "derecha"), true);   // al pasto alto
  assert.deepEqual(w.jugador, { x: 2, y: 1 });
  assert.equal(m.mover(w, "abajo"), true);
  assert.deepEqual(w.jugador, { x: 2, y: 2 });
});

test("mover: muro, agua y dirección desconocida no cambian nada", () => {
  const w = m.crearMundo(MAPA);
  assert.equal(m.mover(w, "abajo"), false);    // muro
  assert.deepEqual(w.jugador, { x: 2, y: 2 });
  m.mover(w, "derecha");                       // (3,2)
  assert.equal(m.mover(w, "arriba"), false);   // agua en (3,1)
  assert.deepEqual(w.jugador, { x: 3, y: 2 });
  assert.equal(m.mover(w, "diagonal"), false);
  assert.deepEqual(w.jugador, { x: 3, y: 2 });
});

test("TECLAS: minúsculas y mayúsculas", () => {
  const esperado = { w: "arriba", s: "abajo", a: "izquierda", d: "derecha" };
  for (const [k, v] of Object.entries(esperado)) {
    assert.equal(m.TECLAS[k], v);
    assert.equal(m.TECLAS[k.toUpperCase()], v);
  }
});

test("mundo.js no toca el DOM", () => {
  const src = readFileSync(RUTA, "utf8");
  assert.doesNotMatch(src, /\b(window|document)\b/);
});

test("existen los archivos de la tarea", () => {
  for (const f of ["index.html", "src/render.js", "src/main.js", "test/mundo.test.js"]) {
    assert.ok(existsSync(join(DIR, f)), f);
  }
  const html = readFileSync(join(DIR, "index.html"), "utf8");
  assert.match(html, /id=["']juego["']/);
  assert.match(html, /type=["']module["']/);
  const render = readFileSync(join(DIR, "src/render.js"), "utf8");
  assert.match(render, /export\s+(function\s+dibujar|\{[^}]*\bdibujar\b)/);
});
