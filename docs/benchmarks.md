# 📊 Benchmarks y decisiones

Qwen3.6-35B-A3B en **RTX 3060 12 GB + 32 GB RAM** con llama.cpp. Resumen de las mediciones que justifican la configuración por defecto.

> Las mediciones del 13-14 oct 2026 se hicieron con `bench-qwen.sh` usando Claude Code como harness (antes de pasar a Pi). Miden el servidor y el modelo, así que siguen siendo válidas para llama.cpp; los tiempos de "turnos" dependen del harness.

## Decisión

| Parámetro        | Valor                                   |
| ---------------- | --------------------------------------- |
| Modelo           | UD-Q4_K_XL (~20.8 GB)                   |
| `-b` / `-ub`     | 2048 (⚠ ver nota abajo)                 |
| `--n-cpu-moe`    | 28                                      |
| KV cache         | q8_0 · `-fa on`                         |
| Thinking         | activado                                |
| Muestreo         | temp 0.6 · top-p 0.95 · top-k 20 · min-p 0 |
| Plan B           | IQ3_XXS con `--n-cpu-moe` 18            |

**Regla de decisión:** contexto > thinking > cuantización.

> ⚠️ **Posible desajuste con el código actual:** estas mediciones se hicieron con `-b` y `-ub` en 2048, pero la referencia de variables de entorno de la repo da como defecto `QWENX_BATCH`/`QWENX_UB` = 2048/**512** y añade `-cram 2048` (cuya prueba sigue abierta). Si el código realmente lanza con `-ub 512`, estos números no describen la configuración en uso. Verifica con `qwen-status` o `ps` y alinea una de las dos cosas.

## Criterio de "usable"

- Generación ≥ 20 tok/s con 16k de contexto ocupado
- Primer mensaje en frío (~13k tokens) ≤ 30 s
- Mensajes siguientes ≤ 3 s hasta el primer token
- VRAM ≤ ~11.5 GB y RAM libre ≥ 4 GB

## Punto de partida (Ollama)

Generación ~47 tok/s · prompt ~285 tok/s (trozos de 512) · carga en frío ~20 s.
Cuellos de botella: procesado del prompt y caché KV perdida en cada mensaje.

## Barrido `--n-cpu-moe` × batch

`--n-cpu-moe N` manda los expertos MoE de las primeras N capas a RAM; `-ub` sube el prefill a costa de VRAM.

**Q4_K_XL:** candidatas `-ub` 4096 / ncmoe 32 y `-ub` 2048 / ncmoe 28. Elegida la segunda (`-ub` 2048 / ncmoe 28): VRAM 10020 MiB a 32k, frente a 8779 MiB de la otra. El reproceso mínimo en caliente es `-ub` tokens (~2k). Nota: la documentación original justificaba la elección por "más holgura de VRAM", pero estas cifras muestran lo contrario a 32k; el criterio real parece ser el menor reproceso en caliente.

**IQ3_XXS** (`-ub` 2048):

| `--n-cpu-moe` | pp4096 (tok/s) | tg128 (tok/s) |
| ------------- | -------------- | ------------- |
| 28            | 1129.5         | 39.3          |
| 24            | 1176.5         | 43.1          |
| 20            | 1289.4         | 47.6          |
| 16            | 1415.7         | 53.0          |
| 12            | error de carga | —             |

Suelo: 16. Servidor con 18 (+2 de margen por el contexto).

## Fase 6: pruebas A/B (2026-10-13)

Proyecto de prueba: validador de RUT chileno con tests. Etapa 1 en frío, etapa 2 en caliente. Contexto 64k (32k en `q4-ctx32k`). **Una sola corrida por configuración.**

| Config        | Frío (s) | Caliente (s) | Gen mín (tok/s) | VRAM (MiB) | RAM mín (MiB) | Etapa 1 | Etapa 2 | Tests | Veredicto      |
| ------------- | -------- | ------------ | --------------- | ---------- | ------------- | ------- | ------- | ----- | -------------- |
| `q4-base`     | 17.1     | 1.6          | 27.5            | 10701      | 7422          | 192 s   | 29 s    | OK    | cumple todo    |
| `q4-ctx32k`   | 17.2     | 2.4          | 30.3            | 10350      | 7587          | 683 s   | 75 s    | OK    | cumple todo    |
| `q4-nothink`  | 17.0     | 1.6          | 25.3            | 11027      | 6660          | 263 s   | 31 s    | OK    | cumple todo    |
| `iq3xxs`      | 11.6     | 1.1          | 38.0            | 10345      | 16544         | 168 s   | 31 s    | OK    | cumple todo    |
| `base-ollama` | —        | —            | —               | 11233      | 20227         | timeout | 67 s    | FALLA | no cumple      |

**Lecturas**

- **Ollama descartado:** timeout en la etapa 1 y tests rotos en la etapa 2.
- **Quitar thinking o contexto no acelera:** `q4-nothink` y `q4-ctx32k` necesitaron más turnos. El 683 s del 32k no está explicado.
- **IQ3_XXS** es la más rápida y deja ~16 GB de RAM libre, pero pierde calidad.

## VRAM vs contexto (Q4_K_XL, medido)

| `-c`   | VRAM (MiB)                          |
| ------ | ----------------------------------- |
| 32768  | 10020 (bajo carga)                  |
| 65536  | 10368–10414 reposo · 10701 máx bajo carga |
| 131072 | 11262 tras cargar (umbral 11500, margen ~240 MiB) |

Coste ≈ 12–14 MiB por cada 1000 tokens de contexto. La estimación lineal se quedó ~280 MiB corta a 131072.

> ⚠️ **Inconsistencia a resolver:** la decisión original fue **131072**, pero el valor por defecto actual es `QWENX_CTX=100000`. No hay medición de VRAM a 100000 en estos datos. O es intencional (y conviene medirlo), o hay que alinear el valor.

## Compilar llama.cpp (CUDA, arquitectura 86)

En esta máquina faltaba `libcudart_static.a`, así que se usa runtime compartido:

```bash
git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp
cd ~/llama.cpp
CUDAFLAGS="--cudart shared" cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86 \
  -DBUILD_SHARED_LIBS=OFF -DCMAKE_CUDA_RUNTIME_LIBRARY=Shared
cmake --build build --config Release -j --target llama-server llama-bench llama-cli
```

Resultado: build 11606 (0.6.0-dev), CUDA0: RTX 3060 11908 MiB. Si el GCC del sistema es demasiado nuevo para nvcc: paquete `cuda-gcc-c++` (negativo17, solo Fedora/Nobara) o `-DCMAKE_CUDA_FLAGS="-allow-unsupported-compiler"`. En esta máquina no hizo falta: nvcc usó `g++-15` como compilador host. Las notas de `dnf`/negativo17 vienen del plan original en Nobara; en Ubuntu/Kubuntu usa `apt`.

## Fix de caché KV (Claude Code)

Claude Code antepone una cabecera de atribución con hash distinto en cada petición, lo que invalida la caché KV. Con ese harness: `CLAUDE_CODE_ATTRIBUTION_HEADER=0`. Es específico de Claude Code; para Pi, la referencia ([`pi-qwen-referencia-v2.md`](pi-qwen-referencia-v2.md)) apunta a mantener el historial append-only y `preserve_thinking`.

## Riesgos

- **Llamadas a herramientas:** reportes de la comunidad estiman ~10× más fallos que en modelos alojados. Pasos chicos y plan mode.
- **Calidad:** hay reportes de alucinaciones desde los primeros 10k tokens. En una sesión real el modelo ejecutó `date` (martes 13) pero resumió "martes 14". Verificar con tareas reales.
- **Memoria:** un Q4 de ~22 GB más escritorio y navegador deja poco margen en 32 GB. Cerrar apps pesadas al medir.
- **VRAM:** no dejar Ollama y llama-server cargados a la vez.
- **Cifras de blogs:** se descartaron las que prometen 150–190 tok/s en 12 GB sin hardware ni método.

## Pendientes

- [ ] Repetir `q4-base` para medir varianza (y explicar el 683 s de `q4-ctx32k`)
- [ ] Validar calidad con tarea real; si no convence, plan B IQ3_XXS
- [ ] Medir VRAM bajo carga real al contexto elegido (100000 vs 131072)
- [ ] Prueba larga de `-cram` (el intento del 14-oct murió antes de medir RSS/swap finales)
- [ ] Opcional (solo si el uso real se siente lento): MTP, `--moe-expert-cache`, ik_llama.cpp

## Fuentes

- [Guía de Unsloth para Claude Code local](https://unsloth.ai/docs/basics/claude-code) · muestreo, KV q8_0, cabecera de atribución
- [drohack/llama-cpp-local](https://github.com/drohack/llama-cpp-local) · referencia de rendimiento y `tune_ncpu.py`
- [`--n-cpu-moe` duplica la generación en 12 GB](https://aiweekly.co/alerts/qwen3-moe-cpu-expert-offload-doubles-decode-speed-on-12gb-vram)
- [Guía de optimización MoE CPU+GPU](https://gist.github.com/DocShotgun/a02a4c0c0a57e43ff4f038b46ca66ae0)
- [Comparativa de cuantizaciones de Qwen3.6-35B-A3B](https://modelfit.io/quant-compare/qwen3.6-35b-a3b/)
- [CUDA con GCC no soportado en Fedora (negativo17)](https://negativo17.org/cuda-with-unsupported-gcc-versions/)
- [RFC de caché de expertos en llama.cpp](https://github.com/ggml-org/llama.cpp/discussions/28248)
