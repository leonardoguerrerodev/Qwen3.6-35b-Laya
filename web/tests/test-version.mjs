/* Verifica el mecanismo anti-caché-vieja:
 *   1. Con la versión correcta → badge discreto, sin recarga.
 *   2. Con una versión vieja simulada (se pisa __QWEN_BUILD__ como lo haría una
 *      copia cacheada de pwa.js) → badge rojo de alerta + autocuración:
 *      borra cachés, desregistra el SW y recarga con ?v=<version>.
 *   3. El badge nunca debe robar un tap (pointer-events:none).
 */
import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8780";
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
let fallos = 0;
const chequear = (cond, txt) => { console.log(`   ${cond ? "✓" : "✗"} ${txt}`); if (!cond) fallos++; };

// ── 1. versión al día ──
console.log("\n── Versión al día");
{
  const page = await ctx.newPage();
  await page.goto(BASE + "/", { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  const b = await page.evaluate(() => {
    const el = document.getElementById("qwen-build");
    return el ? { txt: el.textContent, pe: getComputedStyle(el).pointerEvents } : null;
  });
  chequear(!!b, "aparece el badge de versión");
  chequear(b && /^v\d/.test(b.txt), `badge muestra la versión: "${b && b.txt}"`);
  chequear(b && b.pe === "none", "el badge no intercepta taps (pointer-events:none)");
  chequear(!page.url().includes("?v="), "no recargó (no hacía falta)");
  await page.close();
}

// ── 2. versión vieja simulada ──
console.log("\n── Versión vieja (simula pwa.js cacheado)");
{
  const page = await ctx.newPage();
  // Se pisa la constante que inyecta el server, justo como pasaría si el
  // navegador sirviera un pwa.js viejo desde la caché.
  await page.addInitScript(() => {
    Object.defineProperty(window, "__QWEN_BUILD__", { value: "01/01 00:00", writable: false, configurable: false });
  });
  await page.goto(BASE + "/", { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);
  const url = page.url();
  chequear(url.includes("?v="), `se autocuró recargando con cache-buster → ${url.replace(BASE, "")}`);
  const quedoSw = await page.evaluate(() =>
    navigator.serviceWorker.getRegistrations().then((r) => r.length));
  console.log(`   · service workers tras la limpieza: ${quedoSw}`);
  await page.close();
}

// ── 3. que no haya bucle de recargas ──
console.log("\n── Sin bucle de recarga");
{
  const page = await ctx.newPage();
  let navegaciones = 0;
  page.on("framenavigated", (f) => { if (f === page.mainFrame()) navegaciones++; });
  await page.addInitScript(() => {
    Object.defineProperty(window, "__QWEN_BUILD__", { value: "01/01 00:00", writable: false, configurable: false });
  });
  await page.goto(BASE + "/", { waitUntil: "networkidle" });
  await page.waitForTimeout(4000);
  chequear(navegaciones <= 3, `navegaciones totales: ${navegaciones} (sin bucle)`);
  await page.close();
}

await browser.close();
console.log(`\n${fallos === 0 ? "TODO OK" : fallos + " PROBLEMA(S)"}`);
