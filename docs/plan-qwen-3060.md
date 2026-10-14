# Plan: Qwen3.6-35B-A3B en RTX 3060 12 GB + 32 GB RAM (Nobara + Claude Code)

Objetivo: máxima calidad con velocidad usable en la práctica.

**Estado (2026-10-14):** Fases 1 a 6 cerradas. Decisión: `qwen` = llama.cpp con UD-Q4_K_XL, thinking activado, `-b`/`-ub` 2048, `--n-cpu-moe` 28, contexto 131072. Ollama queda como `qwen-ollama`. Fase 7 no hace falta por ahora. La configuración vive en `qwen-setup.sh` (v6.1); el detalle de mediciones, en `checklist-qwen-3060.md`.

## Criterio de "usable" (umbrales propuestos, ajústalos)

- Generación ≥ 20 tok/s con 16k de contexto ocupado
- Primer mensaje en frío (~13k tokens de prompt) ≤ 30 s
- Mensajes siguientes ≤ 3 s hasta el primer token
- VRAM ≤ ~11,5 GB y RAM libre ≥ 4 GB

Dentro de esos límites: la cuantización más alta, el mayor contexto y thinking activado si compensa.

## Punto de partida (medido con Ollama)

- Generación: ~47 tok/s
- Procesado de prompt: ~285 tok/s, en trozos de 512 tokens
- Carga en frío: ~20 s

Conclusión: generar ya es bueno. Los cuellos de botella son el procesado del prompt y que la caché se pierda en cada mensaje.

---

## Fase 1: arreglo gratis hoy (5 min, sin cambiar de motor) — HECHA

Claude Code antepone al system prompt una cabecera de atribución con un hash distinto en cada petición. Eso invalida la caché KV del servidor local y hace la inferencia ~90 % más lenta según la guía de Unsloth. Afecta también a Ollama.

Se aplica solo a la config de Qwen (`~/.claude-local`), sin tocar tu `claude` de Pro (hoy lo hace `qwen-setup.sh`):

```bash
python3 - <<'EOF'
import json, os
p = os.path.expanduser("~/.claude-local/settings.json")
d = json.load(open(p)) if os.path.exists(p) else {}
d.setdefault("env", {})["CLAUDE_CODE_ATTRIBUTION_HEADER"] = "0"
json.dump(d, open(p, "w"), indent=2)
print("OK")
EOF
```

---

## Fase 2: instalar llama.cpp con CUDA en Nobara (~30 min) — HECHA

1. Verifica el driver: `nvidia-smi`
2. Dependencias: `sudo dnf install -y cmake gcc-c++ git libcurl-devel openssl-devel`
3. Necesitas el toolkit CUDA (`nvcc --version` debe responder). Si falta, instálalo desde el repo de NVIDIA para Fedora.
4. Problema probable en Nobara: el GCC del sistema suele ser más nuevo que el que soporta nvcc.
   - Solución: paquete `cuda-gcc-c++` de negativo17 (nvcc lo usa automáticamente).
   - Alternativa: compilar dentro de un toolbox de Fedora con CUDA (ver `docs/backend/CUDA-FEDORA.md` en el repo de llama.cpp).
   - Último recurso: añadir `-DCMAKE_CUDA_FLAGS="-allow-unsupported-compiler"` al cmake.
5. Compilar (la 3060 es arquitectura 86). En esta máquina falta `libcudart_static.a`, así que se compiló con runtime compartido:

```bash
git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp
cd ~/llama.cpp
CUDAFLAGS="--cudart shared" cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86 -DBUILD_SHARED_LIBS=OFF -DCMAKE_CUDA_RUNTIME_LIBRARY=Shared
cmake --build build --config Release -j --target llama-server llama-bench llama-cli
```

6. Verifica: `./build/bin/llama-cli --version` y revisa que el log de arranque mencione el backend CUDA. Resultado: build 11606 (0.6.0-dev), CUDA0: RTX 3060.

---

## Fase 3: descargar cuantizaciones — HECHA

Tamaños de referencia:

| Cuantización | Tamaño aprox. | Nota |
|---|---|---|
| UD-Q4_K_XL / Q4_K_M | ~21-22 GB | Mejor calidad que cabe (RAM+VRAM = 44 GB, margen justo) |
| Q3_K_XL | ~17 GB | Pérdida visible de calidad (no probada) |
| IQ3_XXS | ~12-15 GB | Pérdida visible de calidad, la más rápida (12,29 GiB) |
| 2 bits o menos | — | Descartar: la calidad colapsa |

El modelo denso 27B queda descartado: en una 4090 dio más precisión que el 35B-A3B pero a la mitad de velocidad, y en una 3060 sería mucho peor.

```bash
pip install --user -U huggingface_hub
mkdir -p ~/models
hf download unsloth/Qwen3.6-35B-A3B-GGUF --include "*UD-Q4_K_XL*" --local-dir ~/models
hf download unsloth/Qwen3.6-35B-A3B-GGUF --include "*IQ3_XXS*" --local-dir ~/models
```

---

## Fase 4: afinar `--n-cpu-moe` × batch (la clave) — HECHA

Dos palancas que Ollama no deja tocar:

- **`--n-cpu-moe N`**: manda los expertos MoE de las primeras N capas a la RAM y deja atención y capas pequeñas en la GPU. Un usuario con 12 GB de VRAM duplicó la generación (17 → 34 tok/s) al subirlo de 8 a 30. Otro, con una 3060 12 GB y 32 GB de RAM, pasó de 7,1 a 25,3 tok/s tras ajustar (con un MoE parecido).
- **`-b` / `-ub` (batch)**: el default físico (`-ub`) es 512, el mismo que usa Ollama. Con MoE parcialmente en CPU, subirlo acelera mucho el prefill (en un caso medido en una 3090, de ~380 a ~2090 tok/s con `-ub` 8192), a cambio de subir `--n-cpu-moe` para seguir cabiendo en VRAM y una pequeña caída en generación. Si no usas sesiones paralelas, iguala `-b` y `-ub`.

Primero libera la GPU: `sudo systemctl stop ollama`

Barrido de combinaciones:

```bash
M=~/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf
for ub in 512 1024 2048 4096; do
  for n in 40 36 32 28 24; do
    echo "== ub=$ub ncmoe=$n"
    ~/llama.cpp/build/bin/llama-bench -m "$M" -ngl 99 -ncmoe $n -b $ub -ub $ub -fa 1 -ctk q8_0 -ctv q8_0 -p 4096 -n 128 -r 1 2>&1 | grep -E 'pp4096|tg128|error'
  done
done | tee ~/bench-q4.txt
```

Cómo elegir:

1. Descarta las combinaciones que den error de memoria.
2. Elige la de mayor prefill (`pp`) y generación (`tg`) que no desborde.
3. Confírmala con `llama-server` a tu contexto real mirando `nvidia-smi`: `llama-bench` usa poco contexto, así que la VRAM real será mayor.
4. Si pasa de ~11,5 GB, sube `--n-cpu-moe` de 1 en 1.
5. Repite el barrido con IQ3_XXS.

**Resultado Q4_K_XL:** elegida `-b`/`-ub` 2048 con `--n-cpu-moe` 28 (más holgura de VRAM que `-ub` 4096 / `--n-cpu-moe` 32; el reproceso mínimo en caliente es `-ub` tokens).

**Resultado IQ3_XXS** (`-ub` 2048, pp4096 / tg128 en tok/s; `~/bench-iq3.txt`):

| `--n-cpu-moe` | pp4096 | tg128 |
|---|---|---|
| 28 | 1129,5 | 39,3 |
| 24 | 1176,5 | 43,1 |
| 20 | 1289,4 | 47,6 |
| 16 | 1415,7 | 53,0 |
| 12 | error de carga | |

Suelo: 16. Para el servidor se usó 18 (margen +2 por el contexto de 64k).

Referencia (no promesa): en un proyecto con RTX 3080 10 GB y 96 GB de RAM, IQ3_XXS dio ~55 tok/s generando a 128K, ~440 tok/s de prefill en frío y `--n-cpu-moe` 24. Tu 3060 tiene menos ancho de banda y menos RAM: espera menos. Ese repo (`drohack/llama-cpp-local`) trae `tune_ncpu.py`, una búsqueda binaria de `n-cpu-moe` bajo carga real que puedes adaptar.

Memoria del sistema:

- La velocidad de la RAM limita la inferencia MoE con offload. Revisa en la BIOS que XMP/EXPO esté activo y que tengas dual channel.
- `--load-mode none` (antes `--no-mmap`, ya eliminado en tu build) carga todo el modelo en RAM al inicio y evita lecturas de disco a mitad de generación.

---

## Fase 5: integrar con Claude Code (`qwen`, antes `qwenx`) — HECHA

La función ya no se pega a mano en `~/.bashrc`: la genera `qwen-setup.sh` en `~/.qwen-local.sh` (`./qwen-setup.sh` instala o actualiza, `./qwen-setup.sh --check` muestra el estado). Comandos resultantes:

- `qwen`: llama.cpp con Q4_K_XL (el que ganó en la Fase 6).
- `qwen-ollama`: Ollama, de respaldo.

Config de `qwen` (v6.1): `UD-Q4_K_XL`, `--n-cpu-moe 28`, `-b`/`-ub` 2048, `-c 131072`, KV q8_0, `-fa on`, `--load-mode none`, `--jinja`, puerto 8001. Plan mode como arranque (`permissions.defaultMode` en `~/.claude-local/settings.json`).

Variables de entorno para probar otras combinaciones sin tocar el script (los nombres siguen siendo `QWENX_*`):

```bash
QWENX_CTX=98304 qwen          # menos contexto
QWENX_NCMOE=30 qwen           # más expertos en RAM, menos VRAM
QWENX_NOTHINK=1 qwen          # sin thinking
QWENX_MODEL=~/models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf QWENX_NCMOE=18 qwen   # plan B
```

Notas de diseño:

- **Muestreo**: temperatura 0,6, top-p 0,95, top-k 20, min-p 0 (valores de Unsloth para modo thinking). La caché KV se cuantiza a q8_0 para ahorrar VRAM.
- **Thinking**: la variante sin thinking no mejoró nada (ver Fase 6); se queda activado.
- **Cierre**: al salir de Claude Code se mata el servidor y se libera VRAM y RAM.
- **Contexto**: Claude Code asume una ventana de 200k con modelos locales y `/autocompact` mostró 100k aunque se fijara menos. El script fija ventana 100000 y umbral = 84 % del contexto del servidor con tope 90 (a 131072: ~90k tokens, por debajo de los 131k del servidor). Falta comprobar con `/autocompact` que Claude Code respeta el valor.
- **VRAM medida (tras cargar):** 10368 MiB a 64k y 11262 MiB a 131072 (umbral 11500: margen ~240 MiB). Si con uso real se acerca al umbral, bajar a 98304 o subir `QWENX_NCMOE`.
- **WebSearch** incorporado: lo ejecuta el servidor de Anthropic y con backend local no hace nada (3 intentos, "Did 0 searches"). Denegado en `settings.json`.

---

## Fase 6: pruebas A/B y decisión — HECHA (2026-10-13)

Se usó `bench-qwen.sh` (proyecto de prueba: validador de RUT chileno con tests; etapa 1 en frío, etapa 2 en caliente con `-c`) y `decidir-fase6.py` para aplicar los umbrales. Una sola corrida por configuración.

| Config | Frío (s) | Caliente (s) | Gen mín (tok/s) | VRAM (MiB) | RAM mín (MiB) | Etapa 1 | Etapa 2 | Turnos | Tests | Veredicto |
|---|---|---|---|---|---|---|---|---|---|---|
| `q4-base` | 17,1 | 1,6 | 27,5 | 10701 | 7422 | 192 s | 29 s | 9/5 | OK | cumple todo |
| `q4-ctx32k` | 17,2 | 2,4 | 30,3 | 10350 | 7587 | 683 s | 75 s | 20/14 | OK | cumple todo |
| `q4-nothink` | 17,0 | 1,6 | 25,3 | 11027 | 6660 | 263 s | 31 s | 15/5 | OK | cumple todo |
| `iq3xxs` | 11,6 | 1,1 | 38,0 | 10345 | 16544 | 168 s | 31 s | 9/5 | OK | cumple todo |
| `base-ollama` | — | — | — | 11233 | 20227 | 900 s (timeout) | 67 s | ?/6 | FALLA | NO cumple: tests |

Variantes: `q4-base` = Q4_K_XL, thinking activado, ctx 64k; `q4-ctx32k` = `QWENX_CTX=32768`; `q4-nothink` = `QWENX_NOTHINK=1`; `iq3xxs` = IQ3_XXS con `--n-cpu-moe` 18; `base-ollama` = Ollama con el fix de la Fase 1.

Lecturas:

- **Ollama descartado**: timeout en la etapa 1 y tests rotos en la etapa 2.
- **Quitar thinking o contexto no acelera**: `q4-nothink` y `q4-ctx32k` necesitaron más turnos (el 32k tardó 683 s en la etapa 1; diferencia grande para ser solo varianza, sin explicar).
- **IQ3_XXS** es la más rápida (168 s, 38-45 tok/s) y deja ~16 GB de RAM libre, pero pierde calidad: es el plan B si Q4 se siente lento en uso real.

Regla de decisión (contexto > thinking > cuantización): gana `q4-base`. Después se subió el contexto a 131072 (VRAM 11262 MiB, bajo el umbral).

Hecho: `qwenx` pasó a `qwen` y el de Ollama a `qwen-ollama` (`qwen-setup.sh` v6).

Pendiente de validar: repetir `q4-base` para medir varianza, y comprobar la calidad con tu tarea real (no solo velocidad).

---

## Fase 7: opcional, solo si no alcanza

Con los resultados de la Fase 6 no hace falta. Se reabre si el uso real se siente lento o falla con 131072.

- **MTP (predicción multi-token)**: requiere compilar llama.cpp desde un PR en borrador sin fusionar y un GGUF MTP específico de Qwen3.6-35B-A3B. Los reportes se contradicen: uno habla de ~80 tok/s con 128K en 12 GB, y otro usuario con una 3060 12 GB dice que en chat normal obtiene más tok/s sin MTP. Compílalo en una carpeta aparte (`~/llama.cpp-mtp`) y mídelo con tu guion.
- **`--moe-expert-cache`**: un RFC de llama.cpp reporta +10 % a +34 % en generación con expertos en CPU. Todavía es una propuesta; solo vigilar.
- **ik_llama.cpp**: fork usado en builds pensados para offload a CPU. Pruébalo solo si llama.cpp principal se queda corto.

---

## Riesgos

- **Llamadas a herramientas**: reportes de la comunidad estiman que Qwen3.6 local falla ~10 veces más al formar llamadas a herramientas que los modelos alojados. Mantén los pasos chicos, el `CLAUDE.md` corto y el plan mode como arranque.
- **Cifras de blogs**: se descartaron artículos que prometen 150-190 tok/s en 12 GB sin indicar hardware ni método.
- **Calidad**: un usuario reportó alucinaciones con el 35B-A3B incluso en los primeros 10k tokens. En una sesión real el modelo ejecutó `date` (martes 13) pero resumió "martes 14". Verifica con tu tarea real, no solo con velocidad.
- **Memoria**: un Q4 de ~22 GB más KDE, navegador y Claude Code deja poco margen en 32 GB. Cierra apps pesadas al medir. Con 131072 la VRAM queda a ~240 MiB del umbral: mejor sin Brave abierto.
- **Conflicto de VRAM**: no dejes Ollama y llama-server cargados a la vez.

---

## Fuentes

- Guía de Unsloth para Claude Code local (cabecera de atribución, muestreo, KV q8_0, thinking): https://unsloth.ai/docs/basics/claude-code
- drohack/llama-cpp-local (referencia de rendimiento y script de afinado): https://github.com/drohack/llama-cpp-local
- `--n-cpu-moe` duplica la generación en 12 GB: https://aiweekly.co/alerts/qwen3-moe-cpu-expert-offload-doubles-decode-speed-on-12gb-vram
- Qué LLM en RTX 3060 12 GB (7,1 → 25,3 tok/s tras ajustar): https://bestllmfor.com/guide/llm-rtx-3060-12gb/
- Efecto de `-ub` en el prefill con `--n-cpu-moe`: https://reddit.sentinel-team.org/posts/1tany5t/snapshots/2026-05-15T23%3A40%3A01.25497Z
- Guía de optimización MoE CPU+GPU (batch y offload de prompt): https://gist.github.com/DocShotgun/a02a4c0c0a57e43ff4f038b46ca66ae0
- Prueba en RTX 3060 12 GB con `--cpu-moe` y batch: https://linuxfr.org/users/jflesch/journaux/corrigendum-auto-heberger-ses-llm-ia-debordement-cpu-ram-mixture-of-experts-et-benchmarks.epub
- Comparativa de cuantizaciones de Qwen3.6-35B-A3B: https://modelfit.io/quant-compare/qwen3.6-35b-a3b/
- Hoja de VRAM para LLM locales: https://insiderllm.com/guides/vram-requirements-local-llms/
- JET (decisión con modelos existentes, 27B vs 35B-A3B en 4090): https://arxiv.org/pdf/2609.33874
- CUDA con GCC no soportado en Fedora (negativo17): https://negativo17.org/cuda-with-unsupported-gcc-versions/
- Velocidad de RAM como límite del offload MoE: https://reddit.sentinel-team.org/posts/1u17jhp/snapshots/2026-06-13T02%3A56%3A06.64152Z
- `--no-mmap` y ajuste de `--n-cpu-moe`: https://en.kocpc.com.tw/?p=3261
- MTP en llama.cpp con Qwen3.6-35B-A3B: https://reddit.sentinel-team.org/posts/1t82zxv/snapshots/2026-05-15T23%3A40%3A01.25497Z
- Reporte de una 3060 12 GB sin MTP: https://huggingface.co/LuffyTheFox/Qwen3.6-35B-A3B
- RFC de caché de expertos: https://github.com/ggml-org/llama.cpp/discussions/28248
- Tasa de errores en llamadas a herramientas con Qwen3.6 local: https://huggingface.co/sokada4/Qwen3.6-27B-GPTQ-Int4
