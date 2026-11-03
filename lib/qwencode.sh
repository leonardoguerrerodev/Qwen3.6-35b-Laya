# lib/qwencode.sh — qwen-code como segundo harness (además de Pi).
# Requiere lib/config.sh, lib/laya.sh, lib/llama.sh y lib/pi.sh.
# Elección: QWEN_HARNESS=pi|qwen-code salta la pregunta; sin variable pregunta en el menú.

# ── Binario real de qwen-code (la función/alias `qwen` es el menú, no el binario) ──
_qwen_code_bin() {
    local b
    if [ -n "${QWEN_CODE_BIN:-}" ]; then
        printf '%s\n' "$QWEN_CODE_BIN"
        return 0
    fi
    for b in qwen-code qwen; do
        type -P "$b" 2>/dev/null && return 0
    done
    return 1
}

# ── Pregunta con qué harness arrancar; deja el resultado en _QWEN_HARNESS ──
_qwen_pick_harness() {
    case "${QWEN_HARNESS:-}" in
        pi|qwen-code) _QWEN_HARNESS="$QWEN_HARNESS"; return 0 ;;
    esac
    _QWEN_HARNESS=pi
    [ -t 0 ] && [ -t 1 ] || return 0
    local ans=""
    printf '\n¿Con qué harness arrancar?  [p] pi (por defecto)  ·  [q] qwen-code : '
    read -r -n 1 ans
    printf '\n'
    case "$ans" in
        q|Q|c|C) _QWEN_HARNESS=qwen-code ;;
    esac
}

# ── Ejecuta qwen-code contra el llama-server local ──
_qwen_code() { # _qwen_code profile [args de qwen-code...]
    local profile="$1"; shift
    local bin mode=plan a has_mode=0
    local -a extra=()
    bin="$(_qwen_code_bin)" || {
        echo "No encuentro qwen-code en PATH. Define QWEN_CODE_BIN=/ruta/al/binario (mira 'type qcode')." >&2
        return 127
    }
    [ "$profile" = edit ] && mode=default
    for a in "$@"; do
        case "$a" in
            --approval-mode|--approval-mode=*|--yolo|-y) has_mode=1 ;;
        esac
    done
    [ "$has_mode" = 0 ] && extra+=(--approval-mode "$mode")
    [ "${QWEN_PI_NO_SESSION:-0}" = 1 ] \
        && echo "aviso: el modo incógnito no aplica a qwen-code (guarda su historial en ~/.qwen)" >&2
    OPENAI_API_KEY=local \
    OPENAI_BASE_URL="http://127.0.0.1:${QWEN_PORT}/v1" \
    OPENAI_MODEL="$QWEN_ALIAS" \
        "$bin" --auth-type openai ${extra[@]+"${extra[@]}"} "$@"
}

# ── Sesión local completa: llama-server (+laya) → qwen-code → apagado ──
_qwen_run_local_code() { # _qwen_run_local_code profile [args de qwen-code...]
    local profile="$1"; shift
    local rc=0
    unset QWENX_INT
    trap 'QWENX_INT=1; _qwenx_down' INT
    if _qwenx_up; then rc=0; else rc=$?; fi
    trap - INT
    unset QWENX_INT
    [ "$rc" -eq 0 ] || { _qwenx_down; return "$rc"; }
    if _qwen_code "$profile" "$@"; then rc=0; else rc=$?; fi
    _qwenx_down
    return "$rc"
}

# ── Despacha según _QWEN_HARNESS (lo fija _qwen_pick_harness) ──
_qwen_run_harness() { # _qwen_run_harness profile [args...]
    _qwen_pick_harness
    if [ "${_QWEN_HARNESS:-pi}" = qwen-code ]; then
        _qwen_run_local_code "$@"
    else
        _qwen_run_local "$@"
    fi
}
