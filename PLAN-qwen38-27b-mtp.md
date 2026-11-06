# Plan: Qwen3.8-27B GSQ-RCO IQ3_XXS (MTP) en Qwen3.6-35b+Laya

Objetivo: máximos tok/s del `Qwen3.8-27B-GSQ-RCO-IQ3_XXS-mtp.gguf` en una RTX 3060 12 GB, integrado en el proyecto actual (menú, `lib/*.sh`, Pi, laya/kev) **sin romper el flujo del 35B-A3B**.

Estado: **solo plan. No se toca ningún archivo hasta ver el código real.**

---

## 1. Qué sé y qué no

**Fuentes externas (no medido en tu máquina):**

- El modelo es denso (27B), de ~10,4 GB, y trae una cabeza MTP incluida en el fichero (ISTA-DASLab).
- llama.cpp activa MTP con `--spec-type draft-mtp --spec-draft-n-max N` (PR #22673, julio 2026). Hace falta un build reciente.
- El repo `sudoingX/qwen38-mtp` recoge barridos de comunidad: n-max 2 a 4 es el rango útil, `--spec-draft-p-min 0.60-0.75` suele ayudar en tarjetas de poco ancho de banda, y `--parallel 1` es obligatorio para medir.
- Un desbordamiento de VRAM (por ejemplo, contexto de más) puede reducir la velocidad a la mitad sin dar error.

**Estimación mía (a confirmar midiendo):**

- 3060 ≈ 360 GB/s, techo ~34 tok/s sin MTP, ~25 realista. Con MTP, ~35-45.

**Lo que no sé (depende de tu código):**

- Cómo construye hoy `lib/llama.sh` el comando de `llama-server`.
- Qué flags acepta **tu** build de llama.cpp.
- Cómo declara Pi el modelo (ventana de contexto, id, razonamiento).
- Cómo se registran los modelos en el menú y en `config.sh`.

## 2. Por qué el script anterior no vale tal cual

- Lanza `llama-server` con sus propios flags, no con **el mismo comando que usa tu proyecto**. Medir otra cosa que lo que ejecutas en producción no sirve.
- Usa un puerto y variables propios en lugar de `QWEN_PORT`, `QWEN_LLAMA_BIN` y `QWENX_*`.
- No pasa por tu resolución de modelos (`_qwen_model_path`) ni por tus perfiles.
- Solo se probó contra un servidor simulado; los flags reales no están validados en tu build.

**Principio de diseño:** una única fuente de verdad. El barrido debe llamar a la misma función que construye el comando en producción y solo añadir/quitar los flags de speculative decoding.

## 3. Archivos que necesito ver

| Archivo | Para qué |
|---|---|
| `lib/llama.sh` | Cómo se arma el comando de `llama-server`; el punto donde meter flags por modelo |
| `qwen-local.sh` (entero) | `_qwen_run_local`, alias de comandos, `qwen-status` |
| `lib/config.sh` (versión actual) | Variables y `_qwen_model_path` tras mis parches |
| `menu/qwen-menu.py` (versión actual) | Lista `MODELS`, `find_model`, la fila de carpeta |
| Config de Pi en `~/.pi-qwen/agent/` | Ventana de contexto y id del modelo (debe coincidir con `-c`) |
| Salida de `llama-server --version` y `--help` filtrado | Qué flags existen en tu build |
| `git status --short` y `git log --oneline \| head -5` | Saber qué parches están aplicados |
| `ls -lh ~/models` y nombre exacto del `.gguf` nuevo | Resolución del modelo (guion o guion bajo en `IQ3_XXS`) |
| Log de arranque del servidor con el modelo | Comprobar que carga la cabeza MTP (`nextn`) y el tamaño real del KV |

## 4. Fases

### Fase 0: preparación (sin tocar el proyecto)

1. Recompilar llama.cpp: `-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86`.
2. `qwen-stop` y confirmar que la GPU queda en ~700 MiB (nada de kev en CUDA).
3. Verificar que los flags existen en el build: `--spec-type`, `--spec-draft-n-max`, `--spec-draft-p-min`, `-fa`, `--cache-type-k/v`.

**Criterio de salida:** el modelo carga y genera con `-np 1` y contexto 8K.

### Fase 1: línea base y barrido

1. Adaptar el barrido para que **use la función de `lib/llama.sh`** y las variables de `config.sh`.
2. Configuraciones: sin MTP, n-max 2, 3, 4, y p-min 0.60 / 0.75.
3. Ejes secundarios, uno a la vez: `-ub` (256/512), caché KV (`q8_0` / `q4_0`), contexto (8K / 16K / 32K).
4. Registrar tok/s, aceptación y VRAM final.

**Criterio de salida:** una configuración ganadora con ≥ 600 MiB de VRAM libres y sin spill.

### Fase 2: integración como modelo propio

1. Nuevo id de modelo (por ejemplo `q27`) con **patrón de glob que no choque** con el «IQ3» del 35B.
2. Perfil de flags **por modelo**, no globales. El 27B no usa `--n-cpu-moe`, y el contexto y la caché KV son distintos de los del MoE.
3. Entrada en el menú (`MODELS`) con su tamaño y descripción.
4. `qwen-status` muestra el modelo, el n-max activo y la VRAM.
5. Pi: ventana de contexto igual a `-c`.

**Criterio de salida:** `qwen` con el 27B funciona desde el menú y el 35B sigue igual (prueba de regresión).

### Fase 3: coexistencia con laya/kev

- Con el 27B cargado: kev-0.8b en **CPU** (mismo criterio que con el 35B). El 4B en CUDA es incompatible, porque ocupa ~8,9 GB.
- `claude-kev` (4B en CUDA, sin modelo grande) no cambia.
- Comprobar que el menú no deja marcar combinaciones que no caben.

### Fase 4: uso real

- Probar con Pi en una tarea real y medir el tiempo hasta la respuesta.
- Qwen3.8 razona por defecto, y esos tokens cuentan. Evaluar un `reasoning_effort` menor frente al esfuerzo por defecto.

## 5. Pruebas y rollback

- **Regresión:** arrancar el 35B (Base e IQ3) antes y después. Mismo comando, mismos tok/s ±5 %.
- **Rollback:** cada parche hace copia `.bak-*` y es idempotente. Se puede volver con `git checkout -- <archivo>` o restaurando la copia.
- **VRAM:** comprobar con `nvidia-smi` tras la carga y tras 10 minutos de uso (el KV crece).

## 6. Riesgos

| Riesgo | Mitigación |
|---|---|
| VRAM justa (~1,6 GiB para KV + buffers + MTP) | Contexto 16K, `-ub` bajo, KV `q8_0`/`q4_0`, medir spill |
| Flags distintos en tu build | Verificar con `--help` antes de integrar |
| Glob del menú ambiguo con el IQ3 del 35B | Id propio y patrón más específico |
| `QWENX_CTX=100000` y `NCMOE=28` heredados | Perfil por modelo |
| MTP pierde ventaja con varias peticiones a la vez | `-np 1` |
| Prompts del barrido ≠ uso real | Validar el ganador con una tarea real en Pi |

## 7. Decisiones abiertas (tuyas)

1. ¿Contexto mínimo aceptable con Pi? Esto decide `q8_0` frente a `q4_0` y 16K frente a 32K.
2. ¿Vas a usar visión con este modelo? El proyector ocupa ~0,9 GB y en esta tarjeta no cabe.
3. ¿El 27B sustituye al 35B-A3B o conviven como opciones del menú?
4. ¿Prefieres razonamiento completo o reducido por defecto?
