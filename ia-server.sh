#!/usr/bin/env bash
# ia-server.sh — levanta llama-server (API compatible con OpenAI) y lo deja corriendo
# hasta que presiones Enter y confirmes. Al confirmar (o con Ctrl+C) baja el server.
#
# Uso:   ./ia-server.sh
# Config por variables de entorno, ej:
#   MODEL=~/models/algo.gguf LLM_PORT=8001 CTX=32768 ./ia-server.sh
#   LLM_HOST=0.0.0.0 ./ia-server.sh        # exponerlo a la red local
#   EXTRA_ARGS="-ngl 99 --jinja" ./ia-server.sh

set -u

LLAMA_BIN="${LLAMA_BIN:-llama-server}"
MODEL_DIR="${MODEL_DIR:-$HOME/models}"
MODEL="${MODEL:-}"
LLM_HOST="${LLM_HOST:-127.0.0.1}"
LLM_PORT="${LLM_PORT:-8001}"
CTX="${CTX:-16384}"
PARALLEL="${PARALLEL:-2}"
# Pega acá tus flags de siempre (los de qwen-setup.sh) si son distintos.
# --n-cpu-moe 99 manda los expertos MoE a CPU (sirve para 12 GB de VRAM);
# bájalo si te sobra VRAM.
EXTRA_ARGS="${EXTRA_ARGS:--ngl 99 --n-cpu-moe 99 --jinja}"
LOG="${LOG:-/tmp/ia-server.log}"
READY_TIMEOUT="${READY_TIMEOUT:-300}"

C_G=$'\e[32m'; C_Y=$'\e[33m'; C_R=$'\e[31m'; C_D=$'\e[2m'; C_0=$'\e[0m'
say()  { printf '%s\n' "$*"; }
ok()   { printf '%s✔%s %s\n' "$C_G" "$C_0" "$*"; }
warn() { printf '%s!%s %s\n' "$C_Y" "$C_0" "$*"; }
err()  { printf '%s✘%s %s\n' "$C_R" "$C_0" "$*" >&2; }

command -v "$LLAMA_BIN" >/dev/null 2>&1 || { err "no encuentro '$LLAMA_BIN' (usa LLAMA_BIN=/ruta/llama-server)"; exit 1; }
command -v curl >/dev/null 2>&1 || { err "falta curl"; exit 1; }

# ── Puerto libre ──
if curl -s -o /dev/null --max-time 1 "http://127.0.0.1:${LLM_PORT}/health"; then
    err "ya hay algo respondiendo en el puerto ${LLM_PORT}. Ciérralo o usa LLM_PORT=otro."
    exit 1
fi

# ── Elegir modelo ──
if [ -z "$MODEL" ]; then
    mapfile -t MODELS < <(find "$MODEL_DIR" -maxdepth 2 -type f -name '*.gguf' ! -iname '*mmproj*' 2>/dev/null | sort)
    if [ "${#MODELS[@]}" -eq 0 ]; then
        err "no hay .gguf en $MODEL_DIR (usa MODEL=/ruta/modelo.gguf)"; exit 1
    elif [ "${#MODELS[@]}" -eq 1 ]; then
        MODEL="${MODELS[0]}"
    else
        say "Modelos en $MODEL_DIR:"
        for i in "${!MODELS[@]}"; do
            sz=$(du -h "${MODELS[$i]}" | cut -f1)
            printf '  %s%d)%s %s %s(%s)%s\n' "$C_Y" "$((i+1))" "$C_0" "$(basename "${MODELS[$i]}")" "$C_D" "$sz" "$C_0"
        done
        while true; do
            read -r -p "Elige [1-${#MODELS[@]}]: " n || exit 1
            if [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -ge 1 ] && [ "$n" -le "${#MODELS[@]}" ]; then
                MODEL="${MODELS[$((n-1))]}"; break
            fi
        done
    fi
fi
[ -f "$MODEL" ] || { err "no existe el modelo: $MODEL"; exit 1; }

# ── Levantar server (en su propio grupo de procesos, para poder bajarlo entero) ──
PID=""
STOPPED=0

stop_server() {
    [ "$STOPPED" -eq 1 ] && return
    STOPPED=1
    [ -z "$PID" ] && return
    if kill -0 "$PID" 2>/dev/null; then
        say "Bajando el server de la IA..."
        kill -TERM -- "-$PID" 2>/dev/null || kill -TERM "$PID" 2>/dev/null
        for _ in $(seq 1 30); do
            kill -0 "$PID" 2>/dev/null || break
            sleep 0.5
        done
        if kill -0 "$PID" 2>/dev/null; then
            warn "no cerró a tiempo, forzando..."
            kill -KILL -- "-$PID" 2>/dev/null || kill -KILL "$PID" 2>/dev/null
        fi
        wait "$PID" 2>/dev/null
    fi
    ok "Server apagado."
}
trap 'echo; stop_server; exit 0' INT TERM HUP
trap 'stop_server' EXIT

say "Modelo : $(basename "$MODEL")"
say "Escucha: ${LLM_HOST}:${LLM_PORT}  (ctx ${CTX}, ${PARALLEL} slots)"
say "Log    : $LOG"

# shellcheck disable=SC2086
setsid "$LLAMA_BIN" -m "$MODEL" --host "$LLM_HOST" --port "$LLM_PORT" \
    -c "$CTX" --parallel "$PARALLEL" $EXTRA_ARGS >"$LOG" 2>&1 &
PID=$!

# ── Esperar a que cargue ──
printf 'Cargando modelo'
t=0
while ! curl -s -f -o /dev/null --max-time 2 "http://127.0.0.1:${LLM_PORT}/health"; do
    if ! kill -0 "$PID" 2>/dev/null; then
        echo; err "llama-server murió al arrancar. Últimas líneas del log:"
        tail -n 15 "$LOG" >&2
        exit 1
    fi
    if [ "$t" -ge "$READY_TIMEOUT" ]; then
        echo; err "no quedó listo en ${READY_TIMEOUT}s (revisa $LOG)"; exit 1
    fi
    printf '.'; sleep 2; t=$((t+2))
done
echo
ok "IA lista en  http://${LLM_HOST}:${LLM_PORT}/v1/chat/completions"
say "${C_D}Health: http://${LLM_HOST}:${LLM_PORT}/health   |   Modelo (API): cualquier nombre sirve${C_0}"
echo
say "Presiona ${C_Y}Enter${C_0} para cerrar el server."

# ── Mantener vivo hasta Enter + confirmación ──
while true; do
    if ! kill -0 "$PID" 2>/dev/null; then
        err "el server se cayó solo. Últimas líneas del log:"
        tail -n 15 "$LOG" >&2
        exit 1
    fi
    read -r -t 2 _
    rc=$?
    [ "$rc" -gt 128 ] && continue          # timeout: seguir vigilando
    [ "$rc" -ne 0 ] && break               # EOF (stdin cerrado): apagar
    read -r -p "¿Seguro que quieres bajar el server de la IA? [s/N] " ans || break
    case "${ans,,}" in
        s|si|sí|y|yes) break ;;
        *) say "Sigue corriendo. Enter para cerrar cuando quieras." ;;
    esac
done

stop_server
