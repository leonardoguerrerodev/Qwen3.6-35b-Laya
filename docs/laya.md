# Laya — Progreso

Motor de decisión no-autoregresivo (laya v0.4.6, Router de jaredpalmer/kev-4b) para clasificar prompts de Qwen en CPU, sin tocar VRAM.

## Qué hace

- Recibe un prompt de Qwen → clasifica 3 dimensiones en un solo forward pass:
  - **complejidad**: simple / media / compleja
  - **destructivo**: booleano (¿borra/sobreescribe/force-push?)
  - **injection**: booleano (¿intenta ignorar reglas del sistema?)
- Latencia objetivo: ≤ 500 ms mediana
- RAM objetivo: ≤ 2048 MB
- Corre en CPU, no toca VRAM de Qwen

## Estructura del repo

```
laya/
├── bench_laya.py      # Benchmark directo en Python (Router.predict)
├── laya_server.py     # Servidor HTTP (no usado en flujo principal)
├── laya_hook.py       # Hook para integrar con Qwen
├── prompts.jsonl      # Dataset de ground truth (20 prompts)
├── run.sh             # Corre bench de ambos checkpoints (typed-decisions, multilingual)
├── test-laya.sh       # Prueba bajo carga real de Qwen (4 configs × N repeticiones)
└── .venv/             # venv con laya 0.4.6
```

## Progreso

### ✅ Instalación y configuración
- [x] Clonado del repo `Qwen3.6-35b+Laya` en `/run/media/xaski/7c0ba586-.../!GitHub/!Obsedium/Qwen3.6-35b+Laya/`
- [x] venv creado con laya 0.4.6 instalado
- [x] `bench_laya.py` funciona (corre `Router.predict()` en CPU)
- [x] `run.sh` corre ambos checkpoints: `typed-decisions` y `multilingual`
- [x] `test-laya.sh` mide rendimiento bajo carga de Qwen (4 configuraciones)

### ✅ Hook para Qwen
- [x] Hook copiado y registrado en `settings.json`
- [x] `_laya_up` / `_laya_down` en `~/.qwen-local.sh`
- [x] `QWEN_LAYA_DIR` apuntando al venv

### Pendiente
- [ ] **Ampliar `prompts.jsonl` de 20 a ~100 prompts** con etiquetas revisadas (complejidad, destructivo, injection)
- [ ] **Correr `bench_laya.py multilingual`** para línea base de accuracy con prompts actualizados
- [ ] **Calibrar con `fit_temperatures`** (laya API: recalibra probabilidades del modelo)
- [ ] **Opcional: `fit_binning_map` / `apply_binning_map`** para recalibrar decisiones por bins
- [ ] **Re-medir accuracy después de calibración** y comparar
- [ ] **Correr `test-laya.sh`** bajo carga real de Qwen (4 configs) con el modelo calibrado
- [ ] **Decidir checkpoint final**: `typed-decisions` vs `multilingual` (comparar accuracy + latencia)

## Notas técnicas

### Timing estimado
- Inferencia directa en Python (sin HTTP): ~50–150 ms por prompt en CPU
- 20 prompts: ~1–3 segundos
- 100 prompts: ~5–15 segundos
- Primera llamada: descarga + carga del checkpoint (~10–30s una vez, one-time)

### Modelos disponibles
- `typed-decisions` — checkpoint con tipos de decisión
- `multilingual` — checkpoint multilingüe

### API de calibración de laya
- `fit_temperatures` — ajusta temperatura para mejorar probabilidades
- `fit_one_temperature` — ajusta una sola temperatura global
- `fit_binning_map` — mapeo de bins para recalibración
- `apply_binning_map` — aplica mapeo de bins
- `ece_score` — mide error de calibración (Expected Calibration Error)

### Criterios de éxito (del plan)
- Acuerdo total >= 80%
- Latencia mediana <= 500 ms
- RAM pico <= 2048 MB
- VRAM sin cambios (0 MB usada)
