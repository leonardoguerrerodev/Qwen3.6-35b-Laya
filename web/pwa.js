/* pwa.js — service worker, ajustes de ventana propia, y detección de caché vieja.
 *
 * Al guardar la web en el dock del iPhone, iOS la abre en ventana propia
 * ("standalone"): sin barra de Safari, y sin botón de recargar. Eso trae dos
 * cosas que este archivo resuelve:
 *
 *   1. El layout empieza pegado al borde del dispositivo, así que hay que
 *      reservar el alto de la isla/notch → <html class="standalone"> + CSS.
 *   2. No hay forma cómoda de forzar una recarga, y una copia vieja en caché es
 *      indistinguible de un bug. Se detecta y se cura sola (ver más abajo).
 */
(function () {
  // ── 1. Service worker ──
  if ("serviceWorker" in navigator) {
    // Sin await ni .catch ruidoso: si falla (http sin TLS en algún navegador
    // estricto, por ejemplo) la web funciona igual, solo no es instalable.
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").catch(function () {});
    });
  }

  // ── 2. ¿Estamos corriendo código viejo? ──
  //
  // El server le inyecta a ESTE archivo la versión con la que lo sirvió
  // (window.__QWEN_BUILD__). Si el navegador devolvió una copia cacheada, esa
  // constante queda vieja; comparándola contra /api/version, que siempre va a
  // la red, se sabe con certeza. Sin esto no hay manera de distinguir "el fix
  // no funcionó" de "el fix no llegó", que fue justo lo que costó diagnosticar.
  var MIO = window.__QWEN_BUILD__ || "?";

  function badge(texto, malo) {
    var b = document.getElementById("qwen-build") || document.createElement("div");
    b.id = "qwen-build";
    b.textContent = texto;
    b.style.cssText =
      "position:fixed;right:4px;bottom:3px;z-index:9999;font:10px/1.4 ui-monospace,monospace;" +
      "padding:1px 5px;border-radius:4px;pointer-events:none;" +   // nunca debe robar un tap
      (malo ? "background:#c23a6b;color:#fff;opacity:.95;"
            : "background:transparent;color:currentColor;opacity:.32;");
    if (!b.parentNode) document.body.appendChild(b);
  }

  function chequearVersion() {
    fetch("/api/version", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var server = d.version || "?";
        if (server === MIO) {
          sessionStorage.removeItem("qwen-recarga-forzada");
          badge("v" + MIO, false);
          return;
        }
        badge("viejo " + MIO + " ≠ " + server, true);
        // Autocuración, una sola vez por sesión para no entrar en bucle si por
        // alguna razón las versiones nunca llegan a coincidir.
        if (sessionStorage.getItem("qwen-recarga-forzada")) return;
        sessionStorage.setItem("qwen-recarga-forzada", "1");
        limpiarYRecargar(server);
      })
      .catch(function () { badge("v" + MIO, false); });
  }

  function limpiarYRecargar(server) {
    var tareas = [];
    if (window.caches && caches.keys) {
      tareas.push(caches.keys().then(function (ks) {
        return Promise.all(ks.map(function (k) { return caches.delete(k); }));
      }).catch(function () {}));
    }
    if (navigator.serviceWorker && navigator.serviceWorker.getRegistrations) {
      tareas.push(navigator.serviceWorker.getRegistrations().then(function (rs) {
        return Promise.all(rs.map(function (r) { return r.unregister(); }));
      }).catch(function () {}));
    }
    Promise.all(tareas).then(function () {
      // Se recarga con la versión en la URL: una URL distinta no puede venir de
      // la caché, que es lo único seguro cuando ni location.reload() alcanza.
      location.replace(location.pathname + "?v=" + encodeURIComponent(server));
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", chequearVersion);
  } else {
    chequearVersion();
  }

  // ── 3. Ajustes de ventana propia ──
  // `standalone` de iOS; `display-mode` es el equivalente estándar.
  var instalada = window.navigator.standalone === true ||
    (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches);
  if (!instalada) return;

  document.documentElement.classList.add("standalone");

  // Teclado que no aparece al tocar un campo (solo en la PWA instalada).
  // En Safari normal el tap enfoca el <input> y sale el teclado; en standalone
  // iOS a veces genera el `click` pero NO el `focus`, y sin focus no hay
  // teclado. Se fuerza a mano.
  //
  // Clave: el .focus() va DENTRO del handler del gesto. iOS solo abre el
  // teclado si el foco se pide durante un gesto real del usuario; pedirlo más
  // tarde (en un setTimeout, o al terminar un fetch) no sirve.
  //
  // Los dos listeners son deliberadamente pasivos y no cancelan nada: un
  // preventDefault en `touchend` es precisamente lo que rompía el teclado, la
  // selección de texto y la interacción con los campos en una versión anterior.
  function enfocarCampo(e) {
    var el = e.target && e.target.closest
      ? e.target.closest("input, textarea, select")
      : null;
    if (!el || el.disabled || el.readOnly) return;   // readonly no abre teclado a propósito
    if (document.activeElement === el) return;
    try { el.focus({ preventScroll: false }); } catch (err) { /* da igual */ }
  }
  document.addEventListener("touchend", enfocarCampo, { passive: true, capture: true });
  document.addEventListener("click", enfocarCampo, true);
})();
