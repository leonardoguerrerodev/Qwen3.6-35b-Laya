/* no-zoom.js — bloquea el zoom táctil en index.html / voz.html / pi.html.
 *
 * Por qué hace falta JS y no alcanza el <meta viewport>: Safari de iOS ignora
 * a propósito `user-scalable=no` / `maximum-scale` desde iOS 10 (lo hicieron
 * por accesibilidad). El meta tag sigue puesto porque Android/Chrome sí lo
 * respeta; esto cubre iOS, que es el caso real de uso (iPhone por LAN).
 *
 * Dos gestos hay que tapar, y cada uno se tapa donde corresponde:
 *   1. pinch con dos dedos → acá, con los eventos `gesture*` (solo WebKit) más
 *      un refuerzo en `touchmove` con 2+ dedos por si Safari no los emite.
 *   2. doble tap → NO acá: lo mata `touch-action: manipulation` desde el CSS
 *      (ver style.css), que existe justo para eso.
 *
 * Por qué el doble tap ya no se bloquea por JS (importante, no revertir):
 * antes había un handler de `touchend` que hacía preventDefault al detectar dos
 * toques seguidos. Eso rompía el teclado dentro de la PWA instalada — iOS
 * sintetiza el `focus` de un <input> a partir del `touchend`, así que cancelarlo
 * en un listener de `document` dejaba los campos sin teclado. Tenía una exención
 * para controles y aun así fallaba en modo standalone. La vía declarativa
 * (`touch-action`) hace lo mismo sin meterse con la cadena de eventos.
 *
 * `{ passive: false }` es obligatorio en los que quedan: sin eso el navegador
 * ignora el preventDefault() y el gesto pasa igual.
 *
 * Lo que NO rompe, a propósito: el scroll de un dedo (incluida la terminal de
 * pi.html) y los sliders de voz.html — todo eso es un solo touch y nunca entra.
 */
(function () {
  var opts = { passive: false };

  // 1. pinch — gestos nativos de WebKit.
  ["gesturestart", "gesturechange", "gestureend"].forEach(function (ev) {
    document.addEventListener(ev, function (e) { e.preventDefault(); }, opts);
  });

  // 1b. pinch — refuerzo por si no llegan los gesture*: cualquier movimiento
  // con dos o más dedos no es scroll, es zoom.
  document.addEventListener("touchmove", function (e) {
    if (e.touches.length > 1) e.preventDefault();
  }, opts);
})();
