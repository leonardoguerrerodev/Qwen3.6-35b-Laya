# Checklist: Qwen3.6-35B-A3B en RTX 3060 12 GB + 32 GB RAM

Basado en `plan-qwen-3060.md`. Se avanza de a un paso.
Última actualización: 2026-10-14 (Fase 6 cerrada; `qwen` = llama.cpp con contexto 131072).

## Estado y pendientes para la próxima sesión

Estado: Fase 6 cerrada con `python3 decidir-fase6.py`: gana `q4-base` (Q4_K_XL, thinking activado, `-b`/`-ub` 2048, `--n-cpu-moe` 28). Las cuatro variantes de llama.cpp cumplen todos los umbrales; Ollama no (timeout y tests rotos). `qwenx` pasó a `qwen` y la de Ollama a `qwen-ollama`. Contexto por defecto 131072 (`qwen-setup.sh` v6.1). Detalle en «Resultados de la Fase 6» (notas técnicas).

Hecho:

1. [x] Esperar a que termine `~/fase6.sh`.
2. [x] Entregar `~/fase6-resumen.txt`, `resultados.csv` y `bench-iq3.txt`.
3. [x] `python3 decidir-fase6.py` con los logs reales: gana `q4-base`.
4. [x] Registrar filas, cerrar la Fase 4 con IQ3_XXS (barrido en `~/bench-iq3.txt`, suelo 16), `permissions.deny = ['WebSearch']` confirmado en `--check`, y renombrar `qwenx` → `qwen`, `qwen` → `qwen-ollama`.
5. [x] Contexto 131072: VRAM medida tras cargar 11262 MiB (la estimación era ~10980; el real quedó ~280 MiB por encima), bajo el umbral de 11500 por ~240 MiB. A 64k eran 10368 MiB.
6. [x] Fijar 131072 por defecto en `qwen-setup.sh` (v6.1, con `QWEN_PCT` limitado a 90). Ejecutar `./qwen-setup.sh && source ~/.bashrc && ./qwen-setup.sh --check`.

Pendiente, en este orden:

1. [ ] Dentro de `qwen` (131072), escribir `/autocompact`: comprobar que el umbral es ~90k (90 % de la ventana de 100k). Si Claude Code lo ignora o lo limita, ajustar el script (ventana igual al contexto del servidor cuando pase de 100k).
2. [ ] Vigilar la VRAM bajo carga real a 131072 (`watch -n2 'nvidia-smi --query-gpu=memory.used --format=csv,noheader'`). Si pasa de ~11500 MiB o falla con error de memoria: `QWENX_NCMOE=30 qwen` o `QWENX_CTX=98304 qwen`. Mejor sin Brave abierto.
3. [ ] Tras una sesión larga, mirar el contexto máximo visto: `grep -oE 'n_tokens = [0-9]+' /tmp/llama-server.log | sort -t= -k2 -n | tail -1` (copiar antes el log si se va a reabrir `qwen`: `cp /tmp/llama-server.log ~/sesion-$(date +%H%M).log`).
4. [ ] Confirmar que la barra de carga de `qwen` avanza (hasta ahora solo se vio la línea final).
5. [ ] Comprobar que el modelo ya no intenta `WebSearch` en una sesión real (la sintaxis de la regla `deny` no está verificada).
6. [ ] Repetir `q4-base` una vez más (`./bench-qwen.sh llama q4-base-2` con Ollama parado) para medir varianza: `q4-ctx32k` tardó 683 s y no está explicado.
7. [ ] Verificar la calidad con tarea real (el plan avisa de alucinaciones y fallos de herramientas); si no convence, plan B: IQ3_XXS (`QWENX_MODEL=~/models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf QWENX_NCMOE=18 qwen`).

Datos de contexto medidos (VRAM): `-c` 32768 → 10020 MiB (bajo carga); `-c` 65536 → 10368-10414 MiB en reposo y 10701 MiB máximo bajo carga (`q4-base`); `-c` 131072 → 11262 MiB tras cargar. Coste ~12 MiB por cada 1000 tokens entre 32k y 64k, y de 64k a 128k fueron ~890 MiB (~14 MiB por cada 1000): la estimación lineal se quedó ~280 MiB corta.

## Fase 1: arreglo gratis (Ollama)

- [x] Aplicar `CLAUDE_CODE_ATTRIBUTION_HEADER=0` en `~/.claude-local/settings.json`
- [~] Línea base con Ollama (parcial, ver tabla abajo)
- [ ] Opcional: repetir el guion con el modelo ya precargado y mirar `journalctl -u ollama -n 60 --no-pager` para separar prefill y generación

## Fase 2: llama.cpp con CUDA

- [x] `nvidia-smi` responde (driver 595.99.02, CUDA 13.2)
- [x] Dependencias instaladas con dnf (ya estaban)
- [x] `nvcc --version` responde (13.2.51)
- [x] Compatibilidad del GCC: nvcc usa `g++-15` como compilador host, no hizo falta `cuda-gcc-c++`
- [x] `cmake -B build` configurado (ver nota del runtime compartido)
- [x] Compilar con `cmake --build` (terminó; `llama-cli --version` → 0.6.0-dev, build 11606)
- [x] Verificar el backend CUDA (`--list-devices` → CUDA0: RTX 3060, 11908 MiB; `ldd` enlaza `libcudart.so.13`). Fase 2 cerrada

## Fase 3: descargas

- [x] Revisar espacio en disco e instalar `huggingface_hub` (modelos en `~/models`, disco del sistema: lectura ~1,7 GB/s; el KIOXIA ~2,3 GB/s no compensa)
- [x] Borrar de Ollama los modelos que no se usan (queda solo `qwen3.6:35b`)
- [x] Iniciar sesión en Hugging Face (`hf auth login --force`; token de solo lectura activo). Los `Traceback ... Exit: 0` de `hf` son un fallo cosmético de typer/click con Python 3.14, no un error
- [x] UD-Q4_K_XL (21 GB en `~/models`, descarga completa)
- [x] IQ3_XXS (descargado en `~/models`)

## Fase 4: barrido de `--n-cpu-moe` × batch

- [x] Parar Ollama (`sudo systemctl stop ollama`)
- [x] Barrido con Q4: candidatas `-ub` 4096 / `--n-cpu-moe` 32 y `-ub` 2048 / `--n-cpu-moe` 28 (ver notas)
- [x] Confirmar con `llama-server` a 32k mirando `nvidia-smi` (candidata `-ub` 4096 / `--n-cpu-moe` 32: VRAM 8779 MiB bajo carga, cumple umbrales; elegida finalmente `-b`/`-ub` 2048 / `--n-cpu-moe` 28: VRAM 10020 MiB, reproceso en caliente ~2k tokens)
- [x] Repetir con IQ3_XXS (`~/bench-iq3.txt`, `-ub` 2048: `--n-cpu-moe` 28 → 39,3 tok/s; 24 → 43,1; 20 → 47,6; 16 → 53,0; 12 → error de carga; suelo 16, servidor con 18)

## Fase 5: función `qwen` (antes `qwenx`)

- [x] Rellenar `NCMOE` y `UB` en `~/.qwen-local.sh`: 28 y 2048, instalados con `qwen-setup.sh` v4.5
- [x] Probar `/v1/messages` con curl (responde `type: message`, bloque `thinking` + bloque `text` "ok", `stop_reason: end_turn`)
- [~] Barra de carga de `qwen` (v4.5): en `bench-qwen.sh` se vio la línea final (100 %, listo en 16 s) pero no el avance intermedio; falta confirmar que el porcentaje avanza (si se queda en 0 %, mirar el formato de puntos en `/tmp/llama-server.log`)

## Fase 6: pruebas A/B y decisión

- [x] Ejecutar el guion en cada configuración (con `bench-qwen.sh`; resultados en «Resultados de la Fase 6»)
  - [x] `q4-base`: Q4_K_XL, ub 2048, ncmoe 28, ctx 65536, thinking activado
  - [x] `q4-nothink`: `QWENX_NOTHINK=1`
  - [x] `q4-ctx32k`: `QWENX_CTX=32768`
  - [x] `iq3xxs`: IQ3_XXS con `--n-cpu-moe` 18 (suelo del barrido 16 + 2)
  - [x] `base-ollama`: timeout en la etapa 1, tests fallan en la etapa 2
- [x] Aplicar la regla de decisión (`decidir-fase6.py`): gana `q4-base`
- [x] Renombrar `qwenx` → `qwen` y `qwen` → `qwen-ollama` (`qwen-setup.sh` v6)

---

## Registro de tiempos

| Configuración | Mensaje | Total (Claude Code) | Primer token | Notas |
|---|---|---|---|---|
| Ollama + fix Fase 1 | En frío (`leeme el CLAUDE.md y resume pendientes`) | 2m 18s | sin medir | Incluye carga del modelo, lectura del archivo, thinking y respuesta |
| Ollama + fix Fase 1 | En caliente (mensaje corto) | 8s | sin medir | 4s de thinking |
| llama.cpp Q4_K_XL, `-ub` 4096, `--n-cpu-moe` 32, `-c` 32768 | 18010 tokens sintéticos en frío (`curl`, prompt `hola ` repetido) | sin medir | 10,8 s | Prefill 1661 tok/s; generación 29,1 tok/s; VRAM 8779 MiB; RAM disp. 8092 MiB. El prompt repetitivo puede ser optimista: repetir con texto real |
| llama.cpp Q4_K_XL, `-ub` 4096, `--n-cpu-moe` 32, `-c` 32768 | Mismo prompt + frase corta, en caliente (`curl`) | sin medir | 2,74 s | `cache_n` 13914 de ~18046; reprocesó 4101 tokens (1494 tok/s); generación 26,4 tok/s. Cumple ≤ 3 s por poco |
| llama.cpp Q4_K_XL, `-b`/`-ub` 2048, `--n-cpu-moe` 28, `-c` 32768 | 18010 tokens sintéticos en frío (`curl`) | sin medir | 11,7 s | Prefill 1537 tok/s; generación 32,1 tok/s |
| llama.cpp Q4_K_XL, `-b`/`-ub` 2048, `--n-cpu-moe` 28, `-c` 32768 | Mismo prompt + frase corta, en caliente (`curl`) | sin medir | 1,60 s | `cache_n` 15962; reprocesó 2053 tokens; generación 32,6 tok/s; VRAM 10020 MiB; RAM disp. 10174 MiB. Cumple todos los umbrales |
| llama.cpp Q4_K_XL, `-b`/`-ub` 2048, `--n-cpu-moe` 28, `-c` 65536 (`qwenx`) | Servidor cargado, sin petición | sin medir | sin medir | VRAM 10414 MiB (desktop incluido) |
| llama.cpp Q4_K_XL, `-b`/`-ub` 2048, `--n-cpu-moe` 28, `-c` 65536 (`qwenx`) | Arranque del servidor hasta `/health` | sin medir | sin medir | Carga 17 s (Ollama: ~20 s) |
| llama.cpp Q4_K_XL, `-b`/`-ub` 2048, `--n-cpu-moe` 28, `-c` 131072 (`qwen`) | Servidor cargado, sin petición | sin medir | sin medir | VRAM 11262 MiB (a 64k, 10368 MiB). Primer mensaje real (`leeme el CLAUDE.md y resume pendientes`): respuesta correcta en ~49 s |
| llama.cpp Q4_K_XL, `-b`/`-ub` 2048, `--n-cpu-moe` 28, `-c` 65536 (`qwenx`) | `curl` a `/v1/messages` ("Responde solo: ok", contexto casi vacío) | sin medir | sin medir | Generación 36,15 tok/s (217 tokens); prompt de 15 tokens, el prefill no es representativo |
| llama.cpp Q4_K_XL, `-b`/`-ub` 2048, `--n-cpu-moe` 28, `-c` 65536 (`qwenx`) | `leeme el CLAUDE.md y resume pendientes` en frío, proyecto real (!cerebronardo) | 3m 55s | sin medir | Cuatro bloques de thinking (43+15+36+38 s), un `WebSearch` fallido de 74 s ("Did 0 searches"), varias lecturas y memorias. No comparable 1:1 con los 2m 18s de Ollama: la tarea hizo más pasos |
| llama.cpp Q4_K_XL, `-b`/`-ub` 2048, `--n-cpu-moe` 28, `-c` 65536 (`qwenx`) | Prueba de caché: dos mensajes cortos seguidos, sin herramientas | sin medir | sin medir | 1.º: prompt de 18.679 tokens (system prompt + herramientas + CLAUDE.md de Claude Code), prefill 19,9 s (937 tok/s). 2.º: solo 16 tokens evaluados de ~18.781, prefill 2,1 s: la caché funciona dentro de la conversación. Generación: 31,6 tok/s (40 tokens) en el 1.º y 21,3 tok/s (48 tokens) en el 2.º, este con otra petición corriendo en paralelo |
| llama.cpp Q4_K_XL, `-b`/`-ub` 2048, `--n-cpu-moe` 28, `-c` 65536 (`qwenx`) | Sesión de prueba de `WebFetch` (peticiones grandes del log) | sin medir | sin medir | 18.702 tokens en 21,3 s (879 tok/s, gen 20,5 tok/s) y 30.855 tokens en 33,6 s (918 tok/s, gen 19,4 tok/s), con otra petición corriendo en paralelo. Probablemente el resumen de las páginas descargadas, no la conversación |

### Registro de `bench-qwen.sh` (RUT chileno, etapa 1 en frío, etapa 2 en caliente con `-c`)

| Etiqueta | Etapa | Total | API | Turnos | Tests | Tests intactos | VRAM máx (MiB) | RAM disp. mín (MiB) | Carga |
|---|---|---|---|---|---|---|---|---|---|
| `q4-base` | 1 (frío) | 192,2 s | 191,0 s | 9 | OK (10) | sí | 10701 | 7903 | 16,7 s |
| `q4-base` | 2 (caliente) | 28,6 s | 218,6 s (acumulado, ver nota) | 5 | OK (13) | sí | 10588 | 7422 | 16,7 s |
| `q4-nothink` | 1 | 263,4 s | 261,8 s | 15 | OK (10) | sí | 10850 | 6660 | 17,0 s |
| `q4-nothink` | 2 | 30,6 s | 291,4 s (acumulado) | 5 | OK (13) | sí | 11027 | 6844 | 17,0 s |
| `q4-ctx32k` | 1 | 682,9 s | 681,6 s | 20 | OK (10) | sí | 10350 | 7864 | 16,9 s |
| `q4-ctx32k` | 2 | 75,0 s | 755,4 s (acumulado) | 14 | OK (13) | sí | 10264 | 7587 | 16,9 s |
| `iq3xxs` | 1 | 168,0 s | 166,8 s | 9 | OK (10) | sí | 10345 | 17094 | 5,1 s |
| `iq3xxs` | 2 | 30,9 s | 196,8 s (acumulado) | 5 | OK (13) | sí | 10175 | 16544 | 5,1 s |
| `base-ollama` | 1 | 900,0 s (timeout) | ? | ? | OK (10) | sí | 11233 | 20227 | 21,5 s |
| `base-ollama` | 2 | 66,6 s | 957,1 s | 6 | FALLAN | sí | 10962 | 20502 | 21,5 s |

- `q4-base` = Q4_K_XL, `-b`/`-ub` 2048, `--n-cpu-moe` 28, `-c` 65536, thinking activado.
- VRAM (≤ 11500 ✔) y RAM disponible (≥ 4096 ✔) cumplen.
- Velocidad: tablas siguientes (en caliente: 3 últimas peticiones del resumen; en frío: log completo de la corrida).

| Petición (etapa 2) | Prompt evaluado | Prefill | Generación |
|---|---|---|---|
| task 5193 | 724 tokens en 1,61 s | 450 tok/s | 30,09 tok/s (289 tokens) |
| task 5484 | 379 tokens en 1,39 s | 273 tok/s | 31,72 tok/s (58 tokens) |
| task 5544 | 336 tokens en 1,24 s | 271 tok/s | 27,52 tok/s (82 tokens) |

| Petición en frío (etapa 1) | Prompt evaluado | Prefill |
|---|---|---|
| task 0 | 16027 tokens en 17,10 s | 937,5 tok/s |

Umbrales del plan: primer mensaje en frío ≤ 30 s, siguientes ≤ 3 s hasta el primer token, ≥ 20 tok/s con 16k de contexto.

---

## Notas técnicas de lo que pasó

### Error de `libcudart_static` al configurar CMake

- **Síntoma:** `cmake -B build` falla en la identificación del compilador CUDA con `no se puede encontrar -lcudart_static`.
- **Causa:** el sistema no trae `libcudart_static.a`, solo `/usr/lib64/libcudart.so` (13.2.51), y CMake enlaza estático por defecto en esa prueba.
- **Solución aplicada:**

```bash
cd ~/llama.cpp
rm -rf build
CUDAFLAGS="--cudart shared" cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86 -DBUILD_SHARED_LIBS=OFF -DCMAKE_CUDA_RUNTIME_LIBRARY=Shared
cmake --build build --config Release -j --target llama-server llama-bench llama-cli
```

- Si hay que volver a configurar, usar siempre ese comando y no el del plan original.
- Si se quiere probar la otra vía: `dnf provides '*/libcudart_static.a'` para ver qué paquete la trae.

### Primer barrido Q4 (solo generación, tg128 en tok/s)

| `-ub` \\ `--n-cpu-moe` | 40 | 36 | 32 | 28 | 24 |
|---|---|---|---|---|---|
| 512 | 27,63 | 30,20 | 30,99 | 35,14 | 37,15 |
| 1024 | 28,78 | 30,74 | 33,01 | 35,56 | 37,45 |
| 2048 | 28,83 | 30,76 | 33,02 | 34,49 | error |
| 4096 | 26,64 | 30,71 | 32,96 | error | error |

- `error` = `failed to create context` (no cabe en VRAM).
- Todas las válidas superan 20 tok/s. Bajar `--n-cpu-moe` acelera la generación; `-ub` casi no la cambia.
- El prefill no salió en esta pasada: el comando del plan usaba `tail -n 3` y se comía esa línea; ya está corregido a `grep -E 'pp4096|tg128|error'` en `plan-qwen-3060.md`. Ver la segunda pasada.

### Segunda pasada Q4 (prefill pp4096 / generación tg128, tok/s)

| `-ub` | `--n-cpu-moe` | pp4096 | tg128 |
|---|---|---|---|
| 512 | 28 | 325 | 31,3 |
| 512 | 24 | 367 | 36,9 |
| 512 | 20 | error de carga | |
| 1024 | 28 | 532 | 33,2 |
| 1024 | 24 | 593 | 36,1 |
| 1024 | 20 | error de carga | |
| 2048 | 32 | 835 | 32,8 |
| 2048 | 28 | 896 | 35,2 |
| 4096 | 36 | 1156 | 27,8 |
| 4096 | 32 | 1218 | 33,1 |

- `--n-cpu-moe` 20 no carga ni con `-ub` 512 (`unable to allocate CUDA0 buffer`): el suelo con `-ub` ≤ 1024 es 24; con 2048, 28; con 4096, 32.
- A igual `--n-cpu-moe` 32, `-ub` 4096 da ~46 % más prefill que 2048 (1218 vs 835) con la misma generación.
- Estimación del primer mensaje en frío (~13k tokens): ~11 s con 1218 tok/s y ~15 s con 896. Es optimista: pp4096 se mide con contexto vacío y el prefill baja al crecer el contexto.
- Candidatas: `-ub` 4096 / `--n-cpu-moe` 32 (máximo prefill) y `-ub` 2048 / `--n-cpu-moe` 28 (más holgura de VRAM, tg 35). Falta confirmar la VRAM real con `llama-server` a `-c 32768` (umbral ~11500 MiB).

### `--no-mmap` ya no existe en `llama-server`

- **Síntoma:** `error: invalid argument: --no-mmap`.
- **Causa:** llama.cpp unificó `--no-mmap`, `--mlock` y `--direct-io` en `-lm` / `--load-mode`. Tu build es la 11606 (0.6.0-dev).
- **Equivalente:** `--no-mmap` → `--load-mode none`. Ya cambiado en `qwen-setup.sh` (v4.1) y en `plan-qwen-3060.md`.
- Comprobar en tu build: `llama-server --help | grep -i load-mode`.

### Caché en caliente: solo reutiliza hasta ~`-ub` tokens antes del final

- Medido: `cache_n` 13914 = 18010 − 4096. Cada mensaje siguiente reprocesa al menos ~4096 tokens (`-ub`), ~2,7 s a 1494 tok/s, aunque solo cambie una frase.
- Hipótesis: el modelo usa checkpoints de contexto y el último queda un lote (`-ub`) antes del final del prompt. Con `-ub` 2048 el reproceso mínimo bajaría a ~2048 tokens; sin verificar.
- Confirmado con `-b`/`-ub` 2048: `cache_n` 15962 = 18010 − 2048; el reproceso en caliente bajó de 4101 a 2053 tokens (2,71 s → 1,60 s). El mínimo de reproceso es `-ub`.
- Tu build tiene `-cms` / `--checkpoint-min-step` (separación mínima entre checkpoints, por defecto 8192 tokens; 0 = sin mínimo) y `-ctxcp` (máximo de checkpoints por slot, por defecto 32). Probado `-cms 1024`: sin efecto (`cache_n` sigue en 13914, reproceso de 4101 tokens en 2,71 s). El log lo confirma: el prompt se parte en 13914 y un último lote de 4096, así que el checkpoint queda un lote antes del final. Siguiente prueba: `-b` 2048 / `-ub` 2048 con `--n-cpu-moe` 28 (candidata 2), esperando un reproceso mínimo de ~2048 tokens.
- `-cram` (caché de prompts en RAM, por defecto hasta 8192 MiB) puede comerse la RAM libre; si la RAM disponible se acerca a 4096 MiB, limitarlo (p. ej. `-cram 2048`).

### Error 400: la petición excede el contexto del servidor

- **Síntoma (Claude Code con `qwenx`):** `API Error: 400 request (41814 tokens) exceeds the available context size (32768 tokens)`.
- **Causa:** con un modelo local, Claude Code asume una ventana de 200k y no compacta a tiempo; la sesión real superó los 32k del servidor.
- **Cambio en `qwen-setup.sh` (v4.3):** `CTX=65536` y `CLAUDE_CODE_AUTO_COMPACT_WINDOW=56000` solo para `qwenx`. `/autocompact` mostró **100k** ("from CLAUDE_CODE_AUTO_COMPACT_WINDOW") en vez de 56k, con la variable bien definida en `~/.qwen-local.sh`; no sé si Claude Code impone un mínimo.
- **v4.4:** ventana fijada en 100000 y `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=55` (umbral ~55k tokens, por debajo de los 64k del servidor). Si sigue dando 400, bajar `PCT`.
- Comprobar el contexto máximo visto tras una sesión larga: `grep -oE 'n_tokens = [0-9]+' /tmp/llama-server.log | sort -t= -k2 -n | tail -1`.
- **VRAM a 64k medida:** 10414 MiB (a 32k eran 10020), con margen de ~1,1 GB bajo el umbral de ~11500 MiB. Duplicar el contexto costó solo ~400 MiB.
- Comprobar en Claude Code el valor activo: `/autocompact`.

### Primera sesión real con `qwenx` (guion, mensaje 1)

- `/v1/messages`: con `max_tokens` 256 el modelo gastó 217 tokens, casi todos en thinking. Con un tope más bajo la respuesta puede cortarse antes del bloque `text`; no es un fallo del servidor.
- **`WebSearch` desperdicia tiempo:** el modelo lo llamó, tardó 74 s y no hizo ninguna búsqueda. Con un backend local no sirve. Pendiente: probar a denegarlo en `~/.claude-local/settings.json` (`permissions.deny`) para que no lo intente; no está aplicado.
- **Calidad:** ejecutó `date` (salió martes 13 oct) pero el resumen dice "Martes 14 de octubre". Es la clase de error de la sección Riesgos del plan; vigilar en la Fase 6.
- **Velocidad de esa sesión: no recuperable.** `qwenx` reescribe `/tmp/llama-server.log` en cada arranque y el log actual solo trae la petición del curl, así que el timing de la sesión de `!cerebronardo` se perdió. Para próximas mediciones, copiar el log antes de volver a abrir `qwenx`: `cp /tmp/llama-server.log ~/sesion-$(date +%H%M).log`.
- Para separar prefill y generación de una sesión: `grep -E 'tokens per second' /tmp/llama-server.log | tail -n 12`. Contexto máximo visto: `grep -oE 'n_tokens = [0-9]+' /tmp/llama-server.log | sort -t= -k2 -n | tail -1`.

### Búsqueda web con `qwenx` (prueba de `WebFetch`)

- `WebSearch` incorporado: devolvió respuesta vacía las 3 veces ("Did 0 searches", 3 s cada una). Es una herramienta del lado del servidor de Anthropic; no funciona con `llama-server`.
- `WebFetch` incorporado: se ejecuta en local, pero no sirve como buscador. DuckDuckGo (HTML y normal) → captcha o solo cabecera; Google → página de error; Bing → resultados de radios chilenas para "obsedium" (no se sabe si por Bing o por la extracción del modelo). El modelo además reintenta en bucle (3 `WebSearch`, 5 `WebFetch`).
- Pendiente de decidir: denegar `WebSearch` en `~/.claude-local/settings.json` (`permissions.deny`) y, si hace falta buscar, MCP de DuckDuckGo (`uvx duckduckgo-mcp-server`, con regla `ask`). Nada aplicado en `qwen-setup.sh`.

### Caché en una sesión real de Claude Code (corrige una hipótesis anterior)

- Medido con dos mensajes cortos seguidos: el segundo evaluó 16 tokens de ~18.781 (2,1 s), así que la caché sí se reutiliza dentro de la conversación. Cada petición aparece como "selected slot by LRU, t_last = -1" y aun así reutilizó el prefijo; mecanismo sin confirmar (¿caché de prompts en RAM, `-cram`?).
- Lo que escribí antes ("algo de Claude Code rompe el prefijo") no está respaldado: los dos reprocesos completos de 18.7k y 30.8k tokens coinciden con peticiones cuyo prompt es el contenido de una página descargada (nada que reutilizar). Es consistente con los tamaños de lo descargado, pero no está probado.
- `llama-server` arranca con 4 slots (no se pasa `-np`). Por ahora no tocarlo: las peticiones auxiliares de Claude Code van a otros slots sin pisar la conversación principal (hipótesis).
- Línea base real de Claude Code: ~18,7k tokens de prompt ya en el primer mensaje, no los ~13k que asumía el plan. Primer mensaje en frío: ~20 s de prefill, dentro del umbral de 30 s.
- Generación de esos dos mensajes (`grep -E ' eval time' /tmp/llama-server.log | grep -v prompt | tail -n 4`): 31,58 tok/s con 40 tokens y 21,27 tok/s con 48 tokens, con ~18,7k de contexto. Muestras muy cortas; la segunda coincidió con otra petición en otro slot (probable causa de la caída, sin confirmar). Cumple el umbral de 20 tok/s, la segunda por poco.
- Umbrales con una sesión real (prefill + generación, sin medir el primer token exacto): primer mensaje en frío ~20 s (≤ 30 s ✔), siguientes ~2,1 s de prefill (≤ 3 s ✔), generación 21-32 tok/s (≥ 20 ✔), VRAM 10414 MiB medida en reposo a 64k (≤ 11500 ✔ falta mirarla bajo carga con 18k de contexto).

### Primera corrida real de `bench-qwen.sh` (`q4-base`, 2026-10-13)

- Los flags de `claude -p` (`--output-format json`, `--max-turns`, `--allowedTools`) funcionan: el JSON se leyó (API y turnos numéricos, `error=false`) y las dos etapas terminaron sin timeout.
- Etapa 1: 9 turnos, 192 s, 10 tests OK. Etapa 2 (sesión continuada con `-c`): 5 turnos, 28,6 s, 13 tests OK. `test_rut.py` intacto en ambas.
- Anomalía: `api_s` de la etapa 2 (218,6 s) supera el total de la etapa (28,6 s). 218,6 − 191,0 = 27,6 s ≈ el total, así que `duration_api_ms` parece acumularse al continuar la sesión. Sin confirmar: mirar `etapa2.json` en la carpeta de la corrida. Mientras tanto, para la etapa 2 usar `wall_s`.
- Carga del modelo 16,7 s (coincide con los ~17 s medidos antes).
- Velocidad en caliente (3 últimas peticiones): generación 27,5-31,7 tok/s (≥ 20 ✔); reproceso de 336-724 tokens en 1,2-1,6 s (≤ 3 s ✔, la caché se reutiliza). Los tok/s de prefill (271-450) no son representativos: con prompts tan cortos el lote no se llena.
- Primer mensaje en frío (task 0, etapa 1): 16027 tokens evaluados en 17,1 s (937 tok/s). Es solo prefill, sin contar la carga del modelo (16,7 s); cumple ≤ 30 s ✔. El prompt de `claude -p` (16k) es menor que el de la sesión interactiva (~18,7k).
- Contexto máximo visto: 26020 tokens (muy por debajo de los 65536 del servidor y del umbral de autocompactado ~55k).
- Generación en toda la corrida: mín 27,52 y máx 32,92 tok/s (≥ 20 ✔).
- Reprocesos mayores (no son mensajes cortos, llevan resultados de herramientas): 2378 tokens en 3,24 s (735 tok/s), 1261 en 1,84 s, 805 en 1,44 s, 755 en 1,60 s. Orden de magnitud: ~1,4 ms por token nuevo; con más de ~2000 tokens nuevos se pasa de 3 s. Para el umbral de ≤ 3 s solo cuentan los mensajes cortos (336-724 tokens, 1,2-1,6 s ✔).
- Resultado de `q4-base` contra umbrales: frío ✔, caliente ✔, generación ✔, VRAM ✔, RAM ✔, tests ✔ en ambas etapas. Sirve como referencia para comparar las demás variantes.
- Una sola corrida por configuración: la variación entre repeticiones no está medida. Si la diferencia entre variantes es pequeña, repetir antes de concluir.

### Resultados de la Fase 6 (`decidir-fase6.py`, 2026-10-13)

Umbrales: frío ≤ 30 s | caliente ≤ 3 s (prompts ≤ 1000 tokens) | gen ≥ 20 tok/s (mínima) | VRAM ≤ 11500 MiB | RAM ≥ 4096 MiB.

| Config | Frío (s) | Cal. (s) | Gen mín | VRAM | RAM mín | Ctx máx | Wall 1 (s) | Wall 2 (s) | Turnos | Tests | Veredicto |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `q4-base` | 17,1 | 1,6 | 27,5 | 10701 | 7422 | 26020 | 192,2 | 28,6 | 9/5 | OK | cumple todo |
| `q4-ctx32k` | 17,2 | 2,4 | 30,3 | 10350 | 7587 | 32767 | 682,9 | 75,0 | 20/14 | OK | cumple todo |
| `q4-nothink` | 17,0 | 1,6 | 25,3 | 11027 | 6660 | 29804 | 263,4 | 30,6 | 15/5 | OK | cumple todo |
| `iq3xxs` | 11,6 | 1,1 | 38,0 | 10345 | 16544 | 27982 | 168,0 | 30,9 | 9/5 | OK | cumple todo |
| `base-ollama` | - | - | - | 11233 | 20227 | - | 900,0 | 66,6 | ?/6 | FALLA | NO cumple: tests |

- Regla (contexto > thinking > cuantización): gana `q4-base`. También cumplen `q4-ctx32k`, `q4-nothink` e `iq3xxs`.
- Ollama: sin log de `llama-server`, solo se compara por wall, VRAM, RAM y tests; descartado.
- Quitar thinking o bajar a 32k no acelera: más turnos y más tiempo. `q4-ctx32k` (683 s en la etapa 1) no está explicado; una sola corrida por configuración.
- `iq3xxs`: la más rápida (frío 11,6 s, gen 38-45 tok/s, 168 s) y con ~16 GB de RAM libre, pero con pérdida de calidad: plan B.
- La VRAM de `q4-nothink` (11027 MiB) es la más alta de las llama.cpp; ninguna pasa de 11500.

### Incidente: `qwen` no encontrada tras renombrar (sed ejecutado dos veces)

- **Síntoma:** `bash: qwen: instrucción no encontrada`; `grep` mostraba dos `qwen-ollama() {` (líneas 39 y 117 de `~/.qwen-local.sh`) y ninguna `qwen()`.
- **Causa:** el bloque de `sed` del renombrado se ejecutó dos veces; en la segunda pasada el `qwen()` de llama.cpp (antes `qwenx`) se volvió `qwen-ollama()`. También quedó duplicada la línea de changelog v6.
- **Arreglo:** `awk` que renombró la segunda `qwen-ollama()` a `qwen()` y quitó el v6 duplicado; luego `./qwen-setup.sh` y `source ~/.bashrc`. Ahora `qwen-setup.sh` v6.1 se entrega completo y `--check` cuenta cuántas veces está definida cada función.
- **Regla:** no volver a aplicar `sed` de renombrado; reemplazar el script por la versión entera.

### Avisos del log que se pueden ignorar

- `Detecting CUDA compiler ABI info - failed` seguido de `works`.
- `NCCL not found`: solo afecta a varias GPU.

---

## Config actual y script

La config de Qwen está separada de tu `claude` de Pro:

- Carpeta propia `~/.claude-local` (sin plugins, no afecta a `claude`).
- `qwen`: llama.cpp con `Qwen3.6-35B-A3B-UD-Q4_K_XL`, contexto 131072 (v6.1).
- `qwen-ollama`: Ollama con `qwen3.6:35b`, de respaldo.
- Arranca en plan mode (`permissions.defaultMode` en su `settings.json`; solo lectura hasta que salgas con Shift+Tab).
- `CLAUDE_CODE_ATTRIBUTION_HEADER=0` y `WebSearch` denegado en su `settings.json`.

Todo eso está recogido en `qwen-setup.sh`, que se actualiza junto con este checklist:

- `./qwen-setup.sh`: instala o actualiza `~/.qwen-local.sh` y el `settings.json`
- `./qwen-setup.sh --check`: muestra el estado sin cambiar nada (incluye cuántas definiciones hay de `qwen()`, `qwen-ollama()` y `qwenx()`)

Pendientes del script:

- [x] Comparar `qwen` del script con tu definición real en `~/.bashrc` y ajustar (v2: añadida la precarga del modelo)
- [x] Ejecutar `./qwen-setup.sh`, borrar la función `qwen` antigua de `~/.bashrc` y comprobar con `--check` (copia en `~/.bashrc.bak`)
- [x] Confirmar dónde se activa el plan mode: `permissions.defaultMode = "plan"` en `~/.claude-local/settings.json`
- [x] Rellenar `NCMOE` y `UB` tras la Fase 4 (28 y 2048, en v4.2)
- [x] Barra de carga (v4.5)
- [x] `qwen-setup.sh` v5: funciones `_qwen_up/_down` y `_qwenx_up/_down` que exige `bench-qwen.sh`; logs con fecha en `~/.cache/qwenx/`; `WebSearch` denegado
- [x] Primera corrida real de `bench-qwen.sh` (los flags de `claude -p` funcionan) y Fase 6 completa con `fase6.sh`
- [x] v6: `qwenx` → `qwen`, `qwen` → `qwen-ollama`
- [x] v6.1: contexto 131072 por defecto y `QWEN_PCT` con tope 90
- [ ] Comprobar `/autocompact` con 131072 (ver pendientes arriba)
- Variables para probar combinaciones (por entorno, sin editar el script; los nombres siguen siendo `QWENX_*`): `QWENX_MODEL`, `QWENX_NCMOE`, `QWENX_UB`, `QWENX_CTX`, `QWENX_NOTHINK=1`. Ej.: `QWENX_NOTHINK=1 ./bench-qwen.sh llama q4-sin-thinking`
