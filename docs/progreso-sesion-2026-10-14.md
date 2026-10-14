# Progreso de la sesión (2026-10-14): RAM, repo y laya

Complementa `plan-qwen-3060.md`, `checklist-qwen-3060.md` y `anexo-router-ram-qwen.md`. Sugerido: guardarlo en `docs/`.

## 1. Resumen

- **RAM recuperada:** el UMA de la iGPU quedó en 512 MiB y el sistema ve 31467 MiB (antes 27,3 GiB). Con qwen cerrado hay 27,5 GB disponibles y el swap está sin uso.
- **Velocidad:** `llama-bench` de línea base nueva: `tg128` 42,16 tok/s (antes ~35).
- **`-cram`:** la prueba está **a medias**. Recién cargado, `QWENX_CRAM=2048` confirmado da RSS 14,46 GiB y 0 de swap. Falta la sesión larga, que es la que decide si la caché era la causa del crecimiento.
- **Repo:** ordenado en `setup/`, `scripts/`, `laya/`, `kev/` y `docs/`. Los scripts usan rutas relativas a su propia ubicación y se verificó que funcionan.
- **Laya:** hay mediciones y benchmarks, pero **la integración con `qwen` todavía no está implementada**. Ver sección 5.

## 2. Mediciones de esta sesión

### RAM del sistema (`free -m`, qwen cerrado)

| | total | disponible | swap usado |
|---|---|---|---|
| Antes (UMA 4096 MiB) | 27939 | 1379 | 9217 |
| Después (UMA 512 MiB) | 31467 | 27509 | 0 |

### `llama-bench` (Q4_K_XL, `-ncmoe 28`, `-b`/`-ub` 2048, `-fa 1`, KV q8_0, `-r 3`)

| | pp4096 (tok/s) | tg128 (tok/s) |
|---|---|---|
| Antes (`-r 1`, otro estado de RAM) | 896 | 35,2 |
| Ahora (UMA 512 MiB) | 874,21 ± 1,54 | **42,16 ± 0,17** |

Lectura: la generación sube ~20 % y el prefill queda igual. Es coherente con que la generación iba limitada por la RAM, pero **no está probado**: la comparación no es limpia (una sola pasada antes, otro estado de memoria).

### `qwen-mem` recién cargado

| Condición | RSS llama-server | Swap llama-server | RAM disponible | Swap del sistema |
|---|---|---|---|---|
| Sin `-cram` (el `pgrep` no mostraba el flag) | 13,88 GiB | 0,18 GiB | ~13050 MB | ~1260-1280 MB |
| Con `-cram 2048` confirmado en `pgrep` | 14,46 GiB | 0,00 GiB | 13017 MB | 1052 MB |

El swap del sistema no es de llama-server: los cinco procesos que más swap tienen suman ~550 MB y ninguno pasa de 164 MB.

## 3. Repo `Qwen3.6-35b+Laya`

```
.
├── docs/      plan, checklist, anexo y este archivo
├── kev/       bench_kev.py, prompts.jsonl, run.sh (kev-repo y .venv no se versionan)
├── laya/      bench_laya.py, prompts.jsonl, run.sh, test-laya.sh
├── scripts/   bench-qwen.sh, decidir-fase6.py, fase6.sh
├── setup/     qwen-setup.sh (v6.2, sin cambios)
└── .gitignore
```

`results/` se crea solo al correr algo y está ignorada por git.

### Cambios de rutas

| Script | Antes | Ahora |
|---|---|---|
| `fase6.sh` | `~/Escritorio/bench-qwen.sh` y `qwen-setup.sh` | relativo a su carpeta; ejecuta `bash "$SETUP" --check` |
| `bench-qwen.sh` (v1.1) | `~/bench-qwen` | `<repo>/results/bench-qwen` (o `BENCH_DIR`) |
| `decidir-fase6.py` | `~/bench-qwen` | `<repo>/results/bench-qwen` (o `BENCH_DIR`) |
| `test-laya.sh` | `~/Escritorio/laya`, `~/laya-test.csv`, `~/laya-test-logs` | su propia carpeta; CSV y logs en `<repo>/results/` |

Además, `test-laya.sh` ya no dice que hay que editar `qwen-setup.sh` para probar `-cram`: ahora indica `QWENX_CRAM=2048 qwen`. `qwen-setup.sh`, `laya/run.sh`, `kev/run.sh` y los `bench_*.py` ya eran independientes de su ubicación.

### Verificado

- `python3 scripts/decidir-fase6.py` lee `results/bench-qwen` y reproduce la Fase 6: gana `q4-base`; también cumplen `q4-ctx32k`, `q4-nothink` e `iq3xxs`.
- `bash setup/qwen-setup.sh --check`: una `qwen()`, una `qwen-ollama()`, cero `qwenx()`, contexto por defecto 131072, `~/.bashrc` carga `~/.qwen-local.sh`.

### No verificado

- Ninguno de los benchmarks (`fase6.sh`, `bench-qwen.sh`, `test-laya.sh`) se ha ejecutado desde el repo; solo se comprobó sintaxis y resolución de rutas. La primera corrida real es la prueba.

### Notas operativas

- La ruta del repo tiene `!` y `+`: guardarla en una variable con comillas simples (`R='...'`) y usar `"$R"`.
- El repo está en `/run/media/...`: ejecutar con `bash script.sh` por si el montaje no deja ejecutar.
- Los `.md` de `docs/` todavía mencionan rutas viejas (`~/Escritorio`, `~/laya-test.csv`, `~/bench-iq3.txt`).

## 4. Prueba de `-cram`: cómo seguir

```bash
QWENX_CRAM=2048 qwen
# en otra terminal, cuando cargue:
pgrep -a llama-server | grep -o -- '-cram [0-9]*'     # debe mostrar -cram 2048
while true; do date +%T; qwen-mem; sleep 120; done | tee -a "$R/results/qwen-mem-cram2048.log"
```

Trabajar 30-60 min con tareas distintas (la caché solo crece con prompts distintos). Antes de cerrar: `cp /tmp/llama-server.log "$R/results/sesion-cram-$(date +%H%M).log"`.

- Si el RSS se queda en ~14,5-16 GiB sin swap: la causa era la caché de prompts.
- Si vuelve a subir hacia ~20 GiB o más: probar `QWENX_LOADMODE=mmap` y vigilar lecturas de disco. `mlock` solo al final.

## 5. Laya

### Estado

**No implementado.** Lo que existe son los benchmarks (`bench_laya.py`, `test-laya.sh`) y las mediciones del anexo. Falta el servicio o hook que conecte laya con `qwen`.

### Qué es laya en este proyecto

Una librería de Python que se carga dentro del propio proceso, no un servidor: `Router(device="cpu", max_loaded=1)` y `router.predict(texto, preguntas, model=...)`. Se fuerza CPU (`CUDA_VISIBLE_DEVICES=""`) para no tocar la VRAM de qwen. Hace tres preguntas por prompt: complejidad (simple / media / compleja), destructivo e injection (umbral 0,5 en las dos últimas).

### Resultados medidos (20 prompts, una corrida)

| Modelo | Acuerdo | Lat. mediana | RAM pico |
|---|---|---|---|
| laya `multilingual` | 83 % | 269 ms (p95 302) | 2322 MB |
| laya `typed-decisions` | 65 % | 545-951 ms | ~2800 MB (descartado) |
| kev-0.8b | 90 % | 1012-1656 ms | ~5580 MB (no cabe junto a qwen) |

`multilingual` por pregunta: complejidad 15/20, destructivo 18/20, injection 17/20.

Bajo carga real (`test-laya.sh`, `tag=base`, **antes** del arreglo del UMA): latencia 231-297 ms con qwen generando (cumple ≤ 500 ms). `taskset` empeoró la latencia (752 y 403 ms). La RAM disponible cayó de 5132 a 508 MB, pero ya bajaba en la fase sin router, así que no venía de laya. Esas cifras hay que repetirlas con la RAM nueva.

### Limitaciones que condicionan el diseño

- `multilingual` deja pasar el `DROP` de la tabla de usuarios y sobrescribir `.env`, no detecta "desactiva el plan mode" como injection y suma 2 falsos positivos de injection.
- Subestima la complejidad siempre hacia "simple".
- La muestra es chica: la diferencia con kev son 4 respuestas de 60, no concluyente.

### Diseño propuesto (por confirmar)

- Laya **solo avisa o sugiere**, nunca bloquea. Las reglas `deny`/`ask` y el plan mode en `~/.claude-local/settings.json` (`rm -rf`, `git push --force`, `DROP`, escribir `.env`) se quedan como red de seguridad.
- Debe ser **opcional y apagado por defecto** hasta medir la RAM con `test-laya.sh` (`TAG=post-uma`).
- Falta decidir cómo se conecta: servicio local o hook de Claude Code. No está evaluado.

### Condiciones previas

1. Cerrar la prueba de `-cram` (sección 4).
2. `TAG=post-uma ./laya/test-laya.sh` con qwen cargado y sin Brave. Criterio: RAM disponible ≥ 4096 MB en todas las fases y tok/s de qwen estables.
3. Ampliar `prompts.jsonl` a ~100 prompts con etiquetas de complejidad revisadas y repetir laya vs kev antes de decidir.

## 6. Pendientes, en orden

1. [ ] Sesión larga con `QWENX_CRAM=2048 qwen` y registro de `qwen-mem` (sección 4).
2. [ ] Mover el módulo de RAM de 8 GiB al canal A (un cambio a la vez) y repetir el `llama-bench` de línea base.
3. [ ] Opcional: escritorio en la iGPU y medir VRAM con `nvidia-smi`.
4. [ ] `TAG=post-uma` de `test-laya.sh`.
5. [ ] Ampliar `prompts.jsonl` (~100) y repetir laya vs kev.
6. [ ] Bootstrap en `setup/`: compilar llama.cpp (con `--cudart shared`), descargar los modelos con `hf` y crear el `.venv` de laya. Falta saber cómo se instaló laya (origen y versión).
7. [ ] Integración de laya con `qwen` (sección 5), solo si pasan 1 y 4.
8. [ ] Actualizar `docs/`: rutas nuevas, `qwen-setup.sh` v6.2, línea base de `llama-bench` y esta sesión en el checklist.
9. [ ] Pendientes heredados del checklist: `/autocompact` con 131072, VRAM bajo carga real, repetir `q4-base` para medir varianza y calidad con una tarea real.

## 7. Sin verificar

- Que `-cram` sea la causa del crecimiento de llama-server.
- Que la subida de `tg128` venga del arreglo del UMA y no de otro cambio de estado.
- Que exista el hueco de dual channel en esta placa y que mover el módulo lo cierre.
- Latencia y RAM de laya y kev con la RAM nueva.
- Que los benchmarks funcionen desde el repo en una corrida real.
