# Prueba: little-coder vs Pi vs Qwen Code (pedido «Grano Sur»)

Preparada el 6-nov-2026. **Todavía no se ha corrido.** Todo está descargado y listo: falta lanzar `./correr.sh` con el llama-server apagado.

## Prueba rápida (recomendada primero): `./rapida.sh`

**Tu Pi normal contra little-coder**, unos 10 minutos en total, con nota automática:

- **La tarea (v2):** un proyecto chico de 3 archivos (`rapida/inicial/`: carrito.js, precios.js, formato.js) con errores que el pedido **no señala**: describe el comportamiento esperado y el agente tiene que encontrarlos. Son un id que llega como texto, el IVA incluido en el precio mal calculado, los negativos mal formateados y faltan validaciones. Además hay que agregar `dividirCuenta`, que tiene casos borde.
- **La nota:** la pone un **oráculo oculto** (`rapida/oraculo.js`, 19 pruebas). Validado: una solución de referencia saca 19/19 y el proyecto sin tocar, 5/19.
- **Mismo nivel de razonamiento para todos:** `EFFORT` (xhigh por defecto) va al servidor como `--reasoning-effort`, que es lo que usan qwen-code y little-coder porque no mandan nivel. Pi lo recibe con `--thinking`. Se cambia con `EFFORT=medium ./rapida.sh`.
- **Dónde trabajan:** cada agente en una carpeta temporal fuera del repo, así que no ve el oráculo. Lo que dejó se copia a `rapida/resultados/<agente>/`.
- **El servidor:** uno solo, con el perfil activo de q38, para los dos. Tokens y peticiones salen del log de llama-server, medidos igual para ambos.
- **Tope:** 600 s por agente. Se cambia con `TMAX=900 ./rapida.sh`.

```bash
./rapida.sh              # pi y lc (tu Pi normal vs little-coder)
./rapida.sh pi lc qcode  # agrega qwen-code como tercera referencia
```

Resultado en `rapida/resumen.txt`, una tabla por corrida:

```
agente oráculo    seg   tokens   pet  herramientas
pi     19/19      ...
lc     17/19      ...
```

- **oráculo:** pruebas pasadas; ⏱ = cortado por el tope.
- **tokens:** generados por el modelo.
- **pet:** peticiones al servidor.

Los fallos de cada agente quedan en `rapida/logs/<agente>.oraculo.json`.

Cómo corre cada agente en la rápida:

- **pi:** tu Pi normal. Usa la misma función del launcher en modo edit (`_qwen_pi edit`): `~/.pi-qwen/agent` con tus extensiones (oficio, modes, laya-hook, voz-hook…), AGENTS.md y las herramientas read/write/edit/bash/grep/find/ls. Solo se agregan `-p --mode json` para correrlo sin pantalla y `--thinking $EFFORT`.
- **lc:** little-coder tal cual, con el shell por su lista blanca, que incluye `node`.
- **qcode** (opcional): como el modo edit del launcher, `auto-edit`. El shell queda denegado, así que no puede probar su código.

Con la temperatura del perfil (1.0 en punto-dulce) una sola corrida es ruidosa. Si dos agentes quedan cerca, conviene repetirla.

La prueba larga (`correr.sh`, la landing completa, 15 a 30 min por agente) queda para confirmar al ganador.

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

Revisé el código del paquete descargado (hoy copiado en `little-coder/`, en la raíz del repo):

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
- **Dependencias:** `@earendil-works/pi-coding-agent`, `playwright` y `@sinclair/typebox`. Se instalaron con `--ignore-scripts` (sin postinstall), 136 paquetes, unos 194 MB. Desde el 6-nov ya no: `little-coder/` es una copia sobre Pi 1.x y solo instala Pi.

## Archivos

| Archivo | Qué es |
|---|---|
| `rapida.sh` | Prueba rápida: tu Pi vs little-coder (qwen-code opcional), tarea chica, oráculo oculto, tabla en `rapida/resumen.txt` |
| `rapida/` | Archivo inicial, oráculo, resultados y logs de la rápida |
| `correr.sh` | Prueba larga: lanza el servidor, corre G y/o F, y escribe `resumen.txt` |
| `models-lc.json` | Catálogo que lee little-coder (`LITTLE_CODER_MODELS_FILE`): proveedor `llamacpp` → `http://127.0.0.1:8001/v1`, modelo `qwen3.8-27b` |
| `../../../little-coder/` | Desde el 6-nov, copia de little-coder 1.20.0 sobre Pi 1.x (la del launcher, `lib/lc.sh`): G ya no corre exactamente «tal como viene». Ver su README |
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

Si falta su Pi (otro PC, o se borró `little-coder/node_modules`):
```bash
cd ../../../little-coder && npm ci --ignore-scripts
```

Probar little-coder a mano, interactivo, con la misma configuración aislada (con el servidor del launcher ya arriba en :8001):
```bash
D="$PWD"; HOME="$D/estado/home" PI_CODING_AGENT_DIR="$D/estado/pi-agent" \
  LITTLE_CODER_MODELS_FILE="$D/models-lc.json" LLAMACPP_API_KEY=local LITTLE_CODER_NO_UPDATE_CHECK=1 \
  ../../../little-coder/bin/little-coder.mjs --model llamacpp/qwen3.8-27b
```
Con tu kit (skills, oficio, permisos que preguntan, planes en `tareas/`): menú `qwen` → Agente: little-coder.
Atajos útiles: `ctrl+q` modo plan, `ctrl+h` atajos, `/extensions` lo que cargó, `/skills` fichas de herramientas.

## Qué mirar al comparar

- **¿Terminó?** Los tres archivos, con todo lo pedido: 9 o más productos en CLP, filtro, modo oscuro con localStorage y responsive.
- **Tiempo total** y **tokens generados** (`logs/*/metricas.json`).
- **Errores de herramienta y reescrituras.** E tuvo cero.
- **Compactaciones**, si las hubo, y cuánto contexto usó cada agente. Como referencia, qwen-code compacta a ~19k con 52k de ventana.
- **Calidad visual.** Abrir las tres páginas lado a lado.

## Si little-coder gana

No reemplazar el launcher, porque perdería Laya, voz y el oficio. Las piezas candidatas para llevarse al Pi del launcher, todas en `little-coder/.pi/extensions/` (raíz del repo):

- `output-parser`: repara llamadas a herramientas mal formadas.
- `quality-monitor`: detecta respuestas vacías, inventadas o en bucle, y pide corrección.
- `skill-inject`: solo las fichas de herramientas que el turno va a usar.
- `read-guard` y `write-guard`.
- `context-watchdog` y `evidence-compact`: manejo de ventanas chicas.

## Resultados

**Rápida v1 (6-nov, 04:44 y 04:48):** solo carrito.js, 13 pruebas. Pi en medium; qwen-code y little-coder en xhigh porque el servidor no fijaba nivel.

| agente | oráculo | seg | tokens |
|---|---|---|---|
| pi | 13/13 · 13/13 | 49 · 41 | 1134 · 925 |
| lc | 13/13 · 13/13 | 48 · 49 | 1196 · 1264 |
| qcode | 13/13 · 13/13 | 65 · 88 | 1389 · 1863 |

Empate en calidad: la tarea era demasiado fácil para distinguirlos. De ahí salió la v2.

**Rápida v2:** pendiente.
