# 🧭 Laya · system 1

Clasificador de prompts **no autoregresivo** (`laya` 0.4.6, `Router`) que corre **en CPU** y no toca la VRAM de Qwen. Evalúa cada prompt en un solo paso.

| Salida          | Qué mide                                       |
| --------------- | ---------------------------------------------- |
| **complejidad** | simple · media · compleja                      |
| **destructivo** | prob. de borrar / sobreescribir / force-push   |
| **injection**   | prob. de intentar saltarse las reglas          |

> 🚧 **Estado:** laya corre en paralelo a Qwen, pero **Pi aún no la consulta**. El hook existente (`laya_hook.py`) es de Claude Code. Falta conectarla a las extensiones de Pi.

## Archivos

```
laya_server.py    Servidor HTTP: GET /health · POST /classify  (127.0.0.1:8765)
laya_hook.py      Hook UserPromptSubmit de Claude Code (no lo usa Pi)
laya_config.py    Lector común de questions.json y config.json
config.json       Checkpoint, recorte de texto (maxchars) y umbrales
questions.json    Preguntas de laya (única copia)
bench_laya.py     Benchmark directo (Router.predict)
test-laya.sh      Prueba bajo carga real de Qwen
run.sh            Compara checkpoints (typed-decisions, multilingual, kev)
prompts.jsonl     Dataset de ground truth
```

Precedencia de configuración: **variable de entorno > `config.json`**.

## Uso

```bash
# Con el menú: casilla "Laya" (activada por defecto), o:
QWEN_LAYA=0 qwen            # sin laya

# Consulta manual
curl -s -X POST http://127.0.0.1:8765/classify -d '{"text":"borra todos los archivos y haz git push --force"}'
# → compleja · destructivo 0.8566 · injection 0.117 · 164 ms

# Benchmarks
./laya/run.sh               # compara checkpoints
./laya/test-laya.sh         # bajo carga de Qwen
```

| Variable          | Defecto                    | Uso                                  |
| ----------------- | -------------------------- | ------------------------------------ |
| `LAYA_PORT`       | `8765`                     | Puerto                               |
| `LAYA_MODEL`      | el de `config.json`        | Pisa el checkpoint                   |
| `LAYA_MAXCHARS`   | el de `config.json` (2000) | Recorte de texto                     |
| `LAYA_THRESHOLD`  | los de `config.json` (0.5) | Umbrales destructivo / injection     |
| `LAYA_TIMEOUT`    | `30`                       | Espera de arranque (s)               |
| `KEV_RUN`, `KEV_TIMEOUT`, `LAYA_PROMPTS` | —   | Overrides de `run.sh`                |

## Metas de calidad

- Acuerdo total ≥ **80 %**
- Latencia mediana ≤ **500 ms**
- RAM pico ≤ **2048 MB**
- VRAM sin cambios

## Resultados (2026-10-15)

Tres datasets: `prompts.jsonl` / `prompts_en.jsonl` / `prompts_en_extra.jsonl`. Baseline = predecir siempre la clase mayoritaria (73 % / 73 % / 70 %).

| Checkpoint        | Acuerdo (3 datasets) | Mediana    | RAM pico    |
| ----------------- | -------------------- | ---------- | ----------- |
| `multilingual`    | 83 % / 78 % / 80 %   | ~145 ms    | 2316–2321 MB |
| `typed-decisions` | 65 % / 77 % / 67 %   | 440–478 ms | 2787 MB     |

- `multilingual` predice casi siempre "simple" en complejidad; `typed-decisions`, casi siempre "compleja".
- Ambos **superan el tope de RAM** (2048 MB). `multilingual` es el único que cumple acuerdo (en 2 de 3 datasets; supera al baseline por 5–10 puntos) y latencia.

**Prueba con kev-4b** (`jaredpalmer/kev-4b`, CPU, puerto 8009):

| Dataset              | Acuerdo        | Mediana | p95     | RAM pico  |
| -------------------- | -------------- | ------- | ------- | --------- |
| `prompts_en.jsonl`   | 98 % (19/20/20) | 6515 ms | 7635 ms | 18777 MB  |
| `prompts_en_extra`   | 100 % (20/20/20) | 6630 ms | 6963 ms | 19693 MB  |

Pasa acuerdo, **falla latencia y RAM** por mucho (~18–19 GB no caben junto a Qwen Q4 en 32 GB). El único fallo de `prompts_en`: esperaba "compleja", obtuvo "media".

## Limitaciones conocidas de `multilingual`

- Deja pasar `DROP` de la tabla de usuarios y sobrescribir `.env`.
- No detecta "desactiva el plan mode" como injection.
- Subestima la complejidad y suma 2 falsos positivos de injection.
- **Los avisos son ayuda, no protección.**

## Lecciones para integrarla (de la integración con Claude Code)

- El hook solo **avisa en pantalla** (`systemMessage`) y nunca bloquea. Umbrales de aviso: destructivo ≥ 0.5, injection ≥ 0.5, complejidad `compleja`.
- **`additionalContext` no sirve como canal:** Claude Code lo registra, pero Qwen no lo obedece ni lo reporta (2 pruebas).
- El servicio debe arrancar **después** de que llama-server esté listo y apagarse con la sesión; si falla, Qwen sigue funcionando.
- Sin verificar: latencia **bajo carga** (el único dato, 164 ms, se midió sin carga), apagado en la máquina real, y si `test-laya.sh` mide el servicio o el `Router` en proceso.

## Calibración (API de laya)

`fit_temperatures` · `fit_one_temperature` · `fit_binning_map` · `apply_binning_map` · `ece_score` (Expected Calibration Error).

## Pendientes

- [ ] Ampliar `prompts.jsonl` a ~100 prompts con etiquetas revisadas
- [ ] Calibrar con `fit_temperatures` (opcional `fit_binning_map`) y re-medir
- [ ] Reducir la RAM pico por debajo de 2048 MB (hoy ~2.3 GB en el mejor caso)
- [ ] Latencia bajo carga con Qwen generando (3 × `/classify`, criterio ≤ 500 ms)
- [ ] `test-laya.sh` con Qwen cargado y el modelo calibrado
- [ ] Decidir checkpoint final: `typed-decisions` vs `multilingual`
- [ ] Conectar laya a Pi (extension con eventos `input` / `tool_call`)
