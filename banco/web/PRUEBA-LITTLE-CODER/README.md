# Prueba: little-coder vs Pi vs Qwen Code (pedido «Grano Sur»)

Preparada el 6-nov-2026. **Todavía no se ha corrido.** Todo está descargado y listo: falta lanzar `./correr.sh` con el llama-server apagado.

## Por qué

La variante **E** (`../E/`) mostró que el Qwen3.8-27B local, con **Qwen Code** y el tope de razonamiento en el servidor (`--reasoning-budget 6000`), hace la landing completa en un solo pedido. Las variantes de **Pi** (A y B) habían fallado, pero corrieron **sin** ese tope y con `maxTokens` = ctx/4, así que la comparación no era pareja.

[little-coder](https://github.com/itayinbarr/little-coder) (2,7k ⭐, Apache-2.0) es Pi más unas 36 extensiones y skills, afinado para modelos locales chicos y medido con **Qwen3.6-35B-A3B en llama.cpp** (el modelo base del launcher):

- 78,7 % en Aider Polyglot.
- 40 % en Terminal-Bench 1.
- Aceptado en el leaderboard oficial de Terminal-Bench 2.0.

La tesis del proyecto es que el ajuste entre el agente y el modelo pesa tanto como el modelo: con un Qwen de 9,7B pasó de 19 % a 45 % en Aider Polyglot.

Esta prueba responde **qué agente saca más del mismo modelo, con el mismo servidor y el mismo pedido.**

## Variantes

| | Agente | Configuración |
|---|---|---|
| **E** (hecha) | Qwen Code 0.26.8 | `auto-edit` (shell denegado), contexto 49152, tope de 6000 en el servidor. Resultado: página completa, 22,5 min (`../E/LEEME.md`) |
| **G** | **little-coder 1.20.0 tal como viene** | Sus 36 extensiones y su perfil por defecto. Permisos `auto`: edita libre y el shell pasa por su lista blanca |
| **F** | Pi + kit de oficio del launcher | `maxTokens` = ctx/2, `--thinking medium` (reasoning_effort por petición) y el kit de oficio (AGENTS.md "base primero, mejora con edit") |

Las tres usan el mismo llama-server:
- arma el comando del **perfil activo de q38** (hoy punto-dulce: temp 1.0, KV q4_0, MTP y `--reasoning-budget 6000` con mensaje);
- fuerza `-c 49152`, igual que E;
- guarda el comando exacto en `logs/servidor-cmd.txt`.

### Diferencias que hay que tener presentes al comparar

- **G trae su propio tope de razonamiento** (extensión `thinking-budget`, 4096 tokens), que salta antes que el del servidor (6000). Al pasarlo, aborta el turno, apaga el razonamiento y le pide al modelo que se comprometa con una implementación.
- **G manda `temperature: 0.3`** (su perfil por defecto) y `max_tokens` 4096 por respuesta. El servidor arranca con 1.0, pero manda lo que pide el cliente.
- **G no manda `reasoning_effort`**, así que la plantilla de Qwen3.8 usa su valor por defecto, `xhigh`, como en E. **F** manda `medium`.
- **G no carga las extensiones del launcher** (laya-hook, voz-hook, oficio, modes): arranca Pi con `--no-extensions` más su paquete.
- Su catálogo de modelos ya trae `qwen3.8-27b`, pero sin perfil propio: usa el de por defecto.

Si G gana, conviene una segunda corrida que apague uno de los dos topes (el suyo o el del servidor), para saber cuál pesa.

## Revisión de seguridad de little-coder (6-nov-2026, v1.20.0)

Revisé el código del paquete descargado (`lc/node_modules/little-coder`):

- **Sin telemetría.** Lo único que sale solo a internet es la consulta de versión al registro de npm (`bin/update-check.mjs`). Si hay versión nueva, *pregunta* antes de instalarla (`npm install -g --ignore-scripts`). Aquí va apagada con `LITTLE_CODER_NO_UPDATE_CHECK=1` y `--no-update-check`.
- **Red, solo si el modelo la pide:**
  - búsqueda web por DuckDuckGo (`extra-tools`);
  - navegador con Playwright (`browser`, usa sus propios navegadores; aquí no están descargados);
  - `deep-research` (F2).

  El pedido de la prueba no las necesita.
- **Procesos:** el lanzador ejecuta Pi y relanza tras una actualización. `bg-shell`, `shell-session` y `subagent` ejecutan los comandos que el modelo pide.
- **Permisos (`permission-gate`):** el modo `auto` (por defecto) solo deja pasar comandos de una lista blanca:
  - lectura: ls, cat, grep, find, sed;
  - git solo de lectura;
  - python/node, pero no con `-e`/`-c`.

  Las ediciones con `write` y `edit` pasan sin preguntar.
- **Escribe fuera del proyecto:**
  - `~/.little-coder/checkpoints/` (respaldos antes de editar);
  - `~/.cache` (caché de la consulta de versión);
  - `~/.config/little-coder/` (extensiones propias, opcional).

  Para la prueba, `correr.sh` usa un **HOME aislado** en `estado/home` y un agente de Pi aislado en `estado/pi-agent`. No toca `~/.pi`, `~/.pi-qwen` ni `~/.config`.
- **Dependencias:** `@earendil-works/pi-coding-agent`, `playwright` y `@sinclair/typebox`. Se instalaron con `--ignore-scripts` (sin postinstall), 136 paquetes, unos 194 MB, en `lc/node_modules` (fuera de git).

## Archivos

| Archivo | Qué es |
|---|---|
| `correr.sh` | Lanza el servidor, corre G y/o F, y escribe `resumen.txt` |
| `models-lc.json` | Catálogo que lee little-coder (`LITTLE_CODER_MODELS_FILE`): proveedor `llamacpp` → `http://127.0.0.1:8001/v1`, modelo `qwen3.8-27b` |
| `lc/package.json`, `lc/package-lock.json` | little-coder fijado en 1.20.0 |
| `lc/node_modules/` | La descarga (ignorada por git) |
| `G/`, `F/` | Las páginas que haga cada agente (se crean al correr) |
| `logs/` | JSONL de cada corrida, métricas, log y comando del servidor (ignorado por git) |
| `estado/` | HOME y agente de Pi aislados de little-coder (ignorado por git) |

## Cómo correrla

1. Que no haya nada usando la GPU: cerrar qwen-code y Pi, y correr `qwen-stop`. El script se niega a partir si hay un llama-server corriendo.
2. Revisar que el perfil activo de q38 sea el que se quiere comparar: el menú, `5` y el editor de perfil. Para replicar E: punto-dulce con `--reasoning-budget 6000` y Effort vacío.
3. Correr, cada una toma unos 15 a 30 min:
   ```bash
   cd '/run/media/xaski/7c0ba586-7758-4419-b3de-f524b9c9a1fb/!GitHub/!Obsedium/Qwen3.6-35b+Laya/banco/web/PRUEBA-LITTLE-CODER'
   ./correr.sh lc      # solo little-coder (G)
   ./correr.sh pi      # solo Pi + kit (F)
   ./correr.sh ambos   # G y luego F, con el mismo servidor
   ```
4. Mirar `resumen.txt` (tiempo, herramientas usadas y líneas por archivo) y abrir `G/index.html` y `F/index.html` junto a `../E/index.html`.

Si falta la descarga (otro PC, o se borró `lc/node_modules`):
```bash
cd lc && npm ci --ignore-scripts
```

Probar little-coder a mano, interactivo, con la misma configuración aislada (con el servidor del launcher ya arriba en :8001):
```bash
D="$PWD"; HOME="$D/estado/home" PI_CODING_AGENT_DIR="$D/estado/pi-agent" \
  LITTLE_CODER_MODELS_FILE="$D/models-lc.json" LLAMACPP_API_KEY=local LITTLE_CODER_NO_UPDATE_CHECK=1 \
  lc/node_modules/.bin/little-coder --no-update-check --model llamacpp/qwen3.8-27b
```
Atajos útiles: `ctrl+q` modo plan, `ctrl+h` atajos, `/extensions` lo que cargó, `/skills` fichas de herramientas.

## Qué mirar al comparar

- **¿Terminó?** Los tres archivos, con todo lo pedido: 9 o más productos en CLP, filtro, modo oscuro con localStorage y responsive.
- **Tiempo total** y **tokens generados** (`logs/*/metricas.json`).
- **Errores de herramienta y reescrituras.** E tuvo cero.
- **Compactaciones**, si las hubo, y cuánto contexto usó cada agente. Como referencia, qwen-code compacta a ~19k con 52k de ventana.
- **Calidad visual.** Abrir las tres páginas lado a lado.

## Si little-coder gana

No reemplazar el launcher, porque perdería Laya, voz y el oficio. Las piezas candidatas para llevarse al Pi del launcher, todas en `lc/node_modules/little-coder/.pi/extensions/`:

- `output-parser`: repara llamadas a herramientas mal formadas.
- `quality-monitor`: detecta respuestas vacías, inventadas o en bucle, y pide corrección.
- `skill-inject`: solo las fichas de herramientas que el turno va a usar.
- `read-guard` y `write-guard`.
- `context-watchdog` y `evidence-compact`: manejo de ventanas chicas.

## Resultados

(pendiente: pegar aquí las líneas de `resumen.txt` y las observaciones)
