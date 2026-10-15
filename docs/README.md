# Qwen3.6-35B-A3B local · Pi + llama.cpp + laya

Entorno local para usar **Qwen3.6-35B-A3B** desde la terminal con el harness **Pi**, sirviendo el modelo con **llama.cpp** (`llama-server`) y acompañado opcionalmente por **laya** (clasificador de prompts en CPU). Se maneja con un **menú TUI** (`qwen`) o con comandos directos.

> Estado del documento: refleja el código entregado hasta la última modificación (opción Laya en el menú, estado online/offline, apagado del servidor y configuración única de laya).

---

## Índice

1. [Vista rápida](#1-vista-rápida)
2. [Estructura de la repo](#2-estructura-de-la-repo)
3. [Instalación](#3-instalación)
4. [Uso diario](#4-uso-diario)
5. [El menú TUI](#5-el-menú-tui)
6. [Modelos](#6-modelos)
7. [Opciones del menú](#7-opciones-del-menú)
8. [Laya (system 1)](#8-laya-system-1)
9. [Pi: perfiles, herramientas y subagentes](#9-pi-perfiles-herramientas-y-subagentes)
10. [Cómo funciona por dentro](#10-cómo-funciona-por-dentro)
11. [Referencia de módulos](#11-referencia-de-módulos)
12. [Variables de entorno](#12-variables-de-entorno)
13. [Solución de problemas](#13-solución-de-problemas)
14. [Limitaciones y pendientes](#14-limitaciones-y-pendientes)
15. [Historial de cambios](#15-historial-de-cambios)

---

## 1. Vista rápida

```bash
./setup/qwen-setup.sh      # una sola vez
source ~/.bashrc
qwen                       # abre el menú
```

| Quiero… | Comando |
|---|---|
| Abrir el menú | `qwen` |
| Menú con Heretic ya marcado | `qwenh` |
| Lanzar directo con un prompt | `qwen -p "resume este repo"` |
| Ver estado de todo | `qwen-status` |
| Ver memoria de llama-server | `qwen-mem` |
| Apagar un servidor colgado | `qwen-stop` (o tecla `x` en el menú) |

---

## 2. Estructura de la repo

```
qwen-local.sh            Punto de entrada. ~/.qwen-local.sh es un symlink a este archivo.
lib/
  config.sh              Rutas, puertos, valores por defecto, resolución de modelos.
  laya.sh                Ciclo de vida de laya (arrancar / parar / modo solo).
  llama.sh               llama-server, Ollama (respaldo), qwen-mem, qwen-stop.
  pi.sh                  Config de Pi, perfiles de herramientas, ejecución.
menu/
  qwen-menu.py           Menú TUI (solo librería estándar de Python, sin venv).
setup/
  qwen-setup.sh          Instalador corto: symlink + config de Pi + venv de laya + ~/.bashrc.
laya/                    Clasificador de prompts (ya existía):
  laya_server.py         Servidor HTTP (/health, /classify), carga el Router una vez.
  laya_hook.py           Hook de Claude Code (NO lo usa Pi, ver §8).
  bench_laya.py          Benchmark directo.
  test-laya.sh           Prueba bajo carga real de Qwen.
  questions.json         Preguntas de laya (única copia: servidor y bench la leen).
  config.json            Checkpoint, recorte de texto y umbrales de aviso.
  laya_config.py         Lector común de questions.json y config.json (solo biblioteca estándar).
  run.sh  prompts.jsonl  laya.md
commands.md              Notas sueltas (monitor de tokens/s, descarga de heretic).
plan.md                  Plan antiguo de symlinks (reemplazado por este diseño).
```

Fuera de la repo (generado por el instalador o en uso):

| Ruta | Contenido |
|---|---|
| `~/.qwen-local.sh` | Symlink → `<repo>/qwen-local.sh` |
| `~/.pi-qwen/agent/` | `models.json` y `settings.json` de Pi (separado de `~/.pi/agent`) |
| `~/.local/share/qwen/laya-venv` | venv de laya (si no existe `laya/.venv`) |
| `~/.local/state/qwen/menu.json` | Última selección del menú |
| `~/models/*.gguf` | Modelos |
| `~/llama.cpp/build/bin/llama-server` | Binario de llama.cpp |

No se crean logs persistentes de llama-server, laya ni Ollama.

---

## 3. Instalación

Requisitos: `bash`, `python3`, `curl`, `pi` en el `PATH`, llama.cpp compilado y los GGUF en `~/models`.

```bash
./setup/qwen-setup.sh              # instala / actualiza
./setup/qwen-setup.sh --check      # revisa sin modificar nada
./setup/qwen-setup.sh --no-laya    # sin preparar el venv de laya
./setup/qwen-setup.sh --uninstall  # quita symlink y línea de ~/.bashrc
```

El instalador hace cinco cosas:

1. Crea el symlink `~/.qwen-local.sh` → `<repo>/qwen-local.sh` (si había un archivo real, lo respalda como `.bak-<fecha>`).
2. Genera/actualiza la config de Pi en `~/.pi-qwen/agent` (conserva lo que ya tengas; no toca `~/.pi/agent`).
3. Prepara el venv de laya (necesita red solo la primera vez).
4. Deja **una sola línea** en `~/.bashrc` y elimina las de versiones anteriores.
5. Limpia logs del instalador viejo y te indica qué restos puedes borrar (`~/.local/share/qwen/qwen-menu.py`, `~/.local/share/qwen/rich-venv`).

Después: `source ~/.bashrc`.

---

## 4. Uso diario

**Sin argumentos abre el menú; con argumentos lanza directo** y pasa todo a `pi`.

| Comando | Modelo | Opciones preseleccionadas en el menú |
|---|---|---|
| `qwen` | Base | lo último que usaste |
| `qwen-edit` | Base | Edición |
| `qwen-incognito` | Base | Incógnito |
| `qwen-edit-incognito` | Base | Edición + Incógnito |
| `qwen-vision` | Base | Visión |
| `qwen-vision-incognito` | Base | Visión + Incógnito |
| `qwenh` y variantes `-edit`, `-incognito`, `-edit-incognito`, `-vision`, `-vision-incognito` | Heretic | igual que arriba |
| `qwen-lite` | IQ3_XXS | — |
| `qwen-ollama` | (ignora el modelo) | Ollama |

Ejemplos de lanzamiento directo (sin menú):

```bash
qwen -p "resume este repo"        # Base, solo lectura
qwen-edit -p "arregla el bug X"   # Base, con write/edit/bash
qwenh-incognito                   # abre el menú con Heretic + Incógnito
```

Los presets de los comandos **no apagan Laya**, salvo que la desmarques tú en el menú.

Utilidades:

| Comando | Qué hace |
|---|---|
| `qwen-status` | Estado de pi, llama-server, modelos, mmproj, puertos, laya y JSON de Pi |
| `qwen-mem` | RAM/swap que usa llama-server |
| `qwen-stop` | Apaga llama-server y laya (TERM; si no cierra en ~6 s, KILL) |

---

## 5. El menú TUI

Diseñado para ser liviano y colorido, sin dependencias (nada de `rich` ni venv). Dibuja en `/dev/tty`, usa pantalla alternativa y al salir deja la terminal limpia.

```
╭──────────────────────────────────────────────────────────────────────╮
│ ◆ QWEN3.6-35B  pi · llama.cpp · laya                                 │
│ ○ llama-server offline :8001   ○ laya offline :8765                  │
├─ Modelo ─────────────────────────────────────────────────────────────┤
│ ◉ 1 Base     Q4_K_XL · MoE 35B-A3B                           20.0 GB │
│ ○ 2 Heretic  uncensored Q4_K_M                               19.8 GB │
│ ○ 3 IQ3      ligero IQ3_XXS                            no encontrado │
├─ Opciones ───────────────────────────────────────────────────────────┤
│ [✓] e Edición   write · edit · bash                                  │
│ [ ] v Visión    mmproj F16                                           │
│ [ ] i Incógnito sin guardar sesión                                   │
│ [ ] o Ollama    respaldo · ignora el modelo                          │
│ [✓] s Laya      system 1 · clasifica prompts en CPU                  │
│   ! Pi podrá escribir y ejecutar bash: solo en proyectos de confianza│
├─ Argumentos para pi ─────────────────────────────────────────────────┤
│ › opcional · ej: -p "resume este repo"                             a │
├──────────────────────────────────────────────────────────────────────┤
│ ▶ Lanzar                                  base · edición · laya      │
╰──────────────────────────────────────────────────────────────────────╯
```

(Ilustración aproximada; los colores y el aspecto exacto son los de tu captura.)

**Teclas**

| Tecla | Acción |
|---|---|
| `↑` `↓` (o `k` `j`) | Mover el foco |
| `espacio` | Seleccionar modelo / marcar opción / editar argumentos / lanzar (según la fila) |
| `enter` | Lanzar (en la fila de argumentos, editarlos) |
| `1`–`3` | Elegir modelo |
| `e` `v` `i` `o` `s` | Marcar Edición / Visión / Incógnito / Ollama / Laya |
| `a` | Editar argumentos para pi (`enter` acepta, `esc` cancela, `ctrl+u` borra) |
| `m` | `qwen-mem` |
| `c` | `qwen-status` |
| `l` | Laya en modo independiente (hasta pulsar Enter) |
| `x` | **Apagar** llama-server y laya (descarga el modelo) |
| `r` | Releer modelos y puertos |
| `q` / `esc` | Salir |

**Estado en vivo:** la segunda línea muestra `online` (verde) / `offline` (gris) de llama-server y laya, y se refresca cada segundo. Si un servidor quedó colgado de una sesión anterior, lo ves nada más abrir el menú y lo apagas con `x`.

**Recuerda tu selección** en `~/.local/state/qwen/menu.json` (modelo, opciones y argumentos). La primera vez vienen marcadas **Edición** y **Laya**.

**Validaciones al lanzar:** si falta el GGUF del modelo elegido, o falta el `mmproj` con Visión marcada, el menú muestra un aviso y no lanza.

**Cómo le habla a bash:** el menú imprime en stdout asignaciones con `shlex.quote` y `qwen-local.sh` hace `eval`:

```
ACTION=launch|mem|status|laya|quit
MODEL_ID=…  MODEL_PATH=…
OPT_EDIT=0|1  OPT_VISION=0|1  OPT_INCOGNITO=0|1  OPT_OLLAMA=0|1  OPT_LAYA=0|1
MMPROJ_PATH=…   PI_ARGS=…
```

---

## 6. Modelos

Los tres son **el mismo Qwen3.6-35B-A3B** en distinta cuantización o variante. Se usa **uno solo a la vez**; no se complementan.

| Modelo | Archivo (patrón en `~/models`) | Para qué |
|---|---|---|
| **Base** · Q4_K_XL (~20.8 GB) | `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf` | Mejor calidad. Uso normal. |
| **Heretic** · Q4_K_M (~20.3 GB) | `*heretic*Q4_K_M*.gguf` | Variante uncensored/abliterada. |
| **IQ3** · IQ3_XXS (~12.3 GB) | `*IQ3_XXS*.gguf` | Más pequeño: carga más rápido y deja VRAM/RAM libre, a cambio de algo de calidad. |
| mmproj (visión) | `mmproj-*F16*.gguf` | Solo con la opción Visión. |

El IQ3 **no** es un modelo “borrador” para acelerar al grande (decodificación especulativa); eso no está montado. Si no lo necesitas, ignóralo o quita su línea de `MODELS` en `menu/qwen-menu.py`.

Si un modelo aparece como `no encontrado`, revisa `ls ~/models/*.gguf` y que el nombre contenga el patrón de la tabla. Descarga de heretic: ver `commands.md`.

`QWENX_MODEL` y `QWENX_MMPROJ` (si los exportas) sobreescriben la ruta del modelo Base y del mmproj.

---

## 7. Opciones del menú

| Opción | Efecto |
|---|---|
| **Edición** (`e`) | Perfil `edit` de Pi: añade `write`, `edit` y `bash`. Sin ella, solo lectura. |
| **Visión** (`v`) | Arranca llama-server con `--mmproj … --no-mmproj-offload`. |
| **Incógnito** (`i`) | Pi con `--no-session`: no guarda la sesión. |
| **Ollama** (`o`) | Usa Ollama (`127.0.0.1:11434`, modelo `qwen3.6:35b`) en vez de llama.cpp; ignora el modelo elegido. |
| **Laya** (`s`) | Arranca laya junto al modelo (por defecto activada). Ver §8. |

> **Cuidado con Edición:** da a Pi escritura y `bash` sin las antiguas reglas deny/ask de Claude Code. Úsala solo en proyectos de confianza.

---

## 8. Laya (system 1)

Laya es un clasificador no autoregresivo (`laya` 0.4.6, `Router`) que corre **en CPU** (no toca VRAM) y evalúa cada prompt en un solo paso:

- **complejidad:** simple / media / compleja
- **destructivo:** probabilidad de que pida borrar/sobreescribir/force-push
- **injection:** probabilidad de que intente saltarse las reglas

`laya_server.py` carga el Router una vez y expone `GET /health` y `POST /classify` en `127.0.0.1:8765`.

**Configuración única:** las preguntas viven en `laya/questions.json` y el resto en `laya/config.json` (`model`, `maxchars`, `thresholds`). Servidor, bench y hook las leen a través de `laya/laya_config.py`. Precedencia: variable de entorno > `config.json`. `bench_laya.py` sin argumento usa el `model` de `config.json`. Los umbrales (0.5) y el recorte (2000) son provisionales: aún no están medidos.

**Qué hace hoy el proyecto**

- Con la casilla **Laya** marcada (o `QWEN_LAYA=1`, el valor por defecto), laya **arranca después de que Qwen está listo** y se **apaga junto con la sesión**, con llama.cpp y también con Ollama.
- Si laya falla o falta, **se avisa y Qwen sigue funcionando**.
- Solo se mata el laya que arrancó esa sesión; uno ya corriendo se respeta.
- Para desactivarla: desmarcar la casilla, o `QWEN_LAYA=0 qwen`.

**Qué NO hace todavía:** Pi **no consulta** a laya. El `laya_hook.py` es un hook `UserPromptSubmit` de **Claude Code**, y Pi no lo usa. Hoy laya queda levantado esperando peticiones, pero ningún prompt pasa por él. Para que actúe de verdad como “system 1” (avisar de acciones destructivas o inyección, o elegir perfil) falta conectarlo con el mecanismo de extensiones/hooks de Pi (ver §14).

Pendientes de calibración de laya (de `laya/laya.md`): ampliar `prompts.jsonl` a ~100 prompts, medir accuracy, calibrar con `fit_temperatures`, decidir checkpoint (`typed-decisions` vs `multilingual`). Criterios de éxito: acuerdo ≥ 80 %, latencia mediana ≤ 500 ms, RAM pico ≤ 2048 MB, VRAM sin cambios. El plan completo de refinamiento está en `refinar-laya.md`.

---

## 9. Pi: perfiles, herramientas y subagentes

Pi se ejecuta con `PI_CODING_AGENT_DIR=~/.pi-qwen/agent`, separado de tu config habitual.

| Perfil | `--tools` |
|---|---|
| `readonly` (por defecto) | `read,grep,find,ls` |
| `edit` | `read,write,edit,bash,grep,find,ls` |

`lib/pi.sh` genera `models.json` (proveedores `qwen-local` y `qwen-ollama`) y `settings.json` (herramientas por defecto de solo lectura, compactación activada). En cada lanzamiento sincroniza el tamaño de contexto de Pi con el de llama-server (`QWENX_CTX`, 120000 por defecto).

**Sin subagentes:** Pi no trae una herramienta de subagentes. Como `--tools` es una **lista cerrada**, solo existen las herramientas listadas y todo ocurre en la sesión principal. Si instalas una extensión de Pi que añada subagentes, habría que revisarlo aparte. (En Claude Code esa regla iría en `deny`, no en `ask`.)

**Argumentos del menú:** el texto de “Argumentos para pi” se divide con `shlex` **sin evaluar nada**, así `-p "resume este repo"` llega bien y un `$(...)` no se ejecuta.

---

## 10. Cómo funciona por dentro

```
qwen ──► qwen-local.sh ──► _qwen_entry
            │                 ├─ sin args ─► _qwen_menu ─► qwen-menu.py ─► eval(ACTION…)
            │                 └─ con args ─► _qwen_launch
            ▼
   ACTION=launch ─► _qwen_run_local (o _qwen_run_ollama)
                       1. _qwen_pi_prepare   sincroniza contexto en models.json/settings.json
                       2. _qwenx_up          libera :8001 si hace falta → llama-server → espera /health
                       3.   └─ _laya_up      (si Laya activada) laya → espera /health
                       4. _qwen_pi           pi --provider … --model … --tools … [--no-session]
                       5. _qwenx_down        apaga laya y llama-server
```

Carga de módulos (en este orden): `config` → `laya` → `llama` → `pi`.

Detalles de `llama-server`: `-ngl 99 --n-cpu-moe 28 -c 120000 -b 2048 -ub 512 -fa on -ctk q8_0 -ctv q8_0 --jinja --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0.0 -cram 2048`, host `127.0.0.1`, puerto 8001, alias `qwen3.6-35b`. Si el puerto está ocupado por un llama-server anterior, lo cierra y espera a que se libere; si lo ocupa otro proceso, aborta con aviso.

`Ctrl+C` durante la espera de arranque cancela y apaga lo levantado.

---

## 11. Referencia de módulos

### `lib/config.sh`
Variables (ver §12) y dos funciones: `_qwen_model_path base|heretic|iq3` y `_qwen_mmproj_path` (mismos patrones glob que el menú). No ejecuta nada.

### `lib/laya.sh`
`_laya_up` · `_laya_down` · `_laya_standalone` · `_laya_ensure_venv` · `_laya_port_open` · `_laya_healthy`.

### `lib/llama.sh`
`_qwenx_up` / `_qwenx_down` (llama.cpp) · `_qwen_up` / `_qwen_down` (Ollama) · `_qwen_wait_ready` · `_qwen_free_port` · `_qwen_port_open` · `qwen-mem` · `qwen-stop`.
Mantiene el contrato que usa `bench-qwen.sh` (`_qwenx_up/_qwenx_down` y `_qwen_up/_qwen_down`).

### `lib/pi.sh`
`_qwen_pi_init` (genera la config de Pi) · `_qwen_pi_prepare` (sincroniza contexto) · `_qwen_split_args` · `_qwen_pi` · `_qwen_run_local` · `_qwen_run_ollama`.

### `qwen-local.sh`
`qwen-status` · `_qwen_launch` · `_qwen_menu` · `_qwen_entry` y los comandos públicos (§4).

### `menu/qwen-menu.py`
Clases/funciones principales: `Menu` (estado, dibujo y bucle de teclas), `Tty` (terminal en modo cbreak), `stop_servers`, `find_model`, `find_mmproj`, `port_open`. Acepta presets por entorno (`QWEN_MENU_MODEL`, `QWEN_MENU_OPTS`, con `nolaya` para apagar Laya).

### `setup/qwen-setup.sh`
Instalador (§3). `--check`, `--no-laya`, `--uninstall`.

---

## 12. Variables de entorno

Todas son opcionales.

| Variable | Defecto | Uso |
|---|---|---|
| `QWEN_ROOT` | (auto) | Raíz de la repo |
| `QWEN_DATA` | `~/.local/share/qwen` | Datos de usuario (venv de laya) |
| `QWEN_LLAMA_BIN` | `~/llama.cpp/build/bin/llama-server` | Binario de llama.cpp |
| `QWEN_MODELS_DIR` | `~/models` | Carpeta de GGUF |
| `QWEN_PORT` | `8001` | Puerto de llama-server (también lo lee el menú) |
| `QWEN_ALIAS` | `qwen3.6-35b` | Alias del modelo |
| `QWENX_MODEL` | — | Ruta del modelo Base |
| `QWENX_MMPROJ` | — | Ruta del mmproj |
| `QWENX_CTX` | `120000` | Contexto |
| `QWENX_NCMOE` | `28` | `--n-cpu-moe` |
| `QWENX_BATCH` / `QWENX_UB` | `2048` / `512` | `-b` / `-ub` |
| `QWENX_CRAM` | `2048` | `-cram` |
| `QWENX_LOADMODE` | `none` | `--load-mode` |
| `QWENX_NOTHINK` | `0` | `1` desactiva el thinking |
| `QWENX_READY_TIMEOUT` | `900` | Segundos de espera de `/health` |
| `QWEN_PI_DIR` | `~/.pi-qwen/agent` | Config de Pi |
| `QWEN_PI_PROVIDER` | `qwen-local` | Proveedor de Pi |
| `QWEN_PI_TOOLS_RO` / `QWEN_PI_TOOLS_EDIT` | ver §9 | Herramientas por perfil |
| `QWEN_PI_NO_SESSION` | `0` | `1` = Pi sin guardar sesión |
| `QWEN_OLLAMA_URL` / `QWEN_OLLAMA_MODEL` / `QWEN_OLLAMA_CTX` | `http://127.0.0.1:11434` / `qwen3.6:35b` / `32768` | Respaldo Ollama |
| `QWEN_OLLAMA_STOP` | `1` | Hace `ollama stop` al terminar |
| `QWEN_LAYA` | `1` | `0` = no arrancar laya |
| `LAYA_DIR` / `LAYA_VENV` | `<repo>/laya` / `laya/.venv` o `$QWEN_DATA/laya-venv` | Ubicación de laya |
| `LAYA_PORT` | `8765` | Puerto de laya |
| `LAYA_MODEL` | (vacío: el de `laya/config.json`) | Pisa el checkpoint |
| `LAYA_MAXCHARS` | (el de `laya/config.json`) | Pisa el recorte de texto |
| `LAYA_THRESHOLD` | (los de `laya/config.json`) | Pisa los umbrales de destructivo/injection (hook y bench) |
| `LAYA_TIMEOUT` | `30` | Segundos de espera de laya |
| `QWEN_MENU` | `<repo>/menu/qwen-menu.py` | Ruta del menú |
| `QWEN_MENU_MODEL` / `QWEN_MENU_OPTS` | — | Presets del menú |

---

## 13. Solución de problemas

| Síntoma | Qué hacer |
|---|---|
| Quedó un servidor colgado / no se libera la VRAM | Menú → `x`, o `qwen-stop`. Manual: `pkill -TERM -f '/home/<tú>/llama.cpp/build/bin/llama-server'` |
| `El puerto 8001 está ocupado por otro proceso` | Algo que no es llama-server usa el puerto. Cámbialo con `QWEN_PORT` o libera el puerto. |
| Error 500 | Probar `QWENX_NOTHINK=1 qwen` (anotado en `commands.md`). |
| Modelo `no encontrado` en el menú | `ls ~/models/*.gguf` y revisa que el nombre contenga el patrón de §6. |
| Visión no lanza | Falta `mmproj-*F16*.gguf` en `~/models`. |
| `No encuentro el comando 'pi'` | Instala Pi o añádelo al `PATH`. |
| Laya no arranca | Se avisa y todo sigue sin laya. Revisa `qwen-status`; la primera vez necesita red para crear el venv. |
| El menú no se ve bien | Necesita terminal con 256 colores y UTF-8, y al menos ~72 columnas. |
| `qwen` sigue apuntando a otra cosa | El `~/.bashrc` ya hace `unalias` de nombres antiguos; abre una terminal nueva o `source ~/.bashrc`. |
| Algo no cuadra tras instalar | `./setup/qwen-setup.sh --check` |

Monitor de tokens/s y comandos de descarga/medición: ver `commands.md`.

---

## 14. Limitaciones y pendientes

- **Laya no está conectada a Pi.** Corre en paralelo pero nada la consulta. Para integrarla hay que usar el sistema de extensiones/hooks de Pi (hoy solo existe el hook de Claude Code).
- Los cambios entregados se comprobaron **solo con `bash -n` / `py_compile`**; no se hicieron pruebas de ejecución completas. Esto incluye la configuración única de laya: no se ha arrancado el servidor con la config nueva.
- No se pudo leer la conversación anterior truncada (enlace compartido); el diseño se basó en el zip, `plan.md` y la memoria del proyecto.
- Ideas mencionadas pero **fuera de esta repo** y sin implementar: delegar tareas a Qwen local desde Claude Pro, y hacer un fine-tune destilado de Qwen3.6-35B-A3B.
- `plan.md` quedó obsoleto: el diseño final deja los venvs fuera de la repo y no copia el menú a `~/.local/share`.

---

## 15. Historial de cambios

| Paso | Cambio |
|---|---|
| 1 | `menu/qwen-menu.py`: menú TUI sin dependencias, con la apariencia de la captura. |
| 2 | `lib/config.sh`: rutas, puertos y resolución de modelos. |
| 3 | `lib/laya.sh` y `lib/llama.sh`: ciclo de vida de laya y llama-server. Corrección del chequeo de puerto (había un espacio en `/dev/tcp/...`). |
| 4 | `lib/pi.sh`: config de Pi, perfiles, división segura de argumentos. |
| 5 | `qwen-local.sh`: entrada, comandos y menú; presets de menú en `qwen-menu.py`. |
| 6 | `setup/qwen-setup.sh`: instalador corto con symlinks (reemplaza al de ~1000 líneas). |
| 7 | Menú: estado **online/offline** en vivo, tecla **`x`** para apagar el servidor, y comando `qwen-stop`. |
| 8 | Menú: opción **Laya** (activada por defecto) y arranque de laya también con Ollama. |
| 9 | El menú lee `QWEN_PORT` (antes `QWEN_LLAMA_PORT`) para coincidir con `lib/config.sh`. |
| 10 | Laya: configuración única (`laya/questions.json`, `laya/config.json`, `laya/laya_config.py`); servidor, bench y hook la leen. `LAYA_MODEL` ya no tiene valor por defecto en `lib/config.sh`. |
