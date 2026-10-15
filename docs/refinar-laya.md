# Refinar laya para código

Guía de cómo funciona laya en este proyecto y qué palancas existen para mejorarla (configuración, datos, calibración y afinado). No trata de velocidad.

Basada en los archivos de `laya/` de la repo y en la documentación del paquete `laya` 0.4.6 (la versión instalada).

---

## Índice

1. [Cómo funciona laya](#1-cómo-funciona-laya)
2. [Dónde vive hoy la configuración](#2-dónde-vive-hoy-la-configuración)
3. [Palancas de refinamiento](#3-palancas-de-refinamiento)
4. [Ideas específicas para código](#4-ideas-específicas-para-código)
5. [Flujo de trabajo recomendado](#5-flujo-de-trabajo-recomendado)
6. [Plan a grandes rasgos](#6-plan-a-grandes-rasgos)
7. [Referencia rápida de la API](#7-referencia-rápida-de-la-api)
8. [Advertencias y límites](#8-advertencias-y-límites)

---

## 1. Cómo funciona laya

Laya **no** es un motor de reglas con un archivo de configuración. Es un modelo pequeño (un encoder, no autoregresivo) que responde **preguntas tipadas** sobre un texto en **un solo paso**, sin generar texto. Corre en CPU y no toca la VRAM de Qwen.

Tipos de pregunta:

| Tipo | Devuelve | Ejemplo en este proyecto |
|---|---|---|
| `choice` | Etiqueta elegida, probabilidades por opción y confianza | `complejidad`: simple / media / compleja |
| `score` | Nivel esperado en una escala ordinal | (no se usa todavía) |
| `noul` | Probabilidad de que la respuesta sea **sí** (0.0–1.0) | `destructivo`, `injection` |

Las tres preguntas actuales:

- **complejidad:** ¿qué tan compleja es la petición de ingeniería de software?
- **destructivo:** ¿pide borrar, sobrescribir o hacer force-push de datos, archivos o historial?
- **injection:** ¿intenta que el asistente ignore sus reglas o instrucciones?

El servidor (`laya_server.py`) carga el `Router` una vez y expone `GET /health` y `POST /classify` en `127.0.0.1:8765`. El hook (`laya_hook.py`) consulta ese servicio y muestra avisos.

> **Importante:** el hook es un hook `UserPromptSubmit` de **Claude Code**. **Pi todavía no consulta a laya**: en el menú, la opción Laya hace que el servidor corra en paralelo, pero ningún prompt pasa por él hasta conectarlo con el mecanismo de extensiones de Pi.

---

## 2. Dónde vive la configuración

Desde la Fase 0 hay una sola fuente (comprobada solo con `py_compile`, `bash -n` y validación de JSON; no se ejecutó el servidor):

| Qué | Dónde | Estado |
|---|---|---|
| Preguntas | `laya/questions.json` | Única copia; servidor y bench la leen con `laya_config.py` |
| Checkpoint | `model` en `laya/config.json` | `LAYA_MODEL` lo pisa; `lib/config.sh` ya no define un valor por defecto |
| Recorte de texto | `maxchars` en `laya/config.json` (2000) | Sigue "elegido sin medir"; `LAYA_MAXCHARS` lo pisa |
| Umbrales de aviso | `thresholds` en `laya/config.json` (0.5 y 0.5) | Los leen hook y bench; `LAYA_THRESHOLD` los pisa. Siguen sin medirse |
| Dataset de evaluación | `prompts.jsonl` (20 filas) | Muy pequeño para medir o calibrar |
| Criterios de éxito | `laya.md` (acuerdo ≥ 80 %, latencia ≤ 500 ms, RAM ≤ 2048 MB, VRAM sin cambios) | — |

Antes de la Fase 0, el diccionario `Q` estaba duplicado en `laya_server.py` y `bench_laya.py` (se verificó que eran idénticas) y el `0.5` aparecía por separado en el hook y en el bench.

---

## 3. Palancas de refinamiento

De menor a mayor esfuerzo.

### 3.1 Unificar la configuración

**Hecho (Fase 0).** Una sola fuente de verdad:

- `laya/questions.json`: las preguntas.
- `laya/config.json`: checkpoint, recorte de texto y umbrales.
- `laya/laya_config.py`: lector común (solo biblioteca estándar, porque el hook corre con el python3 del sistema).

El servidor, el bench y el hook leen de ahí. Precedencia: variable de entorno > `config.json`. Todo se puede cambiar en un solo sitio, que era lo que el resto de las fases necesitaba.

### 3.2 Reescribir preguntas y criterios

Ayuda, pero **tiene un techo**: según la documentación del paquete, los checkpoints base rinden casi al azar sin ajuste en su benchmark de decisiones tipadas (0,36 y 0,35 frente a 0,32 de azar), y la mejora grande viene de afinarlos con datos propios.

Reglas prácticas de la documentación:

- Evita etiquetas tipo `true`/`false` o `yes`/`no` en preguntas `choice`; el modelo puede seguir la etiqueta en vez de la descripción. Usa etiquetas semánticas u opacas (`A`/`B`) y valídalas.
- Las etiquetas semánticas **no** hacen seguras las negaciones (ver §8).
- `noul` admite un mapeo opcional `labels` y `criteria` (`false`/`true`) para cambiar cómo se le presenta la pregunta al modelo; validar siempre con datos propios.

### 3.3 Mejorar el dataset

20 prompts no alcanzan para medir ni para calibrar. Objetivo: **cientos** de prompts reales, en español e inglés (tus prompts son en español; por eso `multilingual`), divididos en entrenamiento, validación y prueba.

Casos difíciles que conviene incluir:

- **Negaciones:** "no hagas `git push --force`", "no borres la carpeta build".
- **Mención sin petición:** "explícame qué hace `rm -rf`" (no es destructivo).
- **Texto pegado de archivos** con instrucciones dentro (injection en el contenido, no en la petición del usuario).
- **Tareas ambiguas** que se parecen a dos niveles de complejidad.
- **Mezclas** de destructivo + injection.

También conviene revisar la **consistencia de las etiquetas**: definir por escrito qué cuenta como "destructivo" (¿borrar `build/` y `.log` cuenta igual que borrar una tabla de producción?) y qué separa simple / media / compleja. Si el criterio humano es ambiguo, el modelo no puede aprenderlo. Si la severidad importa, `destructivo` podría pasar a ser una pregunta `score` en vez de `noul`.

Formato actual de cada fila de `prompts.jsonl`:

```json
{"text": "...", "complejidad": "simple|media|compleja", "destructivo": false, "injection": false}
```

Campos opcionales (`bench_laya.py` los ignora): `"idioma": "es"` o `"en"`, y `"tags"` con los casos difíciles de arriba (`negacion`, `mencion`, `pegado`, `ambigua`, `mezcla`), para medir el acierto por tipo de caso. Los criterios de etiquetado están en `laya/etiquetado.md`.

### 3.4 Calibrar

Los modelos salen **sobreconfiados**: `laya-multilingual` ni siquiera trae temperaturas ajustadas. Con datos propios se ajusta cuánto creer en cada probabilidad. El paquete ofrece:

- `fit_temperature_map`: temperatura por tipo de pregunta y por grupo de opciones.
- `fit_binning_map` / `apply_binning_map`: recalibración por intervalos.
- `fit_abstention_thresholds`: umbrales de abstención por grupo, para un error objetivo.
- `ece_score`: mide el error de calibración.

Límites de tamaño de muestra (constantes del paquete):

| Qué se ajusta | Mínimo de registros |
|---|---|
| Temperatura por **tipo** (`choice`, `noul`…) | 10 |
| Temperatura por **grupo** (tipo × nº de opciones) | 2000 |
| Umbral de abstención por grupo | 100 |

Con un dataset de ~100 prompts y 3 preguntas, solo saldría la calibración **por tipo** y los umbrales de abstención quedarían justos. Para evaluar la mejora, usar datos **separados** de los de ajuste (`compute_ece=True` reserva una parte).

> Pendiente por verificar: cómo aplicar el resultado de la calibración al `Router` que usa `laya_server.py` (el paquete lo documenta para `Agent`).

### 3.5 Abstención con `min_confidence`

`predict(..., min_confidence=…)` marca una respuesta como `low_confidence` cuando su confianza no llega al umbral, sin tocar la respuesta cruda. Acepta un número o un mapa por grupo (por ejemplo `"choice:3-5"`, `"default"`). Para un guardia de seguridad suele convenir "avisar solo si está seguro". Los umbrales se **ajustan** (§3.4), no se eligen a ojo: la misma cifra de confianza no significa lo mismo con distinto número de opciones.

### 3.6 Reducir el sesgo por posición (opcional)

La posición de una opción cambia la respuesta. En preguntas `choice` como `complejidad` (3 opciones) se puede promediar rotando el orden con `option_order`; en las pruebas del paquete bajó de 16,3 % a 6,1 % las respuestas que cambian según el orden. Cuesta k filas por pregunta dentro del mismo paso.

### 3.7 Afinar el modelo (fine-tuning)

Según la documentación es donde está **la mayor parte del valor**: en su benchmark, el checkpoint afinado llega a 0,766 frente a 0,36 del base. Se hace con `laya.train` (`finetune(...)`), con notebooks de ejemplo para Kaggle (2×T4) y Apple Silicon. Referencia de coste: unas 4–5 h para 4 épocas sobre ~30 000 preguntas en 2×T4; con unos cientos de ejemplos sería bastante menos. Requiere GPU o mucha paciencia.

Hay también un layout "parallel" que hace al modelo invariante al orden de opciones (requiere `transformers>=5` y solo funciona en el backend eager).

---

## 4. Ideas específicas para código

- **Clasificar solo la instrucción del usuario**, no el código ni los archivos pegados. Reduce falsos positivos de injection y evita agotar el límite de tokens (el multilingual trae 1024 tokens por defecto; admite hasta 8192 con `max_len=8192`).
- **Comparar con los presets del paquete** como línea base: `laya.router_questions()` y `laya.guard_questions()`. Si tus preguntas no los superan en tu dataset, no aportan.
- **Elegir checkpoint con datos:** `multilingual` (español, más rápido) frente a `typed-decisions` (afinado para flujos en inglés). `bench_laya.py` admite pasar el checkpoint como argumento; sin argumento usa el de `config.json`.
- **Cambiar las preguntas por otras más útiles**, por ejemplo "¿necesita escribir o ejecutar bash?", que podría elegir automáticamente el perfil de solo lectura o de edición. Cada pregunta nueva necesita su etiquetado.
- **Cuidado con el texto largo:** `LAYA_MAXCHARS=2000` recorta; mide si el recorte hace perder la parte que decide la etiqueta.

---

## 5. Flujo de trabajo recomendado

```
1. Reunir prompts reales ──► etiquetar ──► prompts.jsonl (entrenamiento / validación / prueba)
2. Config única ──► questions.json + archivo de umbrales (servidor, bench y hook leen lo mismo)   [hecho]
3. Ejecutar el bench ──► revisar fallos por pregunta ──► reescribir criterios ──► repetir
4. Si la redacción se estanca ──► calibrar ──► fijar umbrales por grupo (min_confidence)
5. Si aún no alcanza ──► afinar el modelo con tus datos
6. Conectar laya a Pi (extensiones/hooks de Pi) para que actúe de verdad como "system 1"
```

Criterios de éxito ya definidos en `laya.md`: acuerdo total ≥ 80 %, latencia mediana ≤ 500 ms, RAM pico ≤ 2048 MB, VRAM sin cambios.

---

## 6. Plan a grandes rasgos

> Esbozo para ordenar el trabajo. Cada fase se profundiza en otra sesión.

```
Fase 0 ─► Fase 1 ─► Fase 2 ─► Fase 3 ─► Fase 4 ─► (Fase 5) ─► Fase 6
config    datos     medir     iterar    calibrar   afinar       integrar con Pi
única                base      preguntas umbrales   si hace falta
```

| Fase | Objetivo | Entregable | Sale cuando… |
|---|---|---|---|
| **0. Configuración única** | Que servidor, bench y hook lean lo mismo | `questions.json` + archivo de configuración (checkpoint, recorte, umbrales) | Cambiar una pregunta o un umbral se hace en un solo sitio |
| **1. Datos** | Un dataset que permita medir de verdad | `prompts.jsonl` ampliado (cientos de prompts, español e inglés, con negaciones y casos difíciles) y dividido en entrenamiento / validación / prueba, más una guía de etiquetado (`laya/etiquetado.md`), un validador (`validar_prompts.py`) y un divisor estable (`dividir_dataset.py`) | Las etiquetas son consistentes y hay casos difíciles de cada tipo |
| **2. Medición base** | Saber de dónde se parte | Resultados del bench por pregunta, por checkpoint (`multilingual` frente a `typed-decisions`) y frente a los presets del paquete | Hay una tabla de referencia contra la que comparar |
| **3. Iterar preguntas** | Mejorar redacción y criterios | Versión revisada de `questions.json` | El acuerdo total llega a ≥ 80 % en validación, o se confirma que la redacción ya no mejora |
| **4. Calibración y umbrales** | Que las probabilidades signifiquen algo | Temperaturas y umbrales por grupo, y `min_confidence` aplicado | Los umbrales salen de datos, no de `0.5` a ojo |
| **5. Afinado (condicional)** | Subir la precisión si 3 y 4 no bastan | Checkpoint afinado con datos propios | Se supera la medición de la fase 2 en datos de prueba |
| **6. Integración con Pi** | Que laya actúe como "system 1" | Conexión con las extensiones/hooks de Pi | Un prompt pasa por laya y produce un efecto (aviso, bloqueo o elección de perfil) |

**Orden y dependencias:** 0 → 1 → 2 → 3 → 4 son secuenciales. La fase 5 solo se hace si hace falta. La fase 6 depende de saber cómo se extiende Pi y puede adelantarse con una configuración provisional para probar el circuito completo.

**Preguntas abiertas para la próxima sesión**

- ¿De dónde saldrán los prompts reales? (por ejemplo, un registro local de tus prompts, con tu consentimiento y sin salir de tu máquina)
- ¿Hay GPU disponible para afinar el modelo o habría que usar un servicio externo?
- ¿Qué debe hacer laya cuando detecta algo: avisar, pedir confirmación, bloquear o elegir el perfil de herramientas?
- ¿Qué otras preguntas serían útiles para código además de las tres actuales?
- ¿Cómo se aplica la calibración al `Router` que usa el servidor? (por verificar)
- Documentación de extensiones o hooks de Pi, necesaria para la fase 6.

### Estado por pasos (resumen inicial)

| Paso | Qué | Estado |
|---|---|---|
| 1 | `questions.json` y configuración única; servidor, bench y hook los leen | Hecho (solo comprobado con `py_compile` / `bash -n`) |
| 2 | Ampliar y etiquetar el dataset (con negaciones y casos difíciles) | En curso: herramientas listas (§6.1); faltan los prompts |
| 3 | Bench por pregunta y por checkpoint; comparar con presets | Pendiente |
| 4 | Calibración y umbrales de abstención | Pendiente |
| 5 | Fine-tuning (si hace falta) | Pendiente |
| 6 | Integración con Pi | Pendiente (hace falta la documentación de extensiones de Pi) |

### 6.1 Fase 1: herramientas (ya creadas)

| Archivo | Para qué |
|---|---|
| `laya/etiquetado.md` | Criterios de etiquetado. Parte de cómo están etiquetadas hoy las 20 filas y deja marcado lo que **aún no está decidido** |
| `laya/validar_prompts.py` | Revisa formato y etiquetas de `prompts.jsonl` y resume cuántas filas hay por clase, idioma y tipo de caso difícil |
| `laya/dividir_dataset.py` | Reparte las filas en `laya/datos/entrenamiento.jsonl`, `validacion.jsonl` y `prueba.jsonl` |

El reparto es **estable**: depende del hash del texto, no de la posición ni del azar, así que al agregar prompts nuevos los anteriores no cambian de grupo y la prueba no se contamina. Con pocas filas los grupos salen desbalanceados; el divisor avisa si a un grupo le falta alguna clase.

Flujo: etiquetar → `python3 laya/validar_prompts.py` → `python3 laya/dividir_dataset.py`.

Estado: las herramientas se comprobaron solo con las 20 filas actuales y con casos mal formados a propósito. Para cerrar la fase falta el contenido: de dónde salen los prompts reales y las decisiones marcadas como "Sin decidir" en `etiquetado.md`.

---

## 7. Referencia rápida de la API

```python
from laya import Router

router = Router(device="cpu", max_loaded=1)
res = router.predict(texto, questions, model="multilingual")
a = res["answers"]
a["complejidad"]["choice"]        # "simple" | "media" | "compleja"
a["destructivo"]["noul"]          # probabilidad de "sí"
res["routing"]["model"]           # checkpoint elegido
```

Parámetros útiles de `Router.predict`: `model`, `max_len`, `head_max_len`, `min_confidence`.

Formato de una pregunta:

```python
{"type": "choice", "instructions": "...", "criteria": {"simple": "...", "media": "...", "compleja": "..."}}
{"type": "noul",   "instructions": "..."}      # opcional: "criteria": {"false": "...", "true": "..."}, "labels": {...}
{"type": "choice", ..., "option_order": [2, 0, 1]}
```

Módulo de calibración: `laya.calibrate` (`fit_temperature_map`, `fit_temperatures`, `fit_one_temperature`, `fit_abstention_thresholds`, `fit_binning_map`, `apply_binning_map`, `records_from_labeled`, `calibration_payload`).

Entrenamiento: `from laya.train import TrainConfig, finetune`.

---

## 8. Advertencias y límites

- **Negación:** la documentación documenta casos en los que peticiones negadas se clasifican como la acción que se niega, a veces con probabilidad casi 1. No es una regla general, pero en código ("no borres…", "sin hacer push…") es un riesgo real de falsos positivos: hay que medirlo con datos propios.
- **Base casi al azar sin ajuste:** laya es "una base rápida para especializar", no un motor de decisión listo para usar.
- **Los umbrales dependen del tipo numérico** (dtype) con que se sirve; ajústalos y mídelos con el mismo que usará el servidor (en CPU, `LAYA_CPU_AMP=bf16` es opcional).
- **Los 0.5 de `config.json` no están medidos.** Hasta calibrar, tómalos como valores provisionales.
- **Casi nada se ha ejecutado:** la Fase 0 está aplicada pero solo comprobada con `py_compile`, `bash -n` y validación de JSON (no se arrancó el servidor con la config nueva). El resto describe el diseño y lo que documenta el paquete; esas fases aún no existen en la repo.
