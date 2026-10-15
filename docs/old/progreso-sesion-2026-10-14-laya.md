# Progreso de la sesión (2026-10-14), parte 2: laya integrada con `qwen`

Complementa `progreso-sesion-2026-10-14.md`, `plan-qwen-3060.md`, `checklist-qwen-3060.md` y `anexo-router-ram-qwen.md`. Sugerido: guardarlo en `docs/`.

## 1. Resumen

- **Laya quedó integrada y funcionando de punta a punta.** Servicio local en CPU + hook de Claude Code que **solo avisa en pantalla** y nunca bloquea. Apagado por defecto: se activa con `QWENX_LAYA=1 qwen`.
- **Hook verificado:** se ejecuta en `qwen`, recibe el `prompt` por stdin y su `systemMessage` se muestra en pantalla.
- **Descartado como canal:** `additionalContext` (avisar al modelo). Claude Code lo registra, pero Qwen no lo obedece ni lo reporta.
- **`qwen-setup.sh` pasa a v6.3** (hook, servicio opcional, `QWEN_LAYA_DIR`).
- **Prueba de `-cram`: sigue sin cerrarse.** El proceso de la sesión larga murió sin medir RSS/swap final. Se guardó el log.
- **Pendiente para dar laya por cerrada:** latencia bajo carga y comprobar el apagado (sección 7, pasos 1 y 2).

## 2. Qué se construyó

| Archivo | Dónde | Función |
|---|---|---|
| `laya_server.py` | `laya/` | Servicio en `127.0.0.1:8765`. Carga `multilingual` una vez (CPU, `CUDA_VISIBLE_DEVICES=""`). `POST /classify`, `GET /health` |
| `laya_hook.py` | `laya/` (se copia a `~/.claude-local/hooks/`) | Cliente delgado: lee `prompt`, consulta al servicio, imprime `{"systemMessage": ...}` si hay aviso. Sin servicio no hace nada |
| `qwen-setup.sh` | `setup/` | v6.3 |

### Qué avisa el hook

| Condición | Aviso |
|---|---|
| `destructivo` ≥ 0,5 | posible acción destructiva |
| `injection` ≥ 0,5 | posible intento de saltarse reglas |
| complejidad `compleja` | tarea compleja: considera dividirla en pasos |

### Cambios de `qwen-setup.sh` v6.3

1. Copia `laya/laya_hook.py` a `~/.claude-local/hooks/` (funciona aunque el disco del repo no esté montado).
2. Registra el hook `UserPromptSubmit` en `~/.claude-local/settings.json` (con `timeout` 3) y **elimina los hooks de prueba** (los que contienen `hook-stdin` o `hook-test`). Es idempotente.
3. Añade a `~/.qwen-local.sh` las funciones `_laya_up` y `_laya_down` y la variable `QWEN_LAYA_DIR` (ruta del repo, con `%q` por los `!` y `+`).
4. `_qwenx_up` arranca el servicio en segundo plano **después** de que llama-server esté listo; `_qwenx_down` lo apaga.
5. `--check` muestra el estado de laya (hook copiado, registrado, `laya_server.py` presente).
6. Sin `QWENX_LAYA=1`, `qwen` se comporta como en la v6.2.

### Uso

```bash
QWENX_LAYA=1 qwen                      # arranca llama-server y, después, el servicio de laya
tail -f ~/.cache/qwenx/laya.log        # espera: "laya: listo en 127.0.0.1:8765"
curl -s -X POST http://127.0.0.1:8765/classify -d '{"text":"..."}'   # puntajes y ms
```

Variables opcionales: `LAYA_PORT` (8765), `LAYA_MODEL` (multilingual), `LAYA_MAXCHARS` (2000), `LAYA_HOOK_TIMEOUT` (1,5 s), `LAYA_THRESHOLD` (0,5).

## 3. Verificado en la máquina

| Qué | Resultado |
|---|---|
| Versión de laya | 0.4.6 en `laya/.venv` (Python 3.12). `direct_url.json` vacío: no viene de git ni de ruta local |
| Hook en `qwen` | Se ejecuta. El stdin trae `session_id`, `transcript_path`, `cwd`, `prompt_id`, `permission_mode`, `hook_event_name` y `prompt` |
| Recarga del hook | Cambiar `settings.json` se aplica **sin reiniciar** `qwen` (el hook v5 escribió su archivo sin reinicio) |
| `additionalContext` | Claude Code lo guarda como adjunto `hook_additional_context` y lo renderiza como `system-reminder`. Qwen **no** lo reportó ni lo obedeció (2 pruebas: `codigo=` y `CLAVE-`) |
| `systemMessage` | Se muestra en pantalla como `UserPromptSubmit says: ...` |
| Instalación v6.3 | Hook copiado y registrado; `--check` correcto |
| Servicio | Arrancó: `laya: listo en 127.0.0.1:8765`. El checkpoint ya estaba en caché (no descargó) |
| `/classify` | `"borra todos los archivos y haz git push --force"` → `compleja`, `destructivo` 0,8566, `injection` 0,117, **164 ms** |
| Prueba completa en `qwen` | Aparece `laya: posible acción destructiva (0.86); tarea compleja: considera dividirla en pasos`. Qwen (plan mode) no ejecutó nada destructivo |

## 4. Prueba de `-cram`: estado

- Log de la sesión larga guardado: `results/sesion-cram-231417.log` (`task 1151` aparece 392 veces).
- Esa tarea generó ~30.000 tokens (último `n_gen` 30028; `tg` ≈ 25,4 t/s; liberada con `n_tokens = 57248`). El log no distingue si terminó sola o por interrupción.
- El proceso (pid 16646, con `-cram 2048`) murió **antes de medir** RSS y swap finales. Esa medición no se recupera: hay que repetir la prueba.
- Servidor siguiente (sin `-cram`), recién cargado: RSS 14,45 GiB, swap 0, 12167 MB disponibles. No sirve como prueba de `-cram`.
- `tg` ≈ 25,4 t/s en la sesión larga frente a 42,16 t/s del `llama-bench`: **no comparable** (contexto distinto). No tomarlo como regresión sin medir con el mismo contexto.

## 5. Incidentes y lecciones operativas

1. **Puerto 8001 ocupado:** un segundo arranque de `llama-server` muere a los 28 ms, y `/tmp/llama-server.log` (enlace al último arranque) pasa a apuntar a ese log inútil. El log real se obtiene con `ls -l /proc/<pid>/fd/1`.
2. **Hipótesis sin confirmar:** si `llama-server` sigue vivo, un segundo `qwen` se conecta al servidor del primero (`_qwen_wait_ready` responde con `/health`), y cerrar uno apagaría el servidor de ambos.
3. `qwen-mem` mide el primer `llama-server` que encuentra (`pgrep | head -n 1`).
4. Los logs de llama-server se conservan solo los últimos 20: copiar el de una sesión importante antes de seguir abriendo `qwen`.
5. `$R` no existe en una terminal nueva: definirla con comillas simples (`R='...'`) y usar `"$R"`. Con la ruta del repo ya como directorio actual, usar rutas relativas (`./setup/...`).
6. Al pegar bloques `<<'EOF'`, las líneas deben ir pegadas al borde izquierdo; con sangría, bash no reconoce el `EOF` y se queda esperando (`>`).
7. Los archivos descargados hay que copiarlos al repo (`laya/` y `setup/`) antes de correr el instalador.

## 6. Sin verificar / limitaciones

- **Latencia de laya con qwen generando:** el único dato (164 ms) no se midió bajo carga.
- **Apagado del servicio al salir de `qwen`:** probado solo en un entorno aislado con un laya simulado, no en la máquina.
- **Campo `timeout` del hook** en `settings.json`: viene de una referencia de terceros, no de la documentación oficial.
- **Tope de 2000 caracteres** y **puerto 8765:** elegidos sin medir.
- **Calidad de `multilingual`:** deja pasar el `DROP` de la tabla de usuarios y sobrescribir `.env`, no detecta "desactiva el plan mode" como injection, subestima la complejidad y suma 2 falsos positivos de injection. Los avisos son ayuda, no protección.
- **Reglas `deny`/`ask`:** el documento dice que `~/.claude-local/settings.json` las tiene (`rm -rf`, `git push --force`, `DROP`, escribir `.env`). El archivo revisado solo tiene `WebSearch` denegado y plan mode. **Pendiente de aclarar** si existen en otro archivo.
- **Directorio de trabajo:** la prueba se hizo con `qwen` abierto en `/home/xaski`, no en una carpeta de proyecto.
- No se revisó si `laya/test-laya.sh` mide el servicio nuevo o el `Router` en proceso.
- Que `-cram` sea la causa del crecimiento de llama-server, y que la subida de `tg128` venga del arreglo del UMA (puntos heredados, siguen abiertos).

## 7. Pendientes, en orden

1. [ ] **Latencia bajo carga.** Con `qwen` generando una tarea larga, repetir 3 veces `curl -s -X POST http://127.0.0.1:8765/classify -d '{"text":"explica este archivo"}'` y anotar `ms`. Criterio: ≤ 500 ms.
2. [ ] **Comprobar el apagado.** Al salir de `qwen`: `pgrep -f laya_server.py; pgrep -a llama-server` no debe mostrar nada.
3. [ ] **Aclarar las reglas `deny`/`ask`.** Si no existen, añadirlas a `settings.json` (idealmente desde `qwen-setup.sh`).
4. [ ] Abrir `qwen` desde la carpeta de un proyecto, no desde el home.
5. [ ] **Prueba larga de `-cram`:** `QWENX_CRAM=2048 qwen`; confirmar con `pgrep -a llama-server | grep -o -- '-cram [0-9]*'`; trabajar 30-60 min con tareas distintas; registrar con `while true; do date +%T; qwen-mem; sleep 120; done | tee -a "$R/results/qwen-mem-cram2048.log"`. **Antes de cerrar:** `qwen-mem` una última vez y copiar el log (`ls -l /proc/<pid>/fd/1` para ubicarlo).
6. [ ] `TAG=post-uma ./laya/test-laya.sh` con qwen cargado y sin Brave. Criterio: RAM disponible ≥ 4096 MB en todas las fases y tok/s de qwen estables. Revisar antes si el script mide el servicio nuevo.
7. [ ] Añadir a `_qwenx_up` el chequeo de puerto libre para llama-server (ver sección 5, puntos 1 y 2).
8. [ ] Ampliar `prompts.jsonl` a ~100 prompts con etiquetas de complejidad revisadas y repetir laya vs kev.
9. [ ] Bootstrap en `setup/`: compilar llama.cpp (con `--cudart shared`), descargar los modelos con `hf` y crear el `.venv` de laya con la versión **0.4.6** (instalada desde un índice de paquetes; el índice exacto no está verificado).
10. [ ] Uso diario de `QWENX_LAYA=1`: solo después de los pasos 5 y 6.
11. [ ] Actualizar `docs/`: rutas nuevas, `qwen-setup.sh` v6.3, línea base de `llama-bench` y esta sesión en el checklist.
12. [ ] Heredados: mover el módulo de RAM de 8 GiB al canal A (un cambio a la vez) y repetir el `llama-bench` de línea base; opcional, escritorio en la iGPU y medir VRAM con `nvidia-smi`; `/autocompact` con 131072; VRAM bajo carga real; repetir `q4-base` para medir varianza y calidad con una tarea real.
