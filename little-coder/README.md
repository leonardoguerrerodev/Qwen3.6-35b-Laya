# little-coder (copia propia sobre Pi fijo)

Copia de [little-coder](https://github.com/itayinbarr/little-coder) 1.20.0 (Apache-2.0, © 2026 Itay Inbar; ver `LICENSE` y `NOTICE`). Está versionada en git y corre sobre un Pi fijo en `node_modules` (la versión, en `package.json`). La arranca el menú `qwen` (Agente: little-coder) a través de `lib/lc.sh`, con el kit de `.pi-qwen` encima.

## Por qué una copia
- **El paquete de npm no puede moverse de Pi 0.83.** Su dependencia es `^0.83.0` y su repo no se mueve desde el 18-sep-2026.
- **Sus 36 extensiones funcionan tal cual sobre Pi 1.x.** Probado en 1.4.0 y 1.5.0: Pi hace que importen el Pi que está corriendo.
- **Al ser nuestra, nada la reemplaza solo.** No hay `npm update` de little-coder ni comando `/update`, y actualizar tu `pi` principal (`~/.pi/agent`) no la toca. Su Pi cambia solo cuando se cambia aquí, a propósito.

## Cambios respecto del original
- `bin/little-coder.mjs`: lanzador nuevo (~60 líneas en vez de 533). Arma el mismo comando de Pi, pero:
  - no busca actualizaciones;
  - no parchea Pi;
  - no escribe en `~/.pi/agent`.

  Lo usan también los sub-agentes.
- `.pi/extensions/edit-repair/` (nueva) reemplaza el parche 2 de `scripts/patch-pi.mjs`: repara `edits` mandado como texto con saltos de línea crudos. En Pi 1.x aquel parche ya no encontraba dónde aplicarse y se saltaba sin avisar.
- **Fuera:**
  - el parche 1, que era solo estético (ocultaba "Operation aborted");
  - la extensión `update-notice`, cuyo `/update` instalaba little-coder global (`npm install -g`) y pisaría esta copia;
  - `bin/update-check.mjs` y `scripts/`.
- `.pi/settings.json`: `thinking_budget` en 32768 en todos los perfiles. Su tope abortaba el turno y apagaba el razonamiento; ahora lo corta el servidor, como en Pi.
- `package.json`: solo depende de Pi, con el mismo override que su instalador oficial (protobufjs). Playwright no está: su navegador no se usa.

**Historial de Pi:** 1.4.0 (6-nov-2026) → 1.5.0 (6-nov-2026, `probar.sh` 7/7). En 1.5.0 `edit-repair` sigue haciendo falta: sin ella falla con `edits.0: expected object, got string`.

## Instalar (otro PC, o si se borró `node_modules`)
```bash
npm ci --ignore-scripts
./probar.sh
```

## Actualizar Pi
1. Cambiar la versión de `@earendil-works/pi-coding-agent` en `package.json`.
2. Correr `npm install --ignore-scripts`.
3. Correr `./probar.sh`. No usa la GPU: un servidor falso le da un guion fijo y revisa:
   - que carguen las extensiones y no haya errores;
   - que estén las 26 herramientas;
   - que el permission-gate bloquee `rm`;
   - que edit-repair arregle un edit roto.
4. Si algo sale FALLA, se vuelve atrás con `git checkout package.json package-lock.json && npm ci --ignore-scripts`.

Después, con el servidor falso del launcher, confirmar lo que `lib/lc.sh` toma de aquí:
- `permission-gate` exporta `isSafeBash`, y `_shared/shell-write.ts` exporta `splitCommandChain` y `detectWriteTargets`. Los usa `lib/lc-permisos.ts`.
- El modo plan escribe `.pi/approved-plan.md`, que `lib/lc-plan.ts` copia a `tareas/`.
- Los nombres de `QWEN_LC_SIN_TOOLS`: con el kit tienen que quedar 12 herramientas.

**No ponerlo en el PATH ni correrlo sin `PI_CODING_AGENT_DIR`:** Pi usaría `~/.pi/agent`, la carpeta de tu Pi principal. `lib/lc.sh` le da la suya, `~/.pi-qwen/lc-agent`.
