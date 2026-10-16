/* sw.js — service worker mínimo, a propósito.
 *
 * Existe para que la web cuente como PWA instalable (Chrome/Android lo exige;
 * iOS no, pero no molesta) y para que al guardarla en el dock del iPhone abra
 * en ventana propia, sin la barra de Safari.
 *
 * NO cachea nada. Es tentador guardar el "app shell" offline, pero esto es un
 * panel de control de una máquina de la LAN: sin Nobora encendida no hay nada
 * que hacer con una copia offline de la UI, y una versión vieja en caché
 * después de tocar el HTML sería un dolor de cabeza difícil de diagnosticar
 * desde el teléfono. Así que todo va siempre a la red.
 *
 * skipWaiting + clients.claim: que una versión nueva tome el control enseguida
 * en vez de esperar a que se cierren todas las pestañas.
 */
self.addEventListener("install", () => self.skipWaiting());

// Al activarse, borra TODA caché que haya quedado de versiones anteriores.
// Una PWA instalada en el dock no tiene botón de recargar, así que si se queda
// con HTML/JS viejo no hay forma cómoda de sacarla de ahí desde el teléfono.
self.addEventListener("activate", (e) => e.waitUntil(
  caches.keys()
    .then((claves) => Promise.all(claves.map((k) => caches.delete(k))))
    .catch(() => {})
    .then(() => self.clients.claim())
));

// Las navegaciones (abrir la app, cambiar de página) se piden siempre frescas,
// saltando la caché HTTP del navegador. Es la contraparte del `Cache-Control:
// no-store` del server: entre los dos, la app no puede quedarse pegada a una
// versión vieja. Si la red falla se reintenta normal, para no romper del todo.
self.addEventListener("fetch", (e) => {
  if (e.request.mode !== "navigate") return;   // el resto va directo a la red
  e.respondWith(
    fetch(new Request(e.request.url, { cache: "reload", credentials: "same-origin" }))
      .catch(() => fetch(e.request))
  );
});
