---
name: rea-js
description: >-
  Recetas exactas de `rea` para analizar una aplicación JavaScript/Electron, sitio estático, PWA o bundle web (carpeta o .asar): archivos, módulos, almacenamiento, IPC, service workers. Usar solo cuando la skill `rea` te mandó aquí. No usar para .NET, Go, Rust ni para binarios.
---

# REA — JavaScript / Electron / web

Reglas de salida y tope de llamadas: las de la skill `rea`. Aquí solo van las recetas.

## Paso 1 — analizar (una vez; tarda segundos o minutos)

```
mkdir -p rea-out
rea analyze-javascript-application '<RUTA>' --format json 2>/dev/null > rea-out/01-js.json
```
Si la carpeta es enorme y solo importan archivos concretos, añade `--source-path <ruta/relativa/dentro>` (repetible). Si no, déjalo completo.

## Paso 2 — mirar (todas son lecturas del archivo; no llaman a `rea`)

| Quiero saber… | Comando |
|---|---|
| Tamaño y cobertura | `jq '.normalized_result.statistics' rea-out/01-js.json` |
| Resumen Electron/IPC (ventanas, preload, canales) | `jq '.normalized_result.summary' rea-out/01-js.json` |
| Cuántos nodos de cada tipo | `jq -c '[.normalized_result.graph.nodes[].kind]\|group_by(.)\|map({(.[0]):length})\|add' rea-out/01-js.json` |
| Lista de archivos y módulos | `jq -r '.normalized_result.graph.nodes[] \| [.kind,(.observations[0].label // ""),(.observations[0].properties.path // "")]\|@tsv' rea-out/01-js.json \| head -60` |
| Uso de almacenamiento (localStorage, cache, IndexedDB…) | `jq -c '.normalized_result.graph.nodes[] \| select(.kind=="storage") \| .observations[] \| {label,properties}' rea-out/01-js.json \| head -20` |
| Qué no se pudo analizar | `jq -r '.normalized_result.limitations[]' rea-out/01-js.json \| cut -c1-200` |
| Alguna palabra concreta (ruta, API, clave) | `grep -rn -F '<palabra>' '<RUTA>' \| head -20` (es `grep` normal sobre el código; **no** llama a `rea`) |

`kind` útiles: `javascript-module`, `javascript-asset`, `electron-renderer`, `storage`, `artifact` (archivo), `unknown` (lo que no pudo analizar: anótalo `[D]`).

## Paso 3 — cerrar

- Para "qué hace esta app", cruza **Paso 2** con `grep` sobre los archivos que la lista marcó como módulos. Las conclusiones van como `[I]` citando el archivo.
- Para Electron, si `summary` trae `preload_entrypoints`, `context_bridge_apis` o `ipc.literal_channels` distintos de 0, repórtalos como `[O]` con su número. Si todo es 0 y la app no es Electron, di "no es Electron" `[I]`.

## Gotchas

- `cache-storage` con `mechanism: call:then` suele ser un service worker (`sw.js`): es una PWA. `[I]`.
- Las `limitations` repiten el mismo aviso para cada HTML ("inline JavaScript bodies…"): cuéntalo una sola vez como `[D]`.
- Un `.wasm` o `.js` minificado grande aparece como un solo módulo: su contenido interno no se desmenuza; dilo `[D]` si la pregunta lo pide.
