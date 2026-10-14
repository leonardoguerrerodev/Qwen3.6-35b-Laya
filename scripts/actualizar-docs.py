#!/usr/bin/env python3
# actualizar-docs.py — actualiza docs/ con lo de la sesión 2026-10-14 (pendiente 11), en un solo paso.
#
# Uso (desde cualquier carpeta; vive en <repo>/scripts/ y actúa sobre <repo>/docs/):
#   python3 scripts/actualizar-docs.py                 aplica los cambios
#   python3 scripts/actualizar-docs.py --dry-run       muestra qué haría, sin escribir nada
#   python3 scripts/actualizar-docs.py RUTA [RUTA...]  además copia a docs/ los progreso-sesion-2026-10-14*.md indicados
#
# Qué hace:
#   - plan-qwen-3060.md, checklist-qwen-3060.md, anexo-router-ram-qwen.md: rutas nuevas, qwen-setup.sh v6.3,
#     línea base de llama-bench, sección de la sesión 2026-10-14 y estado de los pendientes.
#   - progreso-sesion-2026-10-14.md y progreso-sesion-2026-10-14-laya.md: si no están en docs/, los copia
#     (los busca en docs/, la raíz del repo, la carpeta actual, ~/Descargas y ~/Downloads) y les pone una nota arriba.
#   - kev: NO se borra ninguna mención; solo se anota que quedó descartado y no se usará.
#
# Garantías:
#   - Idempotente: si un cambio ya está aplicado lo salta; se puede correr varias veces.
#   - Cada cambio exige que el texto original exista exactamente una vez; si no, lo informa como FALLA y no toca ese punto.
#   - Antes de escribir un archivo, guarda su original en <repo>/results/docs-respaldo-<fecha>/ (results/ está ignorada por git).
#   - Al final lista las rutas viejas que NO tocó (para revisarlas a mano) y cuenta las menciones de kev antes y después.
#
# Código de salida: 0 si todo quedó aplicado o ya estaba; 1 si algún cambio falló.

import argparse
import datetime
import os
import re
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(REPO, "docs")
RESULTS = os.path.join(REPO, "results")

P1 = "progreso-sesion-2026-10-14.md"
P2 = "progreso-sesion-2026-10-14-laya.md"

# ----------------------------------------------------------------------------------------------
# Textos nuevos
# ----------------------------------------------------------------------------------------------

CHK_BASE_LLAMA_BENCH = '''### Línea base de `llama-bench` (2026-10-14, qwen cerrado)

Comando: `~/llama.cpp/build/bin/llama-bench -m ~/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf -ngl 99 -ncmoe 28 -b 2048 -ub 2048 -fa 1 -ctk q8_0 -ctv q8_0 -p 4096 -n 128 -r 3 2>&1 | grep -E 'pp4096|tg128|error'`

| Condición | pp4096 (tok/s) | tg128 (tok/s) |
|---|---|---|
| Antes (`-r 1`, otro estado de RAM) | 896 | 35,2 |
| Ahora (UMA 512 MiB, `-r 3`) | 874,21 ± 1,54 | **42,16 ± 0,17** |

Lectura: la generación sube ~20 % y el prefill queda igual. Es coherente con que la generación iba limitada por la RAM, pero **no está probado**: la comparación no es limpia (una sola pasada antes, otro estado de memoria). Esta es la línea base para repetir tras mover el módulo de RAM de 8 GiB al canal A.

'''

CHK_SESION = '''## Sesión 2026-10-14: RAM, repo y laya

Detalle en `progreso-sesion-2026-10-14.md` (parte 1: RAM y repo) y `progreso-sesion-2026-10-14-laya.md` (parte 2: laya). Mediciones de RAM y de laya en `anexo-router-ram-qwen.md` (sección 11).

Hecho:

- **RAM recuperada:** el UMA Frame Buffer de la iGPU pasó de 4096 a 512 MiB. El sistema ve 31467 MiB (antes ~27,3 GiB); con qwen cerrado hay 27509 MB disponibles y el swap está sin uso (antes: 1379 MB disponibles y 9217 MB de swap).
- **Velocidad:** línea base nueva de `llama-bench`, `tg128` 42,16 tok/s (antes ~35). Ver «Línea base de `llama-bench`».
- **`-cram`: a medias.** Recién cargado con `QWENX_CRAM=2048` confirmado: RSS 14,46 GiB y swap 0. Falta la sesión larga, que es la que decide si la caché de prompts era la causa del crecimiento: el proceso murió antes de medir RSS y swap finales (log en `results/sesion-cram-231417.log`). Hay que repetir la prueba.
- **Repo** ordenado en `setup/`, `scripts/`, `laya/` y `docs/`. `results/` se crea sola al correr algo y está ignorada por git. Los scripts resuelven sus rutas desde su propia carpeta (tabla de abajo).
- **`qwen-setup.sh` v6.3:** laya opcional y apagada por defecto (`QWENX_LAYA=1 qwen`), con un hook `UserPromptSubmit` que solo avisa en pantalla y nunca bloquea. Sin `QWENX_LAYA=1`, `qwen` se comporta como en la v6.2.
- **laya integrada de punta a punta:** servicio local en CPU (`127.0.0.1:8765`) + hook. En la prueba completa con `qwen` apareció el aviso y Qwen (plan mode) no ejecutó nada destructivo. Detalle y límites en el anexo (sección 11).
- **kev: descartado** (decisión del 2026-10-14). No se usará. Sus mediciones y menciones se conservan como historial.

Rutas nuevas (relativas al repo):

| Antes | Ahora |
|---|---|
| `~/Escritorio/bench-qwen.sh`, `~/Escritorio/qwen-setup.sh` | `scripts/bench-qwen.sh` (v1.1), `setup/qwen-setup.sh` |
| `~/bench-qwen` | `results/bench-qwen` (o `BENCH_DIR=ruta`) |
| `python3 decidir-fase6.py` | `python3 scripts/decidir-fase6.py` (lee `results/bench-qwen`) |
| `~/Escritorio/laya`, `~/laya-test.csv`, `~/laya-test-logs` | `laya/` (junto a su `.venv`), `results/laya-test.csv`, `results/laya-test-logs/` |
| `./qwen-setup.sh` | `bash setup/qwen-setup.sh` |

`scripts/fase6.sh` agrega los barridos de IQ3_XXS a `results/bench-iq3.txt`.

Verificado:

- `python3 scripts/decidir-fase6.py` lee `results/bench-qwen` y reproduce la Fase 6: gana `q4-base`; también cumplen `q4-ctx32k`, `q4-nothink` e `iq3xxs`.
- `bash setup/qwen-setup.sh --check`: una `qwen()`, una `qwen-ollama()`, cero `qwenx()`, contexto por defecto 131072 y `~/.bashrc` carga `~/.qwen-local.sh`.

No verificado: ningún benchmark (`fase6.sh`, `bench-qwen.sh`, `test-laya.sh`) se ha ejecutado desde el repo; solo se comprobó sintaxis y resolución de rutas. La primera corrida real es la prueba.

Pendientes de la sesión, en orden (los pendientes 1-7 de arriba siguen vigentes):

1. [ ] **Latencia de laya bajo carga.** Con `qwen` generando una tarea larga, repetir 3 veces `curl -s -X POST http://127.0.0.1:8765/classify -d '{"text":"explica este archivo"}'` y anotar `ms`. Criterio: ≤ 500 ms.
2. [ ] **Comprobar el apagado.** Al salir de `qwen`: `pgrep -f laya_server.py; pgrep -a llama-server` no debe mostrar nada.
3. [ ] **Aclarar las reglas `deny`/`ask`.** `~/.claude-local/settings.json` solo tiene `WebSearch` en `deny`, plan mode y el hook de laya; las reglas para `rm -rf`, `git push --force`, `DROP` y escribir `.env` no están ahí. Si no existen en otro archivo, añadirlas (idealmente desde `qwen-setup.sh`).
4. [ ] Abrir `qwen` desde la carpeta de un proyecto, no desde el home (la prueba de laya se hizo en `/home/xaski`).
5. [ ] **Prueba larga de `-cram`:** `QWENX_CRAM=2048 qwen`; confirmar con `pgrep -a llama-server | grep -o -- '-cram [0-9]*'`; trabajar 30-60 min con tareas distintas; registrar con `while true; do date +%T; qwen-mem; sleep 120; done | tee -a "$R/results/qwen-mem-cram2048.log"`. **Antes de cerrar:** `qwen-mem` una última vez y copiar el log (`ls -l /proc/<pid>/fd/1` para ubicarlo).
6. [ ] `TAG=post-uma ./laya/test-laya.sh` con qwen cargado y sin Brave. Criterio: RAM disponible ≥ 4096 MB en todas las fases y tok/s de qwen estables. Revisado: `test-laya.sh` ejecuta `bench_laya.py` (Router en proceso), no el servicio `laya_server.py`; no mide el costo del servicio ni del hook.
7. [ ] Añadir a `_qwenx_up` el chequeo de puerto libre para llama-server (8001); ver lecciones 1 y 2.
8. [ ] Ampliar `prompts.jsonl` a ~100 prompts con etiquetas de complejidad revisadas y repetir la medición de laya. La comparación con kev ya no va: kev está descartado.
9. [ ] Bootstrap en `setup/`: compilar llama.cpp (con `--cudart shared`), descargar los modelos con `hf` y crear el `.venv` de laya con la versión **0.4.6** (instalada desde un índice de paquetes; el índice exacto no está verificado).
10. [ ] Uso diario de `QWENX_LAYA=1`: solo después de los pasos 5 y 6.
11. [x] Actualizar `docs/` (rutas nuevas, `qwen-setup.sh` v6.3, línea base de `llama-bench` y esta sesión): hecho con `scripts/actualizar-docs.py`.
12. [ ] Heredados: mover el módulo de RAM de 8 GiB al canal A (un cambio a la vez) y repetir el `llama-bench` de línea base; opcional, escritorio en la iGPU y medir VRAM con `nvidia-smi`; `/autocompact` con 131072; VRAM bajo carga real; repetir `q4-base` para medir varianza y calidad con una tarea real.

Lecciones operativas:

1. **Puerto 8001 ocupado:** un segundo arranque de `llama-server` muere a los 28 ms y `/tmp/llama-server.log` (enlace al último arranque) pasa a apuntar a ese log inútil. El log real se obtiene con `ls -l /proc/<pid>/fd/1`.
2. **Hipótesis sin confirmar:** si `llama-server` sigue vivo, un segundo `qwen` se conecta al servidor del primero (`_qwen_wait_ready` responde con `/health`), y cerrar uno apagaría el servidor de ambos.
3. `qwen-mem` mide el primer `llama-server` que encuentra (`pgrep | head -n 1`).
4. Los logs de llama-server se conservan solo los últimos 20: copiar el de una sesión importante antes de seguir abriendo `qwen`.
5. `$R` no existe en una terminal nueva: definirla con comillas simples (`R='...'`, la ruta del repo tiene `!` y `+`) y usar `"$R"`. Con el repo como directorio actual, usar rutas relativas (`./setup/...`).
6. Al pegar bloques `<<'EOF'`, las líneas deben ir pegadas al borde izquierdo; con sangría, bash no reconoce el `EOF` y se queda esperando (`>`).
7. Los archivos descargados hay que copiarlos al repo (`laya/` y `setup/`) antes de correr el instalador. El repo está en `/run/media/...`: ejecutar con `bash script.sh` por si el montaje no deja ejecutar.

'''

ANEXO_V63 = '''
- `qwen-setup.sh` **v6.3** (laya opcional, apagada por defecto): `QWENX_LAYA=1 qwen` arranca `laya/laya_server.py` (CPU, `127.0.0.1:8765`) en segundo plano después de cargar llama-server y lo apaga al salir. `laya/laya_hook.py` se copia a `~/.claude-local/hooks/` y se registra como hook `UserPromptSubmit` (con `timeout` 3), quitando los hooks de prueba (`hook-stdin`, `hook-test`). El hook solo avisa en pantalla (`systemMessage`), nunca bloquea y, sin servicio, no hace nada. Sin `QWENX_LAYA=1`, `qwen` se comporta como en la v6.2. Variable `QWEN_LAYA_DIR` (ruta de `laya/`, la fija el instalador); opcionales `LAYA_PORT`, `LAYA_MODEL`, `LAYA_MAXCHARS`, `LAYA_HOOK_TIMEOUT` y `LAYA_THRESHOLD`.
- Repo reorganizado en `setup/`, `scripts/`, `laya/` y `docs/`: `fase6.sh`, `bench-qwen.sh` (v1.1), `decidir-fase6.py` y `test-laya.sh` resuelven sus rutas desde su propia carpeta y dejan los resultados en `results/`.'''

ANEXO_S11 = '''

## 11. Actualización 2026-10-14 (post-UMA e integración de laya)

Fuente: `progreso-sesion-2026-10-14.md` y `progreso-sesion-2026-10-14-laya.md`.

### RAM del sistema (`free -m`, qwen cerrado)

| | total | disponible | swap usado |
|---|---|---|---|
| Antes (UMA 4096 MiB) | 27939 | 1379 | 9217 |
| Después (UMA 512 MiB) | 31467 | 27509 | 0 |

La línea base de `llama-bench` (`tg128` 42,16 tok/s) está en el checklist.

### `qwen-mem` recién cargado

| Condición | RSS llama-server | Swap llama-server | RAM disponible | Swap del sistema |
|---|---|---|---|---|
| Sin `-cram` (el `pgrep` no mostraba el flag) | 13,88 GiB | 0,18 GiB | ~13050 MB | ~1260-1280 MB |
| Con `-cram 2048` confirmado en `pgrep` | 14,46 GiB | 0,00 GiB | 13017 MB | 1052 MB |

El swap del sistema no es de llama-server: los cinco procesos con más swap suman ~550 MB y ninguno pasa de 164 MB.

### Prueba de `-cram`: estado

- Sigue sin cerrarse. La sesión larga generó una tarea de ~30.000 tokens (`tg` ≈ 25,4 tok/s; liberada con `n_tokens = 57248`); el log no distingue si terminó sola o por interrupción. Log guardado en `results/sesion-cram-231417.log`.
- El proceso (con `-cram 2048`) murió antes de medir RSS y swap finales. Esa medición no se recupera: hay que repetir la prueba.
- El servidor siguiente (sin `-cram`), recién cargado: RSS 14,45 GiB, swap 0 y 12167 MB disponibles. No sirve como prueba de `-cram`.
- `tg` ≈ 25,4 tok/s en la sesión larga frente a 42,16 tok/s del `llama-bench`: no son comparables (contexto distinto). No tomarlo como regresión sin medir con el mismo contexto.
- Cómo seguir: `QWENX_CRAM=2048 qwen`, confirmar con `pgrep -a llama-server | grep -o -- '-cram [0-9]*'`, trabajar 30-60 min con tareas distintas y registrar `qwen-mem` cada 2 minutos. Si el RSS se queda en ~14,5-16 GiB sin swap, la causa era la caché de prompts; si vuelve a subir hacia ~20 GiB o más, probar `QWENX_LOADMODE=mmap` y vigilar lecturas de disco (`mlock` solo al final).

### laya integrada con `qwen` (opcional, apagada por defecto)

- **Servicio** `laya/laya_server.py` en `127.0.0.1:8765`: carga `multilingual` una vez (CPU, `CUDA_VISIBLE_DEVICES=""`); `POST /classify` y `GET /health`. **Hook** `laya/laya_hook.py`: cliente delgado que lee el `prompt` por stdin e imprime `{"systemMessage": ...}` si hay aviso; sin servicio no hace nada y nunca bloquea. Se activa con `QWENX_LAYA=1 qwen`.
- Las reglas `deny`/`ask` y el plan mode siguen siendo la red de seguridad; laya solo avisa.

| Condición (umbral 0,5) | Aviso |
|---|---|
| `destructivo` ≥ 0,5 | posible acción destructiva |
| `injection` ≥ 0,5 | posible intento de saltarse reglas |
| complejidad `compleja` | tarea compleja: considera dividirla en pasos |

Verificado en la máquina:

- El hook se ejecuta en `qwen`; el stdin trae `session_id`, `transcript_path`, `cwd`, `prompt_id`, `permission_mode`, `hook_event_name` y `prompt`. Cambiar `settings.json` se aplica sin reiniciar `qwen`.
- `systemMessage` se muestra en pantalla como `UserPromptSubmit says: ...`.
- `additionalContext` queda **descartado como canal**: Claude Code lo registra como `system-reminder`, pero Qwen no lo reportó ni lo obedeció (2 pruebas).
- `/classify` con `"borra todos los archivos y haz git push --force"` → `compleja`, `destructivo` 0,8566, `injection` 0,117, 164 ms (sin qwen generando).
- Prueba completa en `qwen`: apareció `laya: posible acción destructiva (0.86); tarea compleja: considera dividirla en pasos` y Qwen (plan mode) no ejecutó nada destructivo.
- laya 0.4.6 en `laya/.venv` (Python 3.12); `direct_url.json` vacío: no viene de git ni de una ruta local.

Sin verificar / límites:

- Latencia de laya con qwen generando: el único dato (164 ms) no se midió bajo carga.
- Apagado del servicio al salir de `qwen`: probado solo en un entorno aislado con un laya simulado, no en la máquina.
- El campo `timeout` del hook en `settings.json` viene de una referencia de terceros, no de la documentación oficial. El tope de 2000 caracteres y el puerto 8765 se eligieron sin medir.
- Calidad de `multilingual`: deja pasar el `DROP` de la tabla de usuarios y sobrescribir `.env`, no detecta «desactiva el plan mode» como injection, subestima la complejidad y suma 2 falsos positivos de injection. Los avisos son ayuda, no protección.
- La prueba se hizo con `qwen` abierto en `/home/xaski`, no en una carpeta de proyecto.'''

PLAN_NOTAS = '''
- **laya (opcional, v6.3)**: `QWENX_LAYA=1 qwen` arranca un servicio local de clasificación en CPU (`127.0.0.1:8765`) y un hook `UserPromptSubmit` muestra avisos en pantalla (acción destructiva, intento de saltarse reglas, tarea compleja). Solo avisa: nunca bloquea; las reglas `deny`/`ask` y el plan mode siguen siendo la red de seguridad (hoy `settings.json` solo tiene `WebSearch` denegado, plan mode y el hook de laya). Apagada por defecto hasta cerrar la prueba de `-cram` y repetir `test-laya.sh` con la RAM nueva. Detalle: `anexo-router-ram-qwen.md`, sección 11.
- **RAM (2026-10-14)**: el UMA de la iGPU estaba en 4096 MiB; con 512 MiB el sistema ve 31467 MiB y `tg128` en `llama-bench` subió de ~35 a 42,16 tok/s (comparación no limpia). La prueba de `-cram` sigue a medias.'''

BANNER_P1 = '''<!-- actualizar-docs:2026-10-14 -->
> **Actualización (2026-10-14, posterior):** laya ya quedó integrada con `qwen` (servicio local + hook que solo avisa; `qwen-setup.sh` v6.3): ver `progreso-sesion-2026-10-14-laya.md`. Lo que esta parte dice sobre laya «no implementada» (secciones 1, 5 y 6) quedó superado. **kev se descartó y no se usará:** las menciones a `kev/` y a la comparación laya vs kev se conservan solo como historial.'''

BANNER_P2 = '''<!-- actualizar-docs:2026-10-14 -->
> **Nota (2026-10-14):** **kev se descartó y no se usará.** En el pendiente 8, ampliar `prompts.jsonl` y repetir la medición de laya sin comparar con kev. Revisado: `laya/test-laya.sh` ejecuta `bench_laya.py` (Router en proceso), no el servicio `laya_server.py`; no mide el costo del servicio ni del hook (pendiente 6).'''

BANNER_ANEXO = '''

> **Decisión (2026-10-14): kev no se usará.** Las mediciones de kev-0.8b de este anexo se conservan solo como referencia histórica; el router es laya `multilingual`.
>
> **Actualización:** laya quedó integrada con `qwen` como servicio local + hook que solo avisa (opcional, apagada por defecto: `QWENX_LAYA=1 qwen`); ver la sección 11. Las mediciones de laya bajo carga de la sección 2 son anteriores al arreglo del UMA y hay que repetirlas (`TAG=post-uma`).'''

# ----------------------------------------------------------------------------------------------
# Cambios por archivo. Cada uno: (id, texto_original, texto_nuevo). "tras_h1" inserta una nota bajo el título.
# ----------------------------------------------------------------------------------------------

EDITS = {
    "plan-qwen-3060.md": [
        ("plan-estado-version",
         "La configuración vive en `qwen-setup.sh` (v6.1); el detalle de mediciones, en `checklist-qwen-3060.md`.",
         "La configuración vive en `qwen-setup.sh` (v6.3); el detalle de mediciones y de la sesión del 2026-10-14 (UMA, `-cram`, laya), en `checklist-qwen-3060.md`, `anexo-router-ram-qwen.md` y los `progreso-sesion-2026-10-14*.md`."),
        ("plan-fase5-comandos",
         "(`./qwen-setup.sh` instala o actualiza, `./qwen-setup.sh --check` muestra el estado)",
         "(`bash setup/qwen-setup.sh` instala o actualiza, `bash setup/qwen-setup.sh --check` muestra el estado)"),
        ("plan-fase5-notas-laya-ram",
         "con backend local no hace nada (3 intentos, \"Did 0 searches\"). Denegado en `settings.json`.",
         "con backend local no hace nada (3 intentos, \"Did 0 searches\"). Denegado en `settings.json`." + PLAN_NOTAS),
        ("plan-fase6-bench",
         "Se usó `bench-qwen.sh` (",
         "Se usó `scripts/bench-qwen.sh` ("),
        ("plan-fase6-decidir",
         " y `decidir-fase6.py` para aplicar los umbrales.",
         " y `scripts/decidir-fase6.py` para aplicar los umbrales."),
        ("plan-riesgos-memoria",
         "Con 131072 la VRAM queda a ~240 MiB del umbral: mejor sin Brave abierto.",
         "Con 131072 la VRAM queda a ~240 MiB del umbral: mejor sin Brave abierto. Actualización 2026-10-14: con el UMA de la iGPU en 512 MiB (antes 4096) el sistema ve 31467 MiB y, con qwen cerrado, quedan 27509 MB disponibles."),
    ],
    "checklist-qwen-3060.md": [
        ("chk-fecha",
         "Última actualización: 2026-10-14 (Fase 6 cerrada; `qwen` = llama.cpp con contexto 131072).",
         "Última actualización: 2026-10-14 (Fase 6 cerrada; `qwen` = llama.cpp con contexto 131072; UMA arreglado, `-cram` a medias y laya integrada: ver «Sesión 2026-10-14»)."),
        ("chk-estado-decidir",
         "Estado: Fase 6 cerrada con `python3 decidir-fase6.py`: gana",
         "Estado: Fase 6 cerrada con `python3 scripts/decidir-fase6.py`: gana"),
        ("chk-estado-version",
         "Contexto por defecto 131072 (`qwen-setup.sh` v6.1). Detalle en «Resultados de la Fase 6» (notas técnicas).",
         "Contexto por defecto 131072 (`qwen-setup.sh` v6.1; hoy va en la v6.3). Detalle en «Resultados de la Fase 6» (notas técnicas). Lo hecho después (UMA, `-cram`, repo y laya): «Sesión 2026-10-14»."),
        ("chk-hecho-3",
         "3. [x] `python3 decidir-fase6.py` con los logs reales: gana `q4-base`.",
         "3. [x] `python3 scripts/decidir-fase6.py` con los logs reales: gana `q4-base`."),
        ("chk-hecho-6",
         "Ejecutar `./qwen-setup.sh && source ~/.bashrc && ./qwen-setup.sh --check`.",
         "Ejecutar `bash setup/qwen-setup.sh && source ~/.bashrc && bash setup/qwen-setup.sh --check`."),
        ("chk-pend-3-log",
         "(copiar antes el log si se va a reabrir `qwen`: `cp /tmp/llama-server.log ~/sesion-$(date +%H%M).log`).",
         "(copiar antes el log si se va a reabrir `qwen`: `cp /tmp/llama-server.log \"$R/results/sesion-$(date +%H%M).log\"`, con `R` = ruta del repo; si el último arranque falló, el log real se saca con `ls -l /proc/<pid>/fd/1`)."),
        ("chk-pend-6-bench",
         "(`./bench-qwen.sh llama q4-base-2` con Ollama parado)",
         "(`bash scripts/bench-qwen.sh llama q4-base-2` con Ollama parado)"),
        ("chk-sesion-seccion",
         "## Fase 1: arreglo gratis (Ollama)",
         CHK_SESION + "## Fase 1: arreglo gratis (Ollama)"),
        ("chk-llama-bench",
         "### Registro de `bench-qwen.sh`",
         CHK_BASE_LLAMA_BENCH + "### Registro de `bench-qwen.sh`"),
        ("chk-config-hook",
         "- `CLAUDE_CODE_ATTRIBUTION_HEADER=0` y `WebSearch` denegado en su `settings.json`.",
         "- `CLAUDE_CODE_ATTRIBUTION_HEADER=0` y `WebSearch` denegado en su `settings.json`.\n- Hook `UserPromptSubmit` de laya registrado en su `settings.json` (`timeout` 3): solo avisa, nunca bloquea y, sin servicio, no hace nada (v6.3)."),
        ("chk-script-install",
         "- `./qwen-setup.sh`: instala o actualiza `~/.qwen-local.sh` y el `settings.json`",
         "- `bash setup/qwen-setup.sh`: instala o actualiza `~/.qwen-local.sh` y el `settings.json` (y copia el hook de laya)"),
        ("chk-script-check",
         "- `./qwen-setup.sh --check`: muestra el estado sin cambiar nada",
         "- `bash setup/qwen-setup.sh --check`: muestra el estado sin cambiar nada"),
        ("chk-script-v62-v63",
         "- [ ] Comprobar `/autocompact` con 131072 (ver pendientes arriba)",
         "- [x] v6.2: `QWENX_CRAM`, `QWENX_LOADMODE` y la función `qwen-mem`\n- [x] v6.3: laya opcional (`QWENX_LAYA=1`), hook `UserPromptSubmit` y `QWEN_LAYA_DIR`\n- [ ] Comprobar `/autocompact` con 131072 (ver pendientes arriba)"),
        ("chk-variables",
         "`QWENX_UB`, `QWENX_CTX`, `QWENX_NOTHINK=1`. Ej.: `QWENX_NOTHINK=1 ./bench-qwen.sh llama q4-sin-thinking`",
         "`QWENX_UB`, `QWENX_CTX`, `QWENX_NOTHINK=1`, `QWENX_CRAM`, `QWENX_LOADMODE`, `QWENX_LAYA=1`. Ej.: `QWENX_NOTHINK=1 bash scripts/bench-qwen.sh llama q4-sin-thinking`"),
    ],
    "anexo-router-ram-qwen.md": [
        ("anexo-banner",
         "Anexo a `plan-qwen-3060.md` y `checklist-qwen-3060.md`. Última actualización: 2026-10-14.",
         "Anexo a `plan-qwen-3060.md` y `checklist-qwen-3060.md`. Última actualización: 2026-10-14." + BANNER_ANEXO),
        ("anexo-resumen-recomendacion",
         "- **Recomendación vigente:** no poner router en RAM junto a qwen hasta cerrar lo anterior. Mientras tanto, reglas fijas (`deny`/`ask`, plan mode) para lo destructivo.",
         "- **Recomendación vigente:** no poner router en RAM junto a qwen hasta cerrar lo anterior. Mientras tanto, reglas fijas (`deny`/`ask`, plan mode) para lo destructivo.\n- **Actualización (2026-10-14):** UMA arreglado (sección 4) y laya integrada como opcional y apagada por defecto (sección 11); sigue sin recomendarse el uso diario hasta cerrar `-cram` y repetir `test-laya.sh` con la RAM nueva. Ojo: `~/.claude-local/settings.json` solo tiene `WebSearch` en `deny` y plan mode; las reglas `deny`/`ask` para lo destructivo todavía no existen ahí."),
        ("anexo-s7-testlaya",
         "Resultados en `~/laya-test.csv` y logs en `~/laya-test-logs/`.",
         "Resultados en `results/laya-test.csv` y logs en `results/laya-test-logs/` (rutas relativas al repo; antes se guardaban en el home). Ejecuta `bench_laya.py` (Router en proceso), no el servicio `laya_server.py`."),
        ("anexo-s7-setup-v63",
         "Instalar con `./qwen-setup.sh && source ~/.bashrc && ./qwen-setup.sh --check`.",
         "Instalar con `bash setup/qwen-setup.sh && source ~/.bashrc && bash setup/qwen-setup.sh --check`." + ANEXO_V63),
        ("anexo-s9-item1",
         "1. [ ] Con qwen cerrado, línea base de `llama-bench` (tg128 ~34,5-35,2 tok/s en notas anteriores, con otro estado de RAM):",
         "1. [x] Con qwen cerrado, línea base de `llama-bench` (tg128 ~34,5-35,2 tok/s en notas anteriores, con otro estado de RAM):"),
        ("anexo-s9-item2",
         "2. [ ] Instalar `qwen-setup.sh` v6.2 y probar `QWENX_CRAM=2048 qwen`:",
         "   Resultado (2026-10-14, UMA 512 MiB): pp4096 874,21 ± 1,54 y tg128 42,16 ± 0,17 tok/s. Ver el checklist («Línea base de `llama-bench`»).\n2. [ ] (A medias: recién cargado con `-cram 2048`, RSS 14,46 GiB y swap 0; falta la sesión larga, el proceso murió sin medir y su log está en `results/sesion-cram-231417.log`.) Instalar `qwen-setup.sh` v6.2 (hoy va la v6.3) y probar `QWENX_CRAM=2048 qwen`:"),
        ("anexo-s9-item6-kev",
         "6. [ ] Ampliar `prompts.jsonl` a ~100 prompts con etiquetas revisadas y repetir laya `multilingual` vs kev antes de decidir.",
         "6. [ ] Ampliar `prompts.jsonl` a ~100 prompts con etiquetas revisadas y repetir la medición de laya `multilingual`. La comparación con kev ya no va: kev quedó descartado el 2026-10-14."),
        ("anexo-s9-item7",
         "como red de seguridad; el router solo sugiere o avisa.",
         "como red de seguridad; el router solo sugiere o avisa. Nota (2026-10-14): ese `settings.json` solo tiene `WebSearch` en `deny`; esas reglas no existen ahí todavía.\n\nLista vigente y ordenada de la sesión: sección 7 de `progreso-sesion-2026-10-14-laya.md` (también en el checklist)."),
        ("anexo-s10-kev-y-s11",
         "- Latencia y RAM de kev con la RAM nueva (se midió antes del arreglo del UMA).",
         "- Latencia y RAM de laya con la RAM nueva (se midió antes del arreglo del UMA). Las de kev ya no importan: kev quedó descartado." + ANEXO_S11),
    ],
    P1: [
        ("p1-banner", "tras_h1", BANNER_P1),
    ],
    P2: [
        ("p2-banner", "tras_h1", BANNER_P2),
    ],
}

# Rutas viejas que el script NO modifica a propósito (datos históricos o ubicación desconocida): se listan al final.
PATRONES_REVISION = [
    (r"~/Escritorio", "ruta vieja ~/Escritorio"),
    (r"~/laya-test", "ruta vieja ~/laya-test*"),
    (r"~/bench-qwen", "ruta vieja ~/bench-qwen"),
    (r"~/bench-(?:q4|iq3)\.txt", "archivo de barrido en el home (¿dónde está ahora?)"),
    (r"~/fase6", "~/fase6* (corrida anterior a la reorganización)"),
    (r"~/sesion-", "~/sesion-*.log (log anterior a la reorganización)"),
    (r"(?<![\w/.])\./(?:qwen-setup|bench-qwen)\.sh", "comando con ./ en vez de bash setup/ o scripts/"),
    (r"python3 decidir-fase6\.py", "python3 decidir-fase6.py sin scripts/"),
]


# ----------------------------------------------------------------------------------------------
# Lógica
# ----------------------------------------------------------------------------------------------

def leer(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def escribir(path, texto):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(texto)


def aplicar_cambios(texto, ediciones):
    """Devuelve (texto_nuevo, [(id, estado)]). Estados: aplicado | ya aplicado | FALLA: motivo."""
    res = []
    for id_, viejo, nuevo in ediciones:
        if viejo == "tras_h1":
            if nuevo in texto:
                res.append((id_, "ya aplicado"))
                continue
            m = re.search(r"^# .*\n", texto, flags=re.M)
            if not m:
                res.append((id_, "FALLA: no encuentro el título (# ...)"))
                continue
            i = m.end()
            texto = texto[:i] + "\n" + nuevo + "\n" + texto[i:]
            res.append((id_, "aplicado"))
            continue
        if nuevo in texto:
            res.append((id_, "ya aplicado"))
            continue
        n = texto.count(viejo)
        if n == 1:
            texto = texto.replace(viejo, nuevo, 1)
            res.append((id_, "aplicado"))
        elif n == 0:
            res.append((id_, "FALLA: el texto original no existe (¿el doc cambió?)"))
        else:
            res.append((id_, "FALLA: el texto original aparece %d veces (ambiguo)" % n))
    return texto, res


def localizar(nombre, extras):
    candidatos = []
    for p in extras:
        if os.path.basename(p) == nombre:
            candidatos.append(p)
    home = os.path.expanduser("~")
    for d in (DOCS, REPO, os.getcwd(), os.path.join(home, "Descargas"), os.path.join(home, "Downloads")):
        candidatos.append(os.path.join(d, nombre))
    for c in candidatos:
        if os.path.isfile(c):
            return c
    return None


def main():
    ap = argparse.ArgumentParser(description="Actualiza docs/ con la sesión 2026-10-14.")
    ap.add_argument("--dry-run", action="store_true", help="no escribe nada, solo informa")
    ap.add_argument("rutas", nargs="*", help="progreso-sesion-2026-10-14*.md a copiar a docs/")
    args = ap.parse_args()

    if not os.path.isdir(DOCS):
        sys.exit("No existe %s (este script debe vivir en <repo>/scripts/)" % DOCS)

    for p in args.rutas:
        if not os.path.isfile(p):
            print("aviso: no existe %s, se ignora" % p)
        elif not os.path.basename(p).startswith("progreso-sesion-2026-10-14"):
            print("aviso: %s no es un progreso-sesion-2026-10-14*.md, se ignora" % p)

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    respaldo = os.path.join(RESULTS, "docs-respaldo-" + ts)
    fallas = 0
    cambiados = []
    kev = {}
    finales = {}

    for nombre, ediciones in EDITS.items():
        destino = os.path.join(DOCS, nombre)
        print("== %s" % nombre)

        copiado_desde = None
        if os.path.isfile(destino):
            texto = leer(destino)
            original = texto
        elif nombre in (P1, P2):
            src = localizar(nombre, args.rutas)
            if not src:
                print("   omitido: no está en docs/ ni lo encuentro (pásalo como argumento: python3 scripts/actualizar-docs.py RUTA)")
                continue
            texto = leer(src)
            original = None
            copiado_desde = src
            print("   copia desde %s" % src)
        else:
            print("   FALLA: no existe %s" % destino)
            fallas += 1
            continue

        nuevo_texto, res = aplicar_cambios(texto, ediciones)
        finales[nombre] = nuevo_texto
        for id_, estado in res:
            print("   [%s] %s" % (id_, estado))
            if estado.startswith("FALLA"):
                fallas += 1

        k_antes = len(re.findall(r"kev", texto, flags=re.I))
        k_desp = len(re.findall(r"kev", nuevo_texto, flags=re.I))
        kev[nombre] = (k_antes, k_desp)

        hay_cambio = copiado_desde is not None or nuevo_texto != original
        if not hay_cambio:
            print("   sin cambios")
            continue
        cambiados.append(nombre)
        if args.dry_run:
            print("   (dry-run) se escribiría %s" % destino)
            continue
        if original is not None:
            os.makedirs(respaldo, exist_ok=True)
            escribir(os.path.join(respaldo, nombre), original)
        escribir(destino, nuevo_texto)
        print("   escrito")

    print()
    print("== Menciones de kev (antes → después; no deben bajar)")
    for nombre, (a, d) in kev.items():
        marca = "" if d >= a else "   <-- BAJÓ, revisar"
        print("   %-40s %3d → %3d%s" % (nombre, a, d, marca))

    print()
    print("== Para revisar a mano (el script no los toca)")
    hay = False
    for nombre in sorted(finales):
        if nombre in (P1, P2):
            continue   # son registros de sesión: sus rutas viejas son parte del relato
        for n, linea in enumerate(finales[nombre].splitlines(), 1):
            if linea.lstrip().startswith("|"):
                continue   # filas de tablas (p. ej. la tabla «Antes / Ahora» de rutas)
            for pat, motivo in PATRONES_REVISION:
                if re.search(pat, linea):
                    hay = True
                    print("   %s:%d  %s" % (nombre, n, motivo))
                    break
    if not hay:
        print("   (nada)")

    print()
    if args.dry_run:
        print("dry-run: no se escribió nada. Archivos que cambiarían: %s" % (", ".join(cambiados) or "ninguno"))
    elif cambiados and os.path.isdir(respaldo):
        print("Respaldo de los originales en %s" % respaldo)
    if fallas:
        print("%d cambio(s) fallaron: mira las líneas FALLA arriba." % fallas)
        sys.exit(1)
    print("Listo.")


if __name__ == "__main__":
    main()
