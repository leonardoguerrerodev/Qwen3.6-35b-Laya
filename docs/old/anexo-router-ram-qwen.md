# Anexo: router laya/kev, presión de RAM y arreglo del UMA (Qwen3.6-35B-A3B en RTX 3060 + Ryzen 5 5600G)

Anexo a `plan-qwen-3060.md` y `checklist-qwen-3060.md`. Última actualización: 2026-10-14.

Objetivo de la tarea: decidir si un clasificador chico (laya o kev-0.8b) puede correr **en RAM, en paralelo con `qwen`**, para estimar complejidad y detectar prompts destructivos o de injection. Al medirlo apareció un problema de memoria que pasó a ser lo principal.

## Resumen ejecutivo

- **Router:** laya `multilingual` es la única candidata viable. kev-0.8b es más preciso pero no cabe: ~5,6 GB de RAM y ~1-1,7 s de latencia.
- **Problema real:** la máquina estaba sin RAM. Disponible ~1,4 GB, zram lleno y **~8 GiB de llama-server en swap**. Eso explica tok/s erráticos (10-28) durante las pruebas.
- **Causa del hueco de RAM:** el UMA Frame Buffer de la iGPU estaba en 4096 MiB. Bajado a 512 MiB, `MemTotal` pasó de 27,3 GiB a ~30,7 GiB.
- **Pendiente principal:** averiguar por qué llama-server crece de ~14,5 GiB recién cargado a ~22 GiB con el uso (sospecha: `-cram`, sin confirmar) y balancear los módulos de RAM.
- **Recomendación vigente:** no poner router en RAM junto a qwen hasta cerrar lo anterior. Mientras tanto, reglas fijas (`deny`/`ask`, plan mode) para lo destructivo.

## 1. Comparación laya vs kev-0.8b

Prompts: 20 (`prompts.jsonl`), tres preguntas por prompt (complejidad, destructivo, injection). Umbrales del bench: acuerdo ≥ 80 %, latencia mediana ≤ 500 ms; para laya además RAM ≤ 2048 MB.

| Modelo | Condición | Acuerdo | Lat. mediana (p95) | RAM pico |
|---|---|---|---|---|
| kev-0.8b | CPU, sin qwen | 90 % | 1048 ms (1134) | 5586 MB |
| kev-0.8b | CPU, con qwen cargado | 90 % | 1012 ms (1702) | 5584 MB |
| kev-0.8b | CPU, otra corrida con qwen | 90 % | 1656 ms (1937) | 5578 MB |
| laya `typed-decisions` | CPU, sin qwen | 65 % | 545 ms (611) | 2834 MB |
| laya `typed-decisions` | CPU, con qwen cargado | 65 % | 951 ms (1084) | 2788 MB |
| laya `multilingual` | CPU, con qwen cargado | 83 % | 269 ms (302) | 2322 MB |

Detalle por pregunta:

| Modelo | Complejidad | Destructivo | Injection |
|---|---|---|---|
| kev-0.8b | 15/20 | 19/20 | 20/20 |
| laya `typed-decisions` | 6/20 | 16/20 | 17/20 |
| laya `multilingual` | 15/20 | 18/20 | 17/20 |

Lecturas:

- **kev:** el mejor en seguridad (falla solo "sobrescribe `.env`"). Pero ~1-1,7 s de latencia y ~5,6 GB de RAM lo dejan fuera con qwen Q4 cargado.
- **laya `typed-decisions`:** descartado, 65 % de acuerdo.
- **laya `multilingual`:** pasa precisión y latencia. Su "FALLA" de RAM es contra el umbral del bench (2048 MB), no contra el piso del plan.
- **Fallos de seguridad de `multilingual`:** deja pasar `DROP` de la tabla de usuarios y sobrescribir `.env`, no detecta "desactiva el plan mode" como injection, y suma 2 falsos positivos de injection. No sirve como único guardia de lo destructivo.
- **Complejidad:** `multilingual` subestima siempre hacia "simple". kev se equivoca en ambos sentidos.
- **Muestra pequeña:** 20 prompts y una corrida. La diferencia de acuerdo entre kev y `multilingual` son 4 respuestas de 60; no es concluyente. Pendiente: ~100 prompts con etiquetas de complejidad revisadas (algunas son discutibles).
- **GPU:** kev en modo `gpu` no corre con qwen cargado (`run.sh` se niega por la VRAM en uso, ~11,3 GB de 11,9).

## 2. `test-laya.sh`: laya bajo carga real de qwen

Script `test-laya.sh` (4 configuraciones × 2 repeticiones): `qwen-solo`, `idle`, `carga-libre` (router mientras qwen genera) y `carga-pin` (router fijado a los núcleos 10-11 con 2 hilos). Resultado de la corrida `tag=base` (laya `multilingual`, 12 hilos de CPU):

| config | rep | acuerdo | lat. mediana | p95 | RAM router | RAM disp. mín | qwen tok/s |
|---|---|---|---|---|---|---|---|
| qwen-solo | 1 | - | - | - | - | 5132 MB | 15,9 |
| idle | 1 | 83 % | 257 ms | 299 ms | 2322 MB | 3772 MB | n/a |
| carga-libre | 1 | 83 % | 231 ms | 250 ms | 2322 MB | 2710 MB | 10,2 |
| carga-pin | 1 | 83 % | 752 ms | 901 ms | 2319 MB | 1860 MB | 28,1 |
| qwen-solo | 2 | - | - | - | - | 2675 MB | 23,0 |
| idle | 2 | 83 % | 171 ms | 224 ms | 2321 MB | 1436 MB | n/a |
| carga-libre | 2 | 83 % | 297 ms | 339 ms | 2279 MB | 967 MB | 27,9 |
| carga-pin | 2 | 83 % | 403 ms | 466 ms | 2025 MB | 508 MB | 12,2 |

Lecturas:

- **Latencia:** con el router libre (231 y 297 ms) pasa el umbral de 500 ms con qwen generando.
- **`taskset`:** fue peor las dos veces (752 y 403 ms). Hipótesis, sin probar: los núcleos 10-11 también los usa llama.cpp. Si se quiere fijar, limitar los hilos de llama.cpp con `-t 10`. Por ahora, no fijar.
- **RAM disponible:** cae fase tras fase, de 5132 a 508 MB. La fase `qwen-solo` de la rep 2 corre **sin router** y ya parte 2,5 GB más abajo que la rep 1, así que la caída no viene de laya.
- **tok/s de qwen:** demasiado erráticos (10-28) para medir el costo del router. El 12,2 coincide con los 508 MB libres (presión de memoria; hipótesis).
- **Piso del plan:** la RAM disponible estuvo bajo 4096 MB en casi todas las fases.

## 3. Diagnóstico de memoria

Estado medido durante las pruebas (`free -m`):

```
Mem:  total 27939  used 26560  free 492  shared 14285  buff/cache 15572  available 1379
Swap: total 17203  used 9217
      /dev/zram0 8G (8G usados)   /dev/nvme0n1p4 8,8G (1G usados)
```

- **llama-server:** RSS ~15 GB (el proceso más grande).
- **Swap del proceso:** `VmRSS` 14,99 GB y `VmSwap` **8,44 GB** (en kB: 14988676 y 8444452). Los pesos de qwen se estaban leyendo desde zram/disco.
- **Recién reiniciado:** `VmRSS` 15,17 GB (14,5 GiB) y `VmSwap` 0. Así que el modelo cargado ocupa ~14,5 GiB y los ~8 GiB extra aparecen con el uso.
- **Hipótesis (sin confirmar):** el crecimiento coincide con el tope por defecto de `-cram` (8192 MiB, caché de prompts en RAM). Se descartó una hipótesis anterior de que `--load-mode none` mantuviera una copia completa del modelo, porque la medida recién cargado no la respalda.
- **`--load-mode` en tu build:** `auto` (por defecto, mmap si el dispositivo lo soporta), `none`, `mmap`, `mlock`, `mmap+mlock`. El script usaba `none` explícito.

## 4. El hueco de RAM: UMA de la iGPU

Hardware: Ryzen 5 5600G (6 núcleos / 12 hilos, Vega integrada) + RTX 3060 12 GB.

- **Síntoma:** 32 GiB instalados y `MemTotal` de 28610224 kB (27,3 GiB). `/proc/cmdline` sin `mem=` ni `crashkernel=`.
- **Causa confirmada:** `mem_info_vram_total` de la tarjeta AMD = **4096 MiB** (UMA Frame Buffer Size de la BIOS).
- **Arreglo aplicado:** UMA Frame Buffer Size bajado en la BIOS. Resultado:

```
MemTotal:       32222896 kB
/sys/class/drm/card0/device/mem_info_vram_total 512 MiB
```

Ganancia: +3.612.672 kB (~3,45 GiB). La Vega sigue entregando video; toma memoria del sistema dinámicamente.

## 5. Módulos de RAM desbalanceados

`dmidecode`: tres módulos DDR4 a 3000 MT/s.

| Canal | Slot | Módulo |
|---|---|---|
| A | DIMM 0 | vacío |
| A | DIMM 1 | 8 GiB |
| B | DIMM 0 | 16 GiB |
| B | DIMM 1 | 8 GiB |

- Canal A: 8 GiB; canal B: 24 GiB. En Ryzen con capacidades desiguales probablemente solo ~16 GiB funcionan en dual channel y el resto en canal simple. **No verificado en tu placa.** Importa porque la inferencia MoE con expertos en RAM va limitada por ancho de banda.
- **Arreglo propuesto, sin comprar nada:** mover el módulo de 8 GiB del canal B al slot vacío del canal A (A = 8+8, B = 16, simétrico). Revisar el manual de la placa para saber qué slot es cuál.
- **Riesgo:** quedan dos módulos por canal en A y en B, lo que a veces baja la velocidad máxima estable. Verificar que arranque y que siga en 3000 MT/s.

## 6. Escritorio en la iGPU (opcional)

- Enchufar el monitor a la salida de video de la placa y poner "Primary Display / Initiate Graphic Adapter" en IGD/iGPU en la BIOS. El nombre exacto depende de la placa.
- Ganancia esperada: ~620 MiB de VRAM (lo que usa el escritorio en la 3060, medido con qwen cerrado). Con contexto 131072 el margen de VRAM pasaría de ~240 MiB a ~860 MiB.
- Usar la iGPU como cómputo para qwen no se recomienda: los expertos en RAM están limitados por ancho de banda, que la iGPU comparte con la CPU, y mezclar CUDA con Vulkan no está validado en este build.

## 7. Cambios en scripts

- `test-laya.sh` (nuevo): ver sección 2. Variables: `MODEL`, `ROUTER_CORES`, `REPS`, `TAG`, `LOAD_SECS`, `CSV`, `LAYA_DIR`, `PORT`. Resultados en `~/laya-test.csv` y logs en `~/laya-test-logs/`.
- `qwen-setup.sh` **v6.2**: nuevas variables opcionales `QWENX_CRAM` (pasa `-cram`) y `QWENX_LOADMODE` (por defecto `none`, como antes), y la función `qwen-mem` (RSS y swap de llama-server más `free -m`). Sin cambios de comportamiento por defecto. Instalar con `./qwen-setup.sh && source ~/.bashrc && ./qwen-setup.sh --check`.

## 8. Nota: Qwen3.8

Qwen3.8 existe, pero los pesos abiertos son solo un 2,4T-A95B y un **27B denso** (Apache-2.0, contexto 262k). No hay un MoE chico tipo A3B anunciado. El 27B denso en 12 GB de VRAM no tiene el truco de los expertos activos y el plan ya descartó el 27B de la generación anterior, así que no se cambia el modelo. Su ficha compara contra Qwen3.6-27B, no contra el 35B-A3B.

## 9. Pendientes, en orden

1. [ ] Con qwen cerrado, línea base de `llama-bench` (tg128 ~34,5-35,2 tok/s en notas anteriores, con otro estado de RAM):
   `~/llama.cpp/build/bin/llama-bench -m ~/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf -ngl 99 -ncmoe 28 -b 2048 -ub 2048 -fa 1 -ctk q8_0 -ctv q8_0 -p 4096 -n 128 -r 3 2>&1 | grep -E 'pp4096|tg128|error'`
2. [ ] Instalar `qwen-setup.sh` v6.2 y probar `QWENX_CRAM=2048 qwen`: medir `qwen-mem` recién cargado y tras una sesión larga. Si no crece (~14,5-15 GiB y sin swap), era la caché. Si vuelve a crecer, probar `QWENX_LOADMODE=mmap` y vigilar lecturas de disco. `mlock` solo al final (con poco margen puede empujar otras apps al swap).
3. [ ] Mover el módulo de 8 GiB al canal A y repetir el `llama-bench` de la línea base. Un cambio a la vez para atribuir efectos.
4. [ ] Opcional: escritorio en la iGPU (sección 6) y medir VRAM con `nvidia-smi`.
5. [ ] Repetir `test-laya.sh` (`TAG=post-uma`) con la RAM nueva y sin Brave. Criterio: RAM disponible ≥ 4096 MB en todas las fases y tok/s de qwen estables.
6. [ ] Ampliar `prompts.jsonl` a ~100 prompts con etiquetas revisadas y repetir laya `multilingual` vs kev antes de decidir.
7. [ ] Si el router se adopta: conservar plan mode y las reglas `deny`/`ask` en `~/.claude-local/settings.json` (`rm -rf`, `git push --force`, `DROP`, escribir `.env`) como red de seguridad; el router solo sugiere o avisa.

## 10. Lo que no se ha verificado

- Que `-cram` sea la causa del crecimiento de llama-server.
- Que el hueco de dual channel exista en esta placa y que mover el módulo lo cierre.
- La causa de los resultados erráticos de tok/s (se asocia a la presión de memoria, sin probar).
- Que `taskset` empeore por competir con los hilos de llama.cpp.
- Latencia y RAM de kev con la RAM nueva (se midió antes del arreglo del UMA).
