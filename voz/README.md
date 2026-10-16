# voz — TTS para Qwen (piper), independiente de TTSiro

Servidor HTTP local (mismo patrón que `laya/`: `/health` + un endpoint de trabajo) que lee texto en voz
alta usando [piper](https://github.com/OHF-Voice/piper1-gpl). Completamente separado de `!TTSiro`: venv
propio, modelo `.onnx` propio (en `QWEN_MODELS_DIR`, junto a los GGUF de Qwen), sin compartir ni un
archivo, socket o ruta con ese repo.

## Estado actual

Ciclo de vida del servidor (arrancar/parar junto con `qwen`, toggle en el menú), un cliente manual para
probarlo, y settings de voz en `/voz.html` (vía `qwen-web`) — ver abajo. **Todavía no hay conexión
automática con Pi** — eso es una fase aparte: una extension TS que llame a `/hablar` cuando Pi termine de
responder, una vez verificado contra el binario real de `pi` qué evento de su Extension API
(`message_end` / `agent_settled`) corresponde.

## Motores: piper · kokoro · s2 (16-oct-2026)

Cada perfil tiene un campo `motor` (falta → `piper`, así los perfiles viejos siguen valiendo):

| Motor | Voz del perfil | Dónde corre | Notas |
| --- | --- | --- | --- |
| `piper` | `.onnx` en `QWEN_MODELS_DIR` | en `voz_server.py` | rápido; `dispositivo` `gpu` = onnxruntime-gpu |
| `kokoro` | `ef_dora` · `em_alex` · `em_santa` | worker persistente `kokoro_worker.py` (venv `VOZ_KOKORO_VENV`) | más natural; 1ª frase ~5 s (carga), luego ~0,4 s; ~2 GB RAM; `dispositivo` `cpu`/`gpu` |
| `f5` | igual que `s2` (voz a clonar en `voz/refs/`) | worker persistente `f5_worker.py` (venv `VOZ_F5_VENV`, F5-Spanish de `jpgallegoar`) | clona la referencia; sin etiquetas; en CPU ~16× el audio, en GPU rápido; `dispositivo` `cpu`/`gpu`; licencia no comercial |
| `s2` | `voz/refs/<nombre>.wav` + `.txt` (voz a clonar) | un proceso por frase (fish-speech en `VOZ_FISH_DIR`) | **hace los sonidos de las etiquetas** `[sigh]` `[laughing]`…; en CPU ~10 min por frase y ~20 GB de RAM (no junto al Qwen 35B: se niega si hay menos de `VOZ_S2_RAM_MB`) |
| `s2gguf` | igual que `s2` + `cuant` (`q4_k_m`/`q8_0`) y `dispositivo` (`cpu`/`gpu`) | servidor [s2.cpp](https://github.com/rodrigomatta/s2.cpp) persistente en `127.0.0.1:8779` (`VOZ_S2CPP_DIR`, GGUF de `rodrigomt/s2-pro-gguf`) | S2 Pro cuantizado, con etiquetas; alpha. GPU solo sin el modelo grande (q4 ≈ 7,2 GB VRAM); log en `$QWEN_DATA/s2cpp.log` |

- Instalar kokoro, f5, s2, s2gguf y la GPU de piper/kokoro (una vez, necesita `uv`, `git`, `cmake`, CUDA y red): `qwen-voz-motores`.
- **`/voz.html` funciona con la voz apagada** (web_server.py lee/guarda `perfiles.json` con `voz_config`).
  **«Levantar voz»** deja el perfil en pantalla como activo y carga su modelo (enciende la voz si hacía falta;
  `POST /api/precargar` libera el motor anterior). `voz_server.py` precarga el activo al arrancar, así
  `qwen` + Voz usa el último elegido.
- Las etiquetas de la skill `voz-etiquetas` se quitan en `sintetizar()` salvo con `s2`.
- El hook de Pi no espera la voz (`void hablar(...)`) y usa `node:http` en vez de `fetch` (este corta a los 5 min).
- Elegir motor: `/voz.html` (selector **Motor**) o, en el menú TUI, `Z` para pasar al siguiente perfil.

## Settings de voz (perfil + parámetros, sin reiniciar nada)

`qwen-web` → `/voz.html` (mismo diseño que `!TTSiro`, adaptado): elegir voz, ajustar velocidad/tono/
volumen/expresividad/variación/pausa con sliders, probar con preview instantáneo (`POST /api/voz/probar`,
no toca nada guardado), guardar como perfil con nombre y «Activar» uno como el que usa `/hablar`. También
lista el catálogo de voces `es_*` de HuggingFace para descargar directo a `QWEN_MODELS_DIR`.

Los parámetros se resuelven **por request**, no al arrancar: cambiar de voz o ajustar un control no
reinicia `voz_server.py` (cada `.onnx` se carga una vez, perezoso, y queda cacheado en memoria). El "tono"
usa `rubberband` (debe estar en PATH) como post-proceso; si no cambia nada, no se usa (más rápido).

Los perfiles viven en `voz/perfiles.json` (gitignored — es ajuste personal, no algo del repo). Si no
existe, se arma uno de arranque con la voz/parámetros que resuelvan `VOZ_MODEL`/`VOZ_RUIDO`/etc.
(compatibilidad con el comportamiento anterior) o los defaults de `config.json`.

Si la voz no está corriendo, `/voz.html` ofrece arrancarla sola (sin el modelo grande de Qwen) para poder
ajustar settings sin esperar a que cargue todo.

API completa (todo vía proxy en `web_server.py`, `voz_server.py` sigue en 127.0.0.1 nomás):

```
GET  /api/voz/estado      {voces, rangos, activo, perfiles}  (503 si voz no corre)
GET  /api/voz/catalogo    voces es_* instalables, sin las que ya están
POST /api/voz/probar      {perfil, texto} -> 200 audio/wav   (no persiste nada)
POST /api/voz/descargar   {voz}           -> 200 {ok:true}
POST /api/voz/guardar     {activo, perfiles} -> 200 {ok:true, activo, perfiles}
POST /api/voz/iniciar     arranca voz_server.py sola (QWEN_VOZ=1, sin el modelo grande)
```

## Uso manual

```bash
qwen-voz                                      # arranca standalone, Enter para apagar
curl -sf http://127.0.0.1:8778/health         # "ok"
python3 voz_cliente.py "hola, prueba de voz"
```

O con el menú (`qwen`): toggle **Voz** (tecla `z`) — se levanta y se apaga junto con la sesión, igual que
Laya.

## Modelo de voz

Un archivo `<nombre>.onnx` + `<nombre>.onnx.json` (formato piper) directo en `QWEN_MODELS_DIR` (la misma
carpeta plana donde están los GGUF de Qwen). El primero que matchee `*.onnx` (orden alfabético) se usa;
para fijar uno exacto: `VOZ_MODEL=/ruta/al/archivo.onnx`.

## Endpoint — contrato para la fase 2

```
POST http://127.0.0.1:$VOZ_PORT/hablar
body: {"texto": "..."}
-> 200, header X-Sample-Rate, body: PCM s16le mono crudo
-> 500 {"error": "..."}
```

Es el único endpoint que necesitará llamar una futura extension de Pi. No cambia nada del servidor para
soportarla.

## Variables de entorno

Ver el bloque "Voz" en `../lib/config.sh`: `QWEN_VOZ`, `VOZ_PORT`, `VOZ_MODEL`, `VOZ_MODEL_GLOB`,
`VOZ_VELOCIDAD`, `VOZ_RUIDO`, `VOZ_RUIDO_W`, `VOZ_PAUSA`, `VOZ_TIMEOUT`.
