# lib/qwencode.sh — qwen-code como segundo harness (además de Pi) y modo «servidor» (sin agente).
# Requiere lib/config.sh, lib/laya.sh, lib/llama.sh y lib/pi.sh.
# Elección: fila «Agente» del menú (P_HARNESS); QWEN_HARNESS=pi|qwen-code|servidor la pisa.

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

# ── Agente elegido: QWEN_HARNESS (si existe) o la fila «Agente» del menú (P_HARNESS) ──
_qwen_pick_harness() {
    case "${QWEN_HARNESS:-${P_HARNESS:-pi}}" in
        qwen-code|qwencode|qcode) _QWEN_HARNESS=qwen-code ;;
        servidor|server)          _QWEN_HARNESS=server ;;
        *) _QWEN_HARNESS=pi ;;
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

# ── Modo servidor: llama-server (+laya/kev/voz) con la config del menú, SIN agente ──
# Elegir «servidor» en la fila «Agente». Deja la API OpenAI-compatible en
# http://127.0.0.1:$QWEN_PORT/v1 para usarla desde otros proyectos, muestra el estado
# en vivo y se queda hasta Enter + confirmación (o Ctrl+C), que baja todo.

# Estado en una línea: ● activo / ○ apagado por servicio (+ RAM de llama-server)
_qwen_server_estado() {
    local l="○" y="○" k="○" v="○" ram="" pid
    _qwen_port_open "$QWEN_PORT" && l="●"
    _laya_port_open && y="●"
    _kev_port_open && k="●"
    _voz_port_open && v="●"
    pid="$(pgrep -f "llama-server.*--port $QWEN_PORT" | head -n 1 || true)"
    [ -n "$pid" ] && ram="$(awk '/VmRSS/ {printf "%.1f GiB", $2/1048576}' "/proc/$pid/status" 2>/dev/null)"
    printf 'llama %s :%s · laya %s :%s · kev %s :%s · voz %s :%s%s' \
        "$l" "$QWEN_PORT" "$y" "$LAYA_PORT" "$k" "$KEV_PORT" "$v" "$VOZ_PORT" "${ram:+ · RAM $ram}"
}

_qwen_server_panel() {
    echo
    echo "  ● Servidor de IA listo (sin agente)"
    printf '  %-10s %s\n' "API"      "http://127.0.0.1:$QWEN_PORT/v1"
    printf '  %-10s %s\n' "Modelo"   "$QWEN_ALIAS  ($(basename "${QWENX_MODEL:-?}"))"
    printf '  %-10s %s\n' "Contexto" "${QWENX_CTX} · KV ${QWENX_KV} · temp ${QWENX_TEMP:-0.6}"
    [ -n "${QWENX_MMPROJ:-}" ] && printf '  %-10s %s\n' "Visión" "$(basename "$QWENX_MMPROJ")"
    _laya_port_open && printf '  %-10s %s\n' "Laya" "http://127.0.0.1:$LAYA_PORT"
    echo
    echo "  Ejemplo:"
    echo "    curl http://127.0.0.1:$QWEN_PORT/v1/chat/completions -H 'Content-Type: application/json' \\"
    echo "      -d '{\"model\":\"$QWEN_ALIAS\",\"messages\":[{\"role\":\"user\",\"content\":\"hola\"}]}'"
    echo
}

_qwen_run_local_server() { # _qwen_run_local_server profile
    local rc=0 stop=0 ans cur cols reused=0
    unset QWENX_INT
    trap 'QWENX_INT=1; _qwenx_down' INT
    if _qwenx_up; then rc=0; else rc=$?; fi
    trap - INT
    unset QWENX_INT
    [ "$rc" -eq 0 ] || { _qwenx_down; return "$rc"; }

    [ -z "${QWENX_SPID:-}" ] && reused=1   # _qwenx_up reusó un llama-server ya cargado
    _qwen_server_panel
    [ "$reused" = 1 ] && echo "  (llama-server ya estaba corriendo con esta misma configuración: se reusó)"
    echo "  Enter = bajar el server · Ctrl+C = bajarlo sin preguntar"
    echo

    trap 'stop=1' INT
    while [ "$stop" = 0 ]; do
        if ! _qwen_port_open "$QWEN_PORT"; then
            printf '\r\033[K  ✘ llama-server dejó de responder.\n'
            break
        fi
        cols="$(tput cols 2>/dev/null || echo 80)"
        cur="$(_qwen_server_estado)"
        printf '\r\033[K  %s' "${cur:0:cols-3}"
        read -r -t 2 _; rc=$?
        if [ "$rc" -eq 0 ]; then
            printf '\r\033[K'
            read -r -p "  ¿Seguro que quieres bajar el server de la IA? [s/N] " ans || ans=s
            case "${ans,,}" in
                s|si|sí|y|yes) stop=1 ;;
                *) echo "  Sigue corriendo." ;;
            esac
        elif [ "$rc" -le 128 ]; then
            stop=1   # stdin cerrado (EOF): apagar
        fi
    done
    trap - INT

    printf '\r\033[K  Bajando el server de la IA...\n'
    if [ -n "${QWENX_SPID:-}" ]; then _qwenx_down; else qwen-stop; fi
    echo "  Server apagado."
    return 0
}

# ── Despacha según _QWEN_HARNESS (lo fija _qwen_pick_harness) ──
_qwen_run_harness() { # _qwen_run_harness profile [args...]
    _qwen_pick_harness
    case "${_QWEN_HARNESS:-pi}" in
        qwen-code) _qwen_run_local_code "$@" ;;
        server)    _qwen_run_local_server "$@" ;;
        *)         _qwen_run_local "$@" ;;
    esac
}
