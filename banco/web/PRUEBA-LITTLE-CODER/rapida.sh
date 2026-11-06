#!/usr/bin/env bash
# rapida.sh [agentes...] — prueba corta: tu Pi normal vs little-coder arreglan y amplían el proyecto de rapida/inicial/
# (3 archivos, errores sin señalar + una función nueva) y un oráculo oculto (rapida/oraculo.js, 19 pruebas) los corrige.
# Todos con el mismo nivel de razonamiento: EFFORT (xhigh por defecto). Agentes: pi lc (por defecto: tu Pi y little-coder
# adaptado con lib/lc.sh); qcode opcional. (lcpuro, little-coder tal cual, se retiró el 6-nov al mudarlo a little-coder/:
# esa instalación lleva el tope de razonamiento del launcher. Su resultado quedó en rapida/resumen.txt.)
# Un solo llama-server (perfil activo de q38) para todos. Resultados en rapida/resultados/ y una tabla en rapida/resumen.txt.
set -u
D="$(cd "$(dirname "$0")" && pwd)"; R="$D/../../.."; Q="$D/rapida"; MID="${MID:-q38}"; TMAX="${TMAX:-600}"
AGENTES=("$@"); [ ${#AGENTES[@]} -gt 0 ] || AGENTES=(pi lc)
QWEN_CLI="$HOME/.npm-global/bin/qwen"   # el binario de qwen-code; `qwen` en la shell es el launcher
pgrep -x llama-server >/dev/null && { echo "Hay un llama-server corriendo: qwen-stop primero." >&2; exit 1; }

PEDIDO='Este proyecto de la cafetería (carrito.js, precios.js y formato.js; Node, CommonJS, sin librerías) tiene errores. Revísalo y haz que cumpla exactamente esto:
- subtotal(lineas), con lineas = [{ id, cantidad }]: el id puede venir como número o como texto ("3"). Un id que no está en el catálogo lanza new Error("producto desconocido: " + id). Una cantidad que no sea entero >= 1 lanza new Error("cantidad inválida").
- desglose(total): los precios YA incluyen IVA (19 %). Devuelve { neto, iva } en enteros, con neto = Math.round(total / 1.19) e iva = total - neto.
- formatoCLP(n), en formato.js: punto de miles y signo peso, sin decimales: 0 → "$0", 12990 → "$12.990", -1500 → "-$1.500".
- boleta(lineas) devuelve "Neto $X · IVA $Y · Total $Z" con esos valores formateados.
- Nueva, exportada desde carrito.js: dividirCuenta(total, n) reparte un total entero entre n personas: n montos enteros que suman total, que difieren a lo más en 1, los mayores primero (10000 entre 3 → [3334, 3333, 3333]). Si n no es un entero >= 1, lanza new Error("n inválido").
Conserva lo que ya funciona. Cuando termines, responde en una línea qué cambiaste.'

# ── servidor: el comando del perfil activo (igual que correr.sh), un solo arranque para todos ──
mapfile -d '' CMD < <(python3 - "$R" "$MID" <<'PY'
import os, sys; R, mid = sys.argv[1:]
sys.path.insert(0, os.path.join(R, "banco")); sys.argv = ["x"]
import prueba_corta as p
p.PUERTO = "8001"
c, _ = p.comando(mid, p.MODELOS[mid][1]); sys.stdout.write("\0".join(c) + "\0")
PY
)
[ "${#CMD[@]}" -gt 1 ] || { echo "no pude armar el comando del servidor" >&2; exit 1; }
# mismo nivel de razonamiento para todos: qwen-code y little-coder no lo mandan (usa el del servidor); Pi lo manda (--thinking)
EFFORT="${EFFORT:-xhigh}"; CMD+=(--reasoning-effort "$EFFORT")
arg() { local i; for ((i=0;i<${#CMD[@]};i++)); do [ "${CMD[i]}" = "$1" ] && { echo "${CMD[i+1]}"; return; }; done; }
ALIAS="$(arg --alias)"; ALIAS="${ALIAS:-qwen3.6-35b}"; CTX="$(arg -c)"
LOGS="$Q/logs"; RES="$Q/resultados"; rm -rf "$LOGS" "$RES"; mkdir -p "$LOGS" "$RES"
printf '%q ' "${CMD[@]}" > "$LOGS/servidor-cmd.txt"
"${CMD[@]}" > "$LOGS/servidor.log" 2>&1 & SPID=$!
TRABAJO="$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/rapida.XXXXXX")"   # fuera del repo: el agente no ve el oráculo
trap 'kill $SPID 2>/dev/null; wait $SPID 2>/dev/null; rm -rf "$TRABAJO"' EXIT
until curl -sf localhost:8001/health >/dev/null; do
  kill -0 $SPID 2>/dev/null || { echo "el servidor no cargó ($LOGS/servidor.log)" >&2; exit 1; }; sleep 1
done

# tokens generados y peticiones del servidor desde la línea $1 del log
tokens_desde() { tail -n +"$1" "$LOGS/servidor.log" | awk '/ eval time =/ && !/prompt eval/ {for(i=1;i<=NF;i++) if($i=="/"){g+=$(i+1)}; n++} END {printf "%d %d", g, n}'; }
herramientas() { python3 -I - "$1" <<'PY'
import json, sys, collections
n = collections.Counter()
for l in open(sys.argv[1], errors="replace"):
    try: e = json.loads(l)
    except ValueError: continue
    if e.get("type") == "tool_execution_start": n[e.get("toolName", "?")] += 1          # pi / little-coder
    for c in (e.get("message") or {}).get("content") or []:                              # qwen-code
        if isinstance(c, dict) and c.get("type") == "tool_use": n[c.get("name")] += 1
print(" ".join(f"{k}={v}" for k, v in n.items()) or "-")
PY
}

correr() {  # correr AGENTE CARPETA
  case "$1" in
    qcode)
      ( source "$R/lib/config.sh"; source "$R/lib/qwencode.sh"; _qwen_code_prepare "$HOME/.qwen" "$CTX" "$ALIAS" )
      ( cd "$2" && OPENAI_API_KEY=local OPENAI_BASE_URL=http://127.0.0.1:8001/v1 OPENAI_MODEL="$ALIAS" \
          timeout "$TMAX" "$QWEN_CLI" "$PEDIDO" --approval-mode auto-edit -o stream-json ) ;;
    pi)
      ( source "$R/lib/config.sh"; source "$R/lib/pi.sh"
        QWENX_TEMP=$(arg --temp) QWENX_TOPP=$(arg --top-p) QWENX_TOPK=$(arg --top-k) QWENX_MINP=$(arg --min-p) \
          _qwen_pi_prepare qwen-local "$ALIAS" "$CTX" ) >/dev/null
      # tu Pi normal: la misma función que usa el launcher en modo edit (tus extensiones, AGENTS.md,
      # herramientas de edición); solo se agregan -p, json y --thinking $EFFORT (igual nivel que los otros)
      ( cd "$2" && source "$R/lib/config.sh" && source "$R/lib/pi.sh" \
          && export -f _qwen_pi _qwen_idioma_prompt && export QWEN_PI_DIR QWEN_PI_TOOLS_EDIT QWEN_PI_TOOLS_RO QWEN_PI_NO_SESSION=1 \
          && timeout "$TMAX" bash -c '_qwen_pi edit qwen-local "$1" -p --mode json --thinking "$3" "$2"' _ "$ALIAS" "$PEDIDO" "$EFFORT" ) ;;
    lc)   # little-coder adaptado (lib/lc.sh): tu kit elegido, temperatura del perfil, --thinking $EFFORT
      ( cd "$2" && source "$R/lib/config.sh" && source "$R/lib/pi.sh" && source "$R/lib/lc.sh" \
          && _qwen_lc_prepare "$ALIAS" "$CTX" && export -f _qwen_lc _qwen_idioma_prompt \
          && export QWEN_LC_DIR QWEN_LC_BIN QWEN_PI_TOOLS_RO QWEN_PI_NO_SESSION=1 QWENX_TEMP="$(arg --temp)" \
          && timeout "$TMAX" bash -c '_qwen_lc edit "$1" -p --mode json --thinking "$3" "$2"' _ "$ALIAS" "$PEDIDO" "$EFFORT" ) </dev/null ;;
    *) echo "agente desconocido: $1" >&2; return 2 ;;
  esac
}

{ echo "== $(date '+%F %R') · tarea v2 (3 archivos, 19 pruebas) · lc=adaptado · $MID · ctx=$CTX · temp=$(arg --temp) budget=$(arg --reasoning-budget) effort=$EFFORT · tope ${TMAX}s"
  printf '%-6s %-7s %6s %8s %5s  %s\n' agente oráculo seg tokens pet herramientas; } | tee -a "$Q/resumen.txt"
# el kit respalda en /tmp/qwen: lo que ya había (tuyo) se aparta una vez y lo que deja cada agente se guarda en
# sus logs, para que el siguiente no tropiece con archivos ajenos (pasó: write de LC rechazado por un test de Pi)
[ -e /tmp/qwen ] && mv /tmp/qwen "/tmp/qwen.antes-rapida-$(date +%s)"
for a in "${AGENTES[@]}"; do
  W="$TRABAJO/$a"; mkdir -p "$W"; cp "$Q"/inicial/*.js "$W/"
  linea=$(( $(wc -l < "$LOGS/servidor.log") + 1 )); t0=$(date +%s)
  correr "$a" "$W" > "$LOGS/$a.jsonl" 2> "$LOGS/$a.err"; rc=$?
  seg=$(( $(date +%s) - t0 )); read -r tok pet < <(tokens_desde "$linea")
  nota="$(node "$Q/oraculo.js" "$W")"; echo "$nota" > "$LOGS/$a.oraculo.json"
  cp -r "$W" "$RES/$a"
  [ -e /tmp/qwen ] && mv /tmp/qwen "$LOGS/$a.tmp-qwen"
  ok="$(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print("%s/%s" % (d["ok"], d["total"]))' "$nota" 2>/dev/null || echo "?")"
  [ "$rc" = 124 ] && ok="$ok⏱"
  printf '%-6s %-7s %6s %8s %5s  %s\n' "$a" "$ok" "$seg" "$tok" "$pet" "$(herramientas "$LOGS/$a.jsonl")" | tee -a "$Q/resumen.txt"
done
echo "(⏱ = cortado por el tope de ${TMAX}s; fallos en rapida/logs/<agente>.oraculo.json; archivos en rapida/resultados/)" | tee -a "$Q/resumen.txt"
