# lib/llama.sh — llama-server (backend principal) y Ollama (respaldo).
# Requiere lib/config.sh y lib/laya.sh.
# Sin logs persistentes. Contrato conservado para bench-qwen.sh:
#   _qwenx_up / _qwenx_down (llama.cpp) y _qwen_up / _qwen_down (Ollama).
# Entrada de _qwenx_up por entorno: QWENX_MODEL (ruta GGUF), QWENX_MMPROJ (opcional),
#   QWENX_NOTHINK=1 (desactiva thinking), QWENX_TEMP (temperatura, 0.6 por defecto). Salida: QWEN_URL, QWEN_TOKEN, QWEN_MODEL.

_qwen_port_open() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

# Espera /health de llama-server con spinner (si hay TTY).
_qwen_wait_ready() {
  local pid="$1" port="$2" t0=$SECONDS i=0 tty=0 timeout="$QWENX_READY_TIMEOUT"
  local spin='|/-\'
  [ -t 1 ] && tty=1
  until curl -sf --max-time 2 "http://127.0.0.1:$port/health" >/dev/null 2>&1; do
    if ! kill -0 "$pid" 2>/dev/null; then
      [ "$tty" = 1 ] && printf '\n'
      if [ -n "${QWENX_INT:-}" ]; then echo "cancelado"; return 130; fi
      echo "llama-server terminó antes de estar listo (logs persistentes desactivados)." >&2
      return 1
    fi
    if (( SECONDS - t0 >= timeout )); then
      [ "$tty" = 1 ] && printf '\n'
      echo "Timeout: llama-server no respondió /health en ${timeout}s (QWENX_READY_TIMEOUT)." >&2
      return 124
    fi
    if [ "$tty" = 1 ]; then
      printf '\r\033[K  %s esperando a Qwen... (%ds)' "${spin:i%4:1}" "$((SECONDS - t0))"
    fi
    i=$((i + 1)); sleep 0.2
  done
  if [ "$tty" = 1 ]; then
    printf '\r\033[K  * Qwen listo en %ds\n' "$((SECONDS - t0))"
  else
    echo "Qwen listo en $((SECONDS - t0))s"
  fi
}

# Fingerprint de los flags relevantes del lanzamiento actual de llama-server
# (modelo, mmproj, contexto, batch, etc. — los mismos que arma _qwenx_up).
# Permite detectar si un backend ya activo en el puerto sirve tal cual (p.ej.
# precalentado por `qwen-web`) o hay que reiniciarlo.
_qwen_fingerprint() {
  printf '%s|%s|%s|%s|%s|%s|%s|%s|%s\n' \
    "$1" "$2" "$QWENX_NCMOE" "$QWENX_CTX" "$QWENX_BATCH" "$QWENX_UB" "$QWENX_LOADMODE" "${QWENX_NOTHINK:-0}" \
    "${QWENX_TEMP:-0.6}"
}

# Libera el puerto si lo ocupa un llama-server que no sirve para esta invocación.
# Si $2 (fingerprint) coincide con el guardado en disco y el /health responde,
# NO mata nada: reusa el backend ya cargado. Deja _QWEN_FREE_PORT_REUSED en 1
# en ese caso, 0 en cualquier otro camino de éxito (puerto libre o liberado).
_qwen_free_port() {
  local port="$1" fp="${2:-}" fp_file="$QWEN_DATA/llama-fingerprint" pid n=0
  _QWEN_FREE_PORT_REUSED=0
  _qwen_port_open "$port" || return 0
  if [ -n "$fp" ] && [ "$(cat "$fp_file" 2>/dev/null)" = "$fp" ] \
     && curl -sf --max-time 1 "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
    echo "llama-server en :$port ya tiene el mismo modelo/flags cargados; se reusa (sin reiniciar)." >&2
    _QWEN_FREE_PORT_REUSED=1
    return 0
  fi
  pid="$(pgrep -f "llama-server.*--port $port" | head -n 1 || true)"
  if [ -z "$pid" ]; then
    echo "El puerto $port está ocupado por otro proceso que no es llama-server." >&2
    return 1
  fi
  echo "llama-server en :$port sigue activo; reiniciando con el modelo elegido..." >&2
  kill "$pid" 2>/dev/null || true
  while _qwen_port_open "$port" && (( n++ < 50 )); do sleep 0.2; done
  _qwen_port_open "$port" && { echo "No se pudo liberar el puerto $port." >&2; return 1; }
  rm -f "$fp_file"
  return 0
}

_qwenx_up() {
  local model="${QWENX_MODEL:-}" rc=0 fp
  local -a extra=()

  [ -x "$QWEN_LLAMA_BIN" ] || { echo "No encuentro $QWEN_LLAMA_BIN" >&2; return 1; }
  [ -z "$model" ] && model="$(_qwen_model_path base || true)"
  [ -f "$model" ] || { echo "No encuentro el modelo GGUF: ${model:-<ninguno en $QWEN_MODELS_DIR>}" >&2; return 1; }
  [[ "$QWENX_CTX" =~ ^[1-9][0-9]*$ ]] || { echo "QWENX_CTX debe ser un entero positivo" >&2; return 2; }
  # Cada mmproj sirve solo para su familia: 35B con el del 35B, Qwen3.8-4B con el suyo; los demás
  # (9B) no tienen. Un mmproj que no calza hace fallar a llama-server al cargar.
  if [ -n "${QWENX_MMPROJ:-}" ]; then
    case "$(basename "$model")|$(basename "$QWENX_MMPROJ")" in
      *35B*\|*35B*|*Qwen3.8-4B*\|*Qwen3.8-4B*) ;;
      *) echo "aviso: ese mmproj no es de este modelo (o el modelo no tiene visión); se lanza sin visión" >&2
         QWENX_MMPROJ="" ;;
    esac
  fi

  # Capas en GPU: los MoE van con 99 + --n-cpu-moe (los expertos a RAM). Un denso va sin --n-cpu-moe
  # y con auto: --fit reparte GPU/RAM, pero aborta si hay overrides de tensores (los pone --n-cpu-moe)
  # y entonces un 27B sale con todo a la GPU y muere al cargar. Solo los MoE traen expert_count en la
  # cabecera del GGUF. QWENX_NGL fuerza el número de capas.
  local -a capas=(-ngl "${QWENX_NGL:-99}" --n-cpu-moe "$QWENX_NCMOE")
  grep -aq expert_count <(head -c 2000000 "$model") || capas=(-ngl "${QWENX_NGL:-auto}")

  fp="$(_qwen_fingerprint "$model" "${QWENX_MMPROJ:-}")"
  _qwen_free_port "$QWEN_PORT" "$fp" || return 1
  if [ "$_QWEN_FREE_PORT_REUSED" = 1 ]; then
    QWEN_URL="http://127.0.0.1:$QWEN_PORT/v1"; QWEN_TOKEN="local"; QWEN_MODEL="$QWEN_ALIAS"
    _laya_up || true
    _voz_up  || true
    return 0
  fi
  pgrep -x ollama >/dev/null && echo "aviso: Ollama está activo y puede ocupar VRAM" || true

  [ "${QWENX_NOTHINK:-0}" = 1 ] && extra+=(--chat-template-kwargs '{"enable_thinking": false}')
  extra+=(-cram "$QWENX_CRAM")
  [ -n "${QWENX_MMPROJ:-}" ] && extra+=(--mmproj "$QWENX_MMPROJ" --no-mmproj-offload)

  "$QWEN_LLAMA_BIN" -m "$model" \
    --alias "$QWEN_ALIAS" --host 127.0.0.1 --port "$QWEN_PORT" \
    "${capas[@]}" -c "$QWENX_CTX" -b "$QWENX_BATCH" -ub "$QWENX_UB" \
    -fa on -ctk q8_0 -ctv q8_0 --load-mode "$QWENX_LOADMODE" --jinja \
    --temp "${QWENX_TEMP:-0.6}" --top-p 0.95 --top-k 20 --min-p 0.0 \
    "${extra[@]}" >/dev/null 2>&1 &
  QWENX_SPID=$!
  disown "$QWENX_SPID" 2>/dev/null || true

  QWEN_URL="http://127.0.0.1:$QWEN_PORT/v1"; QWEN_TOKEN="local"; QWEN_MODEL="$QWEN_ALIAS"
  if _qwen_wait_ready "$QWENX_SPID" "$QWEN_PORT"; then
    mkdir -p "$QWEN_DATA" 2>/dev/null || true
    echo "$fp" > "$QWEN_DATA/llama-fingerprint" 2>/dev/null || true
    _laya_up || true          # laya arranca junto a qwen/qwenh, ya con Qwen listo
    _voz_up  || true          # voz (TTS), igual: opcional, fail-open
  else
    rc=$?
    _qwenx_down
  fi
  return "$rc"
}

_qwenx_down() {
  rm -f "$QWEN_DATA/llama-fingerprint" 2>/dev/null || true
  _voz_down
  _laya_down
  if [ -n "${QWENX_SPID:-}" ]; then
    kill "$QWENX_SPID" 2>/dev/null || true
    wait "$QWENX_SPID" 2>/dev/null || true
  fi
  unset QWENX_SPID
  return 0
}

# ── Ollama (respaldo; ignora el modelo GGUF) ──
_qwen_up() {
  QWEN_URL="$QWEN_OLLAMA_URL/v1"
  QWEN_TOKEN="ollama"
  QWEN_MODEL="$QWEN_OLLAMA_MODEL"
  curl -fsS --max-time 2 "$QWEN_OLLAMA_URL/api/tags" >/dev/null 2>&1 || {
    echo "Ollama no responde en $QWEN_OLLAMA_URL" >&2; return 1;
  }
}

_qwen_down() {
  if [ "${QWEN_OLLAMA_STOP:-1}" = 1 ] && command -v ollama >/dev/null 2>&1; then
    ollama stop "${QWEN_MODEL:-$QWEN_OLLAMA_MODEL}" >/dev/null 2>&1 || true
  fi
  return 0
}

# ── Memoria de llama-server ──
qwen-mem() {
  local pid
  pid="$(pgrep -x llama-server | head -n 1 || true)"
  if [ -n "$pid" ]; then
    grep -E 'VmRSS|VmSwap' "/proc/$pid/status" | awk '{printf "  %s %.2f GiB\n", $1, $2/1048576}'
  else
    echo "  llama-server no está corriendo"
  fi
  free -m | awk 'NR==1 || /Mem|Swap/'
}

# ── Apagar a mano (por si queda un servidor colgado) ──
qwen-stop() {
  local n=0
  pkill -TERM -f 'voz_server.py' 2>/dev/null || true
  pkill -TERM -f 'laya_server.py' 2>/dev/null || true
  pkill -TERM -f "kev.serve.*--port $KEV_PORT" 2>/dev/null || true
  if pkill -TERM -f "llama-server.*--port $QWEN_PORT" 2>/dev/null; then
    while _qwen_port_open "$QWEN_PORT" && (( n++ < 30 )); do sleep 0.2; done
    _qwen_port_open "$QWEN_PORT" && pkill -KILL -f "llama-server.*--port $QWEN_PORT" 2>/dev/null || true
    rm -f "$QWEN_DATA/llama-fingerprint" 2>/dev/null || true
    echo "llama-server apagado · modelo descargado"
  else
    echo "llama-server no estaba corriendo"
  fi
  unset QWENX_SPID LAYA_SPID KEV_SPID VOZ_SPID
  return 0
}
