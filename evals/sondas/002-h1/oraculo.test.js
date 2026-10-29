// Oráculo oculto de la tarea 002-h1 (Qwen no lo ve). Cada test se llama eNN = etapa que verifica.
// Uso: QWENGAME_DIR=/ruta/al/proyecto node --test oraculo.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { join } from "node:path";

const DIR = process.env.QWENGAME_DIR
  ?? "/run/media/xaski/7c0ba586-7758-4419-b3de-f524b9c9a1fb/!GitHub/!Obsedium/QwenGame";
const imp = (r) => import(pathToFileURL(join(DIR, r)).href);
const cerca = (a, b, msg, tol = 1e-9) => assert.ok(Math.abs(a - b) <= tol, `${msg}: ${a} ≠ ${b}`);

const M20 = (() => {
  const f = [];
  for (let y = 0; y < 20; y++) {
    let s = "";
    for (let x = 0; x < 20; x++) s += y === 0 || y === 19 || x === 0 || x === 19 ? "#" : x === 10 && y === 10 ? "@" : ".";
    f.push(s);
  }
  return f.join("\n") + "\n";
})();
const M7 = ["#######", "#.....#", "#..#..#", "#.@...#", "#######"].join("\n");

test("e01 constantes", async () => {
  const c = await imp("src/sim/constantes.js");
  assert.equal(c.TICK_HZ, 30); cerca(c.DT, 1 / 30, "DT");
  assert.equal(c.VEL_MAX, 5); assert.equal(c.ACEL, 40); assert.equal(c.FRENO, 50); assert.equal(c.FACTOR_ATRAS, 0.85);
  assert.deepEqual(c.CAJA, { ancho: 0.6, alto: 0.4 }); assert.equal(c.MARGEN, 0.001);
  assert.deepEqual(c.RODAR, { duracion: 0.35, distancia: 3, invDesde: 0.1, invHasta: 0.7, costo: 25 });
  assert.deepEqual(c.ENERGIA, { max: 100, regen: 20, pausa: 0.8 });
  assert.equal(c.CAMARA_SUAVIDAD, 8); assert.equal(c.MAX_PASOS_POR_FRAME, 5);
});

test("e02 longitud y normalizar", async () => {
  const v = await imp("src/sim/vec.js");
  assert.equal(v.longitud(3, 4), 5);
  const n = v.normalizar(3, 4); cerca(n.x, 0.6, "nx"); cerca(n.y, 0.8, "ny");
  assert.deepEqual(v.normalizar(0, 0), { x: 0, y: 0 });
});

test("e03 acercar", async () => {
  const v = await imp("src/sim/vec.js");
  assert.deepEqual(v.acercar(0, 0, 0.5, 0, 1), { x: 0.5, y: 0 });
  const a = v.acercar(0, 0, 3, 4, 1); cerca(a.x, 0.6, "ax"); cerca(a.y, 0.8, "ay");
  assert.deepEqual(v.acercar(1, 1, 1, 1, 0.5), { x: 1, y: 1 });
});

test("e05 crearMapa", async () => {
  const m = await imp("src/sim/mapa.js");
  const mp = m.crearMapa("#####\n#.@~#\n#\"..#\n#####\n");
  assert.equal(mp.ancho, 5); assert.equal(mp.alto, 4);
  assert.deepEqual(mp.inicio, { x: 2.5, y: 1.5 });
  assert.equal(mp.tiles[1], "#..~#"); assert.equal(typeof mp.tiles[0], "string");
  assert.throws(() => m.crearMapa("###\n#.#\n###"), { message: "El mapa no tiene @" });
  assert.throws(() => m.crearMapa("####\n#@#\n###"), { message: "Filas de distinto largo" });
});

test("e06 esSolido", async () => {
  const m = await imp("src/sim/mapa.js");
  const mp = m.crearMapa("#####\n#.@~#\n#\"..#\n#####\n");
  assert.equal(m.esSolido(mp, 0, 0), true); assert.equal(m.esSolido(mp, 3, 1), true);
  assert.equal(m.esSolido(mp, 1, 1), false); assert.equal(m.esSolido(mp, 1, 2), false); assert.equal(m.esSolido(mp, 2, 1), false);
  for (const [x, y] of [[-1, 1], [5, 1], [1, -1], [1, 4]]) assert.equal(m.esSolido(mp, x, y), true, `${x},${y}`);
});

test("e08 colisión en X", async () => {
  const { crearMapa } = await imp("src/sim/mapa.js"); const { moverConColision: f } = await imp("src/sim/fisica.js");
  const mp = crearMapa(M7);
  let r = f(mp, 2.5, 3.5, 0.3, 0); cerca(r.x, 2.8, "libre"); assert.equal(r.chocoX, false); assert.equal(r.y, 3.5);
  r = f(mp, 5.5, 3.5, 0.5, 0); cerca(r.x, 5.699, "der"); assert.equal(r.chocoX, true);
  r = f(mp, 1.5, 3.5, -0.5, 0); cerca(r.x, 1.301, "izq"); assert.equal(r.chocoX, true);
  r = f(mp, 2.5, 3.5, 0, 0); assert.deepEqual(r, { x: 2.5, y: 3.5, chocoX: false, chocoY: false });
});

test("e09 colisión en Y y deslizamiento", async () => {
  const { crearMapa } = await imp("src/sim/mapa.js"); const { moverConColision: f } = await imp("src/sim/fisica.js");
  const mp = crearMapa(M7);
  let r = f(mp, 3.5, 3.5, 0, -0.5); cerca(r.y, 3.201, "arriba"); assert.equal(r.chocoY, true);
  r = f(mp, 5.5, 3.5, 0.5, -0.3); cerca(r.x, 5.699, "slide x"); assert.equal(r.chocoX, true); cerca(r.y, 3.2, "slide y"); assert.equal(r.chocoY, false);
  r = f(mp, 1.5, 1.5, 0, 0.5); cerca(r.y, 2.0, "abajo libre"); assert.equal(r.chocoY, false);
  r = f(mp, 1.5, 3.5, 0, 0.5); cerca(r.y, 4 - 0.2 - 0.001, "abajo borde"); assert.equal(r.chocoY, true);
});

const J = async () => ({ ...(await imp("src/sim/jugador.js")), ...(await imp("src/sim/mapa.js")), ...(await imp("src/sim/constantes.js")) });
const cmd = (mx, my, ax, ay, rodar = false) => ({ mover: { x: mx, y: my }, apuntar: { x: ax, y: ay }, rodar });

test("e11 crearJugador", async () => {
  const { crearJugador, crearMapa } = await J();
  assert.deepEqual(crearJugador(crearMapa(M20)), { x: 10.5, y: 10.5, vx: 0, vy: 0, angulo: 0, energia: 100, pausaEnergia: 0, rodando: null, invulnerable: false });
});

test("e12 pasoJugador: ángulo, aceleración, freno, sin mutar", async () => {
  const { crearJugador, pasoJugador, crearMapa, ACEL, VEL_MAX, FRENO, DT } = await J();
  const mp = crearMapa(M20); const j0 = crearJugador(mp); const copia = structuredClone(j0);
  let j = pasoJugador(j0, cmd(1, 0, 20, 10.5), mp);
  assert.deepEqual(j0, copia, "no muta");
  cerca(j.angulo, 0, "angulo der"); cerca(j.vx, ACEL * DT, "acel"); cerca(j.x, 10.5 + ACEL * DT * DT, "x");
  assert.equal(pasoJugador(j0, cmd(0, 0, 10.5, 15), mp).angulo, Math.PI / 2);
  assert.equal(pasoJugador({ ...j0, angulo: 1.23 }, cmd(0, 0, 10.5, 10.5), mp).angulo, 1.23, "apuntar sobre sí");
  for (let i = 0; i < 29; i++) j = pasoJugador(j, cmd(1, 0, j.x + 5, j.y), mp);
  cerca(j.vx, VEL_MAX, "vel max");
  j = pasoJugador(j, cmd(0, 0, j.x + 5, j.y), mp); cerca(j.vx, VEL_MAX - FRENO * DT, "freno");
  let p = { ...j0, x: 18.65, vx: VEL_MAX };
  p = pasoJugador(p, cmd(1, 0, 25, 10.5), mp); assert.equal(p.vx, 0, "choque anula vx"); cerca(p.x, 19 - 0.3 - 0.001, "pegado");
});

test("e13 penalización hacia atrás", async () => {
  const { crearJugador, pasoJugador, crearMapa, VEL_MAX, FACTOR_ATRAS } = await J();
  const mp = crearMapa(M20); let j = crearJugador(mp);
  for (let i = 0; i < 30; i++) j = pasoJugador(j, cmd(1, 0, j.x - 5, j.y), mp);
  cerca(j.vx, VEL_MAX * FACTOR_ATRAS, "atrás");
  let k = crearJugador(mp);
  for (let i = 0; i < 30; i++) k = pasoJugador(k, cmd(0, 1, k.x + 5, k.y), mp);
  cerca(k.vy, VEL_MAX, "perpendicular sin penalización");
});

test("e14 iniciar rodar", async () => {
  const { crearJugador, pasoJugador, crearMapa } = await J();
  const mp = crearMapa(M20); const j0 = crearJugador(mp);
  let j = pasoJugador(j0, cmd(0, 1, j0.x + 5, j0.y, true), mp);
  assert.equal(j.energia, 75); assert.ok(j.rodando, "rodando"); cerca(j.rodando.dirX, 0, "dirX"); cerca(j.rodando.dirY, 1, "dirY");
  j = pasoJugador(j0, cmd(0, 0, j0.x + 5, j0.y, true), mp); cerca(j.rodando.dirX, 1, "sin mover → mirada");
  j = pasoJugador({ ...j0, energia: 24 }, cmd(1, 0, j0.x + 5, j0.y, true), mp); assert.equal(j.rodando, null); assert.equal(j.energia, 24);
});

test("e15 rodar: avance, invulnerabilidad y fin", async () => {
  const { crearJugador, pasoJugador, crearMapa, RODAR, VEL_MAX, DT } = await J();
  const mp = crearMapa(M20); const j0 = crearJugador(mp);
  let j = pasoJugador(j0, cmd(1, 0, j0.x + 5, j0.y, true), mp);
  assert.equal(j.invulnerable, false, "tick1"); cerca(j.x, 10.5 + (RODAR.distancia / RODAR.duracion) * DT, "x tick1");
  for (let k = 2; k <= 11; k++) {
    j = pasoJugador(j, cmd(1, 0, j.x + 5, j.y), mp);
    if (k === 2) assert.equal(j.invulnerable, true, "tick2");
    if (k === 10) assert.ok(j.rodando, "sigue en tick10");
  }
  assert.equal(j.rodando, null, "termina tick11"); assert.equal(j.invulnerable, false); cerca(j.vx, VEL_MAX, "vx al terminar");
  cerca(j.x, 10.5 + 11 * (RODAR.distancia / RODAR.duracion) * DT, "x tick11");
});

test("e16 energía: pausa y regeneración", async () => {
  const { crearJugador, pasoJugador, crearMapa } = await J();
  const mp = crearMapa(M20); let j = crearJugador(mp);
  j = pasoJugador(j, cmd(0, 0, j.x + 5, j.y, true), mp); assert.equal(j.pausaEnergia, 0);
  for (let k = 2; k <= 20; k++) j = pasoJugador(j, cmd(0, 0, j.x + 5, j.y), mp);
  assert.equal(j.energia, 75, "tick20");
  for (let k = 21; k <= 30; k++) j = pasoJugador(j, cmd(0, 0, j.x + 5, j.y), mp);
  assert.ok(j.energia > 75 && j.energia < 80, `tick30: ${j.energia}`);
  let f = { ...crearJugador(mp), energia: 99.9, pausaEnergia: 5 };
  f = pasoJugador(f, cmd(0, 0, f.x + 5, f.y), mp); assert.equal(f.energia, 100, "tope");
});

test("e18 cámara: crear y seguir", async () => {
  const c = await imp("src/render/camara.js");
  assert.deepEqual(c.crearCamara(1, 2), { x: 1, y: 2 });
  const k = 1 - Math.exp(-8 / 30); const s = c.seguirCamara({ x: 0, y: 0 }, 10, -10, 1 / 30);
  cerca(s.x, 10 * k, "sx"); cerca(s.y, -10 * k, "sy");
});

test("e19 mundoAPantalla y pantallaAMundo", async () => {
  const c = await imp("src/render/camara.js"); const v = { anchoPx: 800, altoPx: 600, tilePx: 24 };
  assert.deepEqual(c.mundoAPantalla({ x: 5, y: 5 }, 5, 5, v), { x: 400, y: 300 });
  assert.deepEqual(c.mundoAPantalla({ x: 5, y: 5 }, 6, 4, v), { x: 424, y: 276 });
  const w = c.pantallaAMundo({ x: 5, y: 5 }, 424, 276, v); cerca(w.x, 6, "wx"); cerca(w.y, 4, "wy");
});

test("e21 comandoDesdeEntrada", async () => {
  const { comandoDesdeEntrada: f } = await imp("src/entrada/comando.js");
  assert.deepEqual(f(new Set(), { x: 1, y: 2 }, 0), { mover: { x: 0, y: 0 }, apuntar: { x: 1, y: 2 }, rodar: false });
  assert.deepEqual(f(new Set(["w", "d"]), { x: 0, y: 0 }, true).mover, { x: 1, y: -1 });
  assert.deepEqual(f(new Set(["a", "d", "s"]), { x: 0, y: 0 }, false).mover, { x: 0, y: 1 });
});

test("e22 pasosPendientes", async () => {
  const { pasosPendientes: f } = await imp("src/sim/bucle.js"); const DT = 1 / 30;
  let r = f(0, DT); assert.equal(r.pasos, 1); cerca(r.alfa, 0, "alfa1", 1e-6);
  r = f(0, DT * 2.5); assert.equal(r.pasos, 2); cerca(r.alfa, 0.5, "alfa2.5", 1e-6); cerca(r.acumulado, DT * 0.5, "acc", 1e-9);
  r = f(0, 1); assert.equal(r.pasos, 5); assert.equal(r.acumulado, 0); assert.equal(r.alfa, 0);
});

test("e24 mapa prueba-h1", async () => {
  const t = readFileSync(join(DIR, "datos/mapas/prueba-h1.txt"), "utf8");
  assert.ok(t.endsWith("\n"), "termina en salto de línea");
  const f = t.split("\n").slice(0, -1); assert.equal(f.length, 40); assert.ok(f.every((r) => r.length === 60), "60 columnas");
  const esp = (x, y) => {
    if (x === 5 && y === 5) return "@";
    if (x >= 25 && x <= 32 && y >= 25 && y <= 33) return '"';
    if (x === 15 && y === 20) return ".";
    if (x >= 10 && x <= 20 && y >= 20 && y <= 28 && (x === 10 || x === 20 || y === 20 || y === 28)) return "#";
    if (x >= 35 && x <= 44 && y >= 10 && y <= 15) return "~";
    if (y === 0 || y === 39 || x === 0 || x === 59) return "#";
    return ".";
  };
  for (let y = 0; y < 40; y++) for (let x = 0; x < 60; x++) assert.equal(f[y][x], esp(x, y), `(${x},${y})`);
});

function ctxFalso() {
  const log = [];
  return new Proxy({ log }, {
    get: (o, k) => (k in o ? o[k] : (...a) => log.push([k, ...a])),
    set: (o, k, v) => { log.push(["set", k, v]); o[k] = v; return true; },
  });
}

test("e25 dibujar (canvas 2D falso)", async () => {
  const { dibujar } = await imp("src/render/canvas2d.js"); const { crearMapa } = await imp("src/sim/mapa.js");
  const ctx = ctxFalso(); const vista = { anchoPx: 240, altoPx: 240, tilePx: 24 };
  dibujar(ctx, { mapa: crearMapa(M20), jugador: { x: 10.5, y: 10.5, angulo: 0, energia: 74.6, invulnerable: false }, camara: { x: 10.5, y: 10.5 }, vista });
  const textos = ctx.log.filter((l) => l[0] === "fillText");
  const arroba = textos.find((l) => l[1] === "@"); assert.ok(arroba, "dibuja @");
  assert.deepEqual([arroba[2], arroba[3]], [120, 120], "@ al centro");
  assert.ok(textos.some((l) => l[1] === "Energía 75"), "texto de energía");
  assert.ok(textos.filter((l) => l[1] === "." || l[1] === "#").length >= 50, "dibuja tiles");
  assert.ok(textos.length < 400, "solo tiles visibles");
});

test("e26 crearEntrada (DOM falso)", async () => {
  const oyentes = {}; const on = (o) => (t, f) => ((oyentes[o + t] ??= []).push(f));
  globalThis.window = { addEventListener: on("w:") };
  const canvas = { addEventListener: on("c:"), getBoundingClientRect: () => ({ left: 10, top: 20 }) };
  const { crearEntrada } = await imp("src/entrada/teclado.js");
  const e = crearEntrada(canvas); const disparar = (k, ev) => (oyentes[k] ?? []).forEach((f) => f(ev));
  let prevenido = false;
  disparar("w:keydown", { key: "W", code: "KeyW", repeat: false, preventDefault() {} });
  assert.ok(e.teclas.has("w"));
  disparar("w:keyup", { key: "W", code: "KeyW", preventDefault() {} }); assert.ok(!e.teclas.has("w"));
  disparar("w:keydown", { key: " ", code: "Space", repeat: false, preventDefault() { prevenido = true; } });
  assert.equal(e.consumirRodar(), true); assert.equal(e.consumirRodar(), false); assert.ok(prevenido, "preventDefault");
  disparar("w:keydown", { key: " ", code: "Space", repeat: true, preventDefault() {} }); assert.equal(e.consumirRodar(), false, "ignora repeat");
  disparar("c:mousemove", { clientX: 110, clientY: 70 }); assert.deepEqual({ ...e.mousePx }, { x: 100, y: 50 });
});

test("e27 juego.html", () => {
  const h = readFileSync(join(DIR, "juego.html"), "utf8");
  assert.match(h, /id=["']juego["']/); assert.match(h, /type=["']module["'][^>]*src=["']src\/juego\.js["']|src=["']src\/juego\.js["'][^>]*type=["']module["']/);
});

test("e28 juego.js usa los módulos", () => {
  const s = readFileSync(join(DIR, "src/juego.js"), "utf8");
  for (const f of ["crearMapa", "crearJugador", "pasoJugador", "pasosPendientes", "seguirCamara", "pantallaAMundo", "comandoDesdeEntrada", "crearEntrada", "dibujar", "requestAnimationFrame", "prueba-h1.txt"])
    assert.ok(s.includes(f), f);
});

test("e00 sim/ es pura", () => {
  for (const f of ["constantes", "vec", "mapa", "fisica", "jugador", "bucle"]) {
    let s; try { s = readFileSync(join(DIR, `src/sim/${f}.js`), "utf8"); } catch { continue; }
    assert.doesNotMatch(s, /\b(window|document|Math\.random|Date\.now)\b/, f);
  }
});
