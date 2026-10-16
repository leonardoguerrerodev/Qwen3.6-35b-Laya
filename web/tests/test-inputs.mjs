/* Testea si los campos de texto son realmente alcanzables e interactuables,
 * simulando el modo standalone (PWA instalada) que es donde falla.
 *
 * Lo que sí reproduce esto: layout, apilado (z-index), estilos computados y si
 * algo tapa al campo (elementFromPoint). Eso es independiente del motor.
 * Lo que NO reproduce: los quirks propios de Safari iOS en standalone.
 */
import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8780";
const PAGINAS = {
  "/": ["#voz-texto", "#cdir-path"],
  "/voz.html": ["#texto", "#perfil"],
  "/pi.html": ["#pin", "#compose"],
};

const browser = await chromium.launch();
let fallos = 0;

for (const standalone of [false, true]) {
  console.log(`\n${"=".repeat(64)}\n  MODO: ${standalone ? "STANDALONE (PWA instalada)" : "navegador normal"}\n${"=".repeat(64)}`);

  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },      // iPhone 14
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
  });

  if (standalone) {
    // pwa.js decide por navigator.standalone / display-mode. Se fuerza el
    // primero antes de que corra cualquier script de la página.
    await ctx.addInitScript(() => {
      Object.defineProperty(window.navigator, "standalone", { get: () => true });
    });
  }

  for (const [ruta, selectores] of Object.entries(PAGINAS)) {
    const page = await ctx.newPage();
    const errores = [];
    page.on("pageerror", (e) => errores.push(String(e)));
    await page.goto(BASE + ruta, { waitUntil: "networkidle" });
    await page.waitForTimeout(600);

    const claseStandalone = await page.evaluate(() =>
      document.documentElement.classList.contains("standalone"));
    console.log(`\n── ${ruta}  (html.standalone=${claseStandalone})`);
    if (errores.length) {
      console.log(`   ⚠ errores JS: ${errores.join(" | ")}`);
      fallos++;
    }

    for (const sel of selectores) {
      const r = await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        if (!el) return { falta: true };
        const cs = getComputedStyle(el);
        const caja = el.getBoundingClientRect();
        const cx = caja.left + caja.width / 2;
        const cy = caja.top + caja.height / 2;
        const encima = document.elementFromPoint(cx, cy);

        // ¿Algún ancestro bloquea la selección de texto? En iOS un
        // user-select:none heredado deja los inputs sin foco.
        let bloqueador = null;
        for (let p = el; p && p !== document.documentElement; p = p.parentElement) {
          const s = getComputedStyle(p);
          const us = s.webkitUserSelect || s.userSelect;
          if (us === "none" && !bloqueador) {
            bloqueador = (p.tagName + (p.id ? "#" + p.id : "") +
                          (p.className && typeof p.className === "string"
                            ? "." + p.className.trim().split(/\s+/).join(".") : "")) + " → user-select:none";
          }
          if (s.pointerEvents === "none" && !bloqueador) {
            bloqueador = p.tagName + " → pointer-events:none";
          }
        }

        return {
          visible: caja.width > 0 && caja.height > 0,
          caja: { x: Math.round(caja.x), y: Math.round(caja.y), w: Math.round(caja.width), h: Math.round(caja.height) },
          dentroPantalla: cy >= 0 && cy <= innerHeight && cx >= 0 && cx <= innerWidth,
          fontSize: cs.fontSize,
          touchAction: cs.touchAction,
          userSelect: cs.webkitUserSelect || cs.userSelect,
          pointerEvents: cs.pointerEvents,
          readOnly: !!el.readOnly,
          // Lo decisivo: ¿el tap en el centro del campo aterriza EN el campo?
          tapLlega: encima === el || el.contains(encima),
          tapAterrizaEn: encima ? encima.tagName + (encima.id ? "#" + encima.id : "") +
            (encima.className && typeof encima.className === "string" && encima.className.trim()
              ? "." + encima.className.trim().split(/\s+/)[0] : "") : "(nada)",
          bloqueador,
        };
      }, sel);

      if (r.falta) { console.log(`   ${sel.padEnd(12)} ✗ no existe en el DOM`); fallos++; continue; }

      // Prueba real: tocar el campo y ver si queda enfocado y acepta texto.
      let enfocado = false, escribio = false;
      try {
        await page.tap(sel, { timeout: 2500 });
        enfocado = await page.evaluate((s) => document.activeElement === document.querySelector(s), sel);
        const esSelect = await page.evaluate((s) => document.querySelector(s).tagName === "SELECT", sel);
        if (!r.readOnly && !esSelect && enfocado) {
          await page.keyboard.type("abc");
          escribio = await page.evaluate((s) => (document.querySelector(s).value || "").includes("abc"), sel);
        }
      } catch (e) { /* el tap no llegó */ }

      const esSel = await page.evaluate((s) => document.querySelector(s).tagName === "SELECT", sel);
      const ok = (r.tapLlega || !r.dentroPantalla) && (r.readOnly || esSel ? enfocado : (enfocado && escribio));
      if (!ok) fallos++;
      console.log(
        `   ${ok ? "✓" : "✗"} ${sel.padEnd(12)} tap→${r.tapAterrizaEn.padEnd(22)} ` +
        `foco=${String(enfocado).padEnd(5)} escribe=${String(escribio).padEnd(5)} ` +
        `font=${r.fontSize.padEnd(5)} touch-action=${r.touchAction.padEnd(13)} us=${r.userSelect}` +
        (r.readOnly ? " [readonly]" : "") +
        (r.bloqueador ? `\n       ⚠ BLOQUEADOR: ${r.bloqueador}` : "")
      );
    }
    await page.close();
  }
  await ctx.close();
}

await browser.close();
console.log(`\n${"=".repeat(64)}\n  ${fallos === 0 ? "TODO OK" : fallos + " PROBLEMA(S)"}\n${"=".repeat(64)}`);
