# lib/laya.sh — ciclo de vida de laya (clasificador de prompts, CPU, no toca VRAM).
# Requiere lib/config.sh. Laya es opcional: si falta o falla, qwen sigue funcionando.
# Solo se mata el laya que arrancó esta sesión (LAYA_SPID); uno ajeno se respeta.

_laya_port_open() { (exec 3<>"/dev/tcp/127.0.0.1/$LAYA_PORT") 2>/dev/null; }

_laya_healthy() { curl -sf --max-time 1 "http://127.0.0.1:$LAYA_PORT/health" >/dev/null 2>&1; }

# Crea el venv con laya la primera vez (una sola vez, necesita red).
_laya_ensure_venv() {
  [ -x "$LAYA_VENV/bin/python" ] && return 0
  echo "laya: creando venv en $LAYA_VENV ..." >&2
  mkdir -p "$(dirname "$LAYA_VENV")" || return 1
  python3 -m venv "$LAYA_VENV" || return 1
  "$LAYA_VENV/bin/pip" install --quiet laya 2>&1 | tail -n 1 >&2
  [ -x "$LAYA_VENV/bin/python" ] || return 1
  echo "laya: venv listo." >&2
}

_laya_up() {
  [ "${QWEN_LAYA:-1}" = 1 ] || return 0
  if [ ! -f "$LAYA_SERVER" ]; then
    echo "laya: no encuentro $LAYA_SERVER (se continúa sin laya)" >&2
    return 0
  fi
  if _laya_port_open; then
    echo "laya: ya corriendo en 127.0.0.1:$LAYA_PORT"
    return 0
  fi
  _laya_ensure_venv || { echo "laya: no se pudo preparar el venv (se continúa sin laya)" >&2; return 1; }

  echo "laya: arrancando en 127.0.0.1:$LAYA_PORT ..."
  LAYA_PORT="$LAYA_PORT" LAYA_MODEL="$LAYA_MODEL" \
    "$LAYA_VENV/bin/python" "$LAYA_SERVER" >/dev/null 2>&1 &
  LAYA_SPID=$!
  disown "$LAYA_SPID" 2>/dev/null || true

  local t0=$SECONDS
  until _laya_healthy; do
    if ! kill -0 "$LAYA_SPID" 2>/dev/null; then
      echo "laya: terminó prematuramente (se continúa sin laya)" >&2
      unset LAYA_SPID; return 1
    fi
    if (( SECONDS - t0 >= LAYA_TIMEOUT )); then
      echo "laya: timeout (${LAYA_TIMEOUT}s) (se continúa sin laya)" >&2
      kill "$LAYA_SPID" 2>/dev/null || true
      unset LAYA_SPID; return 1
    fi
    sleep 0.5
  done
  echo "laya: listo en 127.0.0.1:$LAYA_PORT (modelo: ${LAYA_MODEL:-el de laya/config.json})"
}

_laya_down() {
  if [ -n "${LAYA_SPID:-}" ]; then
    kill "$LAYA_SPID" 2>/dev/null || true
    wait "$LAYA_SPID" 2>/dev/null || true
    unset LAYA_SPID
  fi
  return 0
}

# Modo independiente (tecla 'l' del menú): laya solo, hasta pulsar Enter.
_laya_standalone() {
  _laya_up || return $?
  if [ -z "${LAYA_SPID:-}" ] && _laya_port_open; then
    echo "laya: ya estaba corriendo fuera de esta sesión; no lo detengo."
    return 0
  fi
  read -r -p "Pulsa Enter para detener laya... " _
  _laya_down
  echo "laya: detenido."
}
