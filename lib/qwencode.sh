# lib/qwencode.sh — qwen-code como segundo harness (además de Pi) y modo «servidor» (sin agente).
# Requiere lib/config.sh, lib/laya.sh, lib/llama.sh y lib/pi.sh.
# Elección: fila «Agente» del menú (P_HARNESS); QWEN_HARNESS=pi|qwen-code|qwen-code-web|servidor la pisa.

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
        qwen-code-web|web)        _QWEN_HARNESS=qwen-code-web ;;
        servidor|server)          _QWEN_HARNESS=server ;;
        *) _QWEN_HARNESS=pi ;;
    esac
}

# ── Contexto real y nombre del modelo cargado → settings.json de qwen-code (como _qwen_pi_prepare con Pi) ──
# Sin esto qwen-code cree tener la ventana fija del settings (p. ej. 49152 con el servidor a 30000)
# y choca con llama-server en vez de compactar a tiempo.
# El nombre sale de model.name y del id del proveedor: sin esto qwen-code mostraba siempre qwen3.6-35b.
_qwen_code_prepare() { # _qwen_code_prepare dir_qwen ctx alias
    python3 - "$1/settings.json" "$2" "$3" <<'PY'
import json, os, sys, tempfile
p, ctx, alias = sys.argv[1], int(sys.argv[2]), sys.argv[3]
if not os.path.exists(p): raise SystemExit(0)
with open(p, encoding="utf-8") as f: d = json.load(f)
provs = [x for x in d.get("modelProviders", {}).get("openai", []) if "127.0.0.1" in x.get("baseUrl", "")]
if all(x.get("generationConfig", {}).get("contextWindowSize") == ctx and x.get("id") == alias for x in provs) \
        and d.get("model", {}).get("name") == alias: raise SystemExit(0)
for x in provs:
    x.setdefault("generationConfig", {})["contextWindowSize"] = ctx
    x["id"] = alias
d.setdefault("model", {})["name"] = alias
fd, tmp = tempfile.mkstemp(prefix=".qwen-runtime-", dir=os.path.dirname(p), text=True)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2); f.write("\n")
    os.replace(tmp, p)
finally:
    if os.path.exists(tmp): os.unlink(tmp)
PY
}

# ── Incógnito: qwen-code escribe todo (historial, uso, tmp) bajo QWEN_HOME → carpeta en RAM ──
# Medido 6-nov-2026 (0.26.8): con --chat-recording false ya no guarda la conversación, pero
# ~/.qwen/usage_record.jsonl anota carpeta, hora, tokens y herramientas. Con QWEN_HOME
# temporal (+ settings y QWEN.md copiados) no queda nada en ~/.qwen. Se borra al salir.
# ponytail: si qwen-code muere con SIGKILL la carpeta queda en /run/user (tmpfs: se va al cerrar sesión).
_qwen_code_incognito_home() {
    local h
    h="$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/qwen-incognito.XXXXXX")" || return 1
    chmod 700 "$h"
    cp -p "$HOME/.qwen/settings.json" "$HOME/.qwen/QWEN.md" "$h/" 2>/dev/null
    printf '%s\n' "$h"
}

# ── Ejecuta qwen-code contra el llama-server local ──
_qwen_code() { # _qwen_code profile [args de qwen-code...]
    local profile="$1"; shift
    local bin mode=plan a has_mode=0 home="" rc=0
    local -a extra=() envs
    bin="$(_qwen_code_bin)" || {
        echo "No encuentro qwen-code en PATH. Define QWEN_CODE_BIN=/ruta/al/binario (mira 'type qcode')." >&2
        return 127
    }
    [ "$profile" = edit ] && mode=auto-edit   # edita sin preguntar; shell sigue pidiendo permiso
    for a in "$@"; do
        case "$a" in
            --approval-mode|--approval-mode=*|--yolo|-y) has_mode=1 ;;
        esac
    done
    [ "$has_mode" = 0 ] && extra+=(--approval-mode "$mode")
    envs=(OPENAI_API_KEY=local "OPENAI_BASE_URL=http://127.0.0.1:${QWEN_PORT}/v1" "OPENAI_MODEL=$QWEN_ALIAS")
    if [ "${QWEN_PI_NO_SESSION:-0}" = 1 ]; then
        home="$(_qwen_code_incognito_home)" || { echo "No pude crear la carpeta temporal del incógnito" >&2; return 1; }
        envs+=("QWEN_HOME=$home")
        extra+=(--chat-recording false)
    fi
    _qwen_code_prepare "${home:-$HOME/.qwen}" "$QWENX_CTX" "$QWEN_ALIAS" || echo "aviso: no pude ajustar el contexto de qwen-code" >&2
    env "${envs[@]}" "$bin" --auth-type openai ${extra[@]+"${extra[@]}"} "$@" || rc=$?
    [ -n "$home" ] && rm -rf "$home"
    return "$rc"
}

# ── qwen-code con interfaz web (qwen serve): http://127.0.0.1:4170, solo local ──
# Sin incógnito: la web guarda sus conversaciones (~/Documents/Qwen Code/Conversations);
# el menú deja Incógnito en gris con este agente.
_qwen_run_local_code_web() { # _qwen_run_local_code_web profile
    local bin rc=0
    bin="$(_qwen_code_bin)" || { echo "No encuentro qwen-code en PATH. Define QWEN_CODE_BIN=/ruta/al/binario." >&2; return 127; }
    if [ "${QWEN_PI_NO_SESSION:-0}" = 1 ]; then
        echo "El modo incógnito no está disponible con qwen-code-web (la web guarda sus conversaciones)." >&2
        return 1
    fi
    unset QWENX_INT
    trap 'QWENX_INT=1; _qwenx_down' INT
    if _qwenx_up; then rc=0; else rc=$?; fi
    trap - INT
    unset QWENX_INT
    [ "$rc" -eq 0 ] || { _qwenx_down; return "$rc"; }
    _qwen_code_prepare "$HOME/.qwen" "$QWENX_CTX" "$QWEN_ALIAS" || echo "aviso: no pude ajustar el contexto de qwen-code" >&2
    echo
    echo "  ● qwen-code web en http://127.0.0.1:4170  (carpeta: $PWD)"
    echo "  Ctrl+C = cerrar la web y bajar el server de la IA"
    echo
    trap ':' INT   # Ctrl+C corta a qwen serve, no a esta función: así siempre se baja llama-server
    OPENAI_API_KEY=local OPENAI_BASE_URL="http://127.0.0.1:${QWEN_PORT}/v1" OPENAI_MODEL="$QWEN_ALIAS" \
        "$bin" serve --open --workspace "$PWD" || true
    trap - INT
    _qwenx_down
    return 0
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
    printf '  %-10s %s\n' "Modelo"   "$QWEN_ALIAS"
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
        qwen-code-web) _qwen_run_local_code_web "$@" ;;
        server)    _qwen_run_local_server "$@" ;;
        *)         _qwen_run_local "$@" ;;
    esac
}
