# Tests de la web (mobile / PWA)

Nacieron de un bug que costó tres rondas: en la PWA instalada en el iPhone no se
podía escribir en los campos, ni interactuar con ellos, ni seleccionar texto.
Sin forma de reproducirlo, cada intento era una conjetura. Estos tests cierran
esa puerta: levantan la web en un navegador headless con viewport de teléfono y
verifican lo que antes se revisaba a ojo.

## Correrlos

Necesitan `qwen-web` levantado en el 8780, y Playwright (no es dependencia del
repo; se baja aparte, ~100 MB):

```bash
npx playwright install chromium
npm install playwright --no-save
node web/tests/test-inputs.mjs
node web/tests/test-version.mjs
```

## Qué cubre cada uno

**`test-inputs.mjs`** — por cada campo de texto de las 3 páginas, en modo normal
y en modo standalone (PWA):

- que el tap aterrice **en el campo** y no en algo que lo tape (`elementFromPoint`)
- que ningún ancestro tenga `user-select: none` ni `pointer-events: none`
  (en iOS, un `user-select:none` heredado deja los inputs sin foco)
- `font-size` ≥16px (por debajo, iOS hace auto-zoom al enfocar)
- `touch-action` del campo
- que al tocarlo quede enfocado y acepte texto de verdad

**`test-version.mjs`** — el mecanismo anti-caché-vieja: que el badge de versión
aparezca y no robe taps, que una versión vieja simulada dispare la autocuración
(borrar cachés + desregistrar el SW + recargar con `?v=`), y que eso no entre en
un bucle de recargas.

## Límite importante

Chromium headless reproduce layout, apilado, estilos computados y eventos — o
sea, todo lo que es independiente del motor. **No** reproduce los quirks propios
de Safari iOS en modo standalone. Que estos tests pasen descarta un bug en el
código; no garantiza que el iPhone se comporte igual.
