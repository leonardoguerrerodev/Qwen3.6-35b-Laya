#!/usr/bin/env bash
# correr.sh [lc|pi|ambos] — el pedido «Grano Sur» de la variante E (qwen-code), ahora con:
#   G = little-coder 1.20.0 tal como viene (sus ~35 extensiones), contra el mismo llama-server
#   F = Pi + kit de oficio del launcher (maxTokens ctx/2, nivel de razonamiento medium)
# Servidor: el comando del perfil activo de q38 (punto-dulce) con -c 49152, igual que E.
# Resultados en G/ y F/; logs en logs/; una línea por corrida en resumen.txt. Ver README.md.
set -u
D="$(cd "$(dirname "$0")" && pwd)"; R="$D/../../.."; QUE="${1:-lc}"; MID="${MID:-q38}"; CTX="${CTX:-49152}"
case "$QUE" in lc|pi|ambos) ;; *) echo "uso: $0 [lc|pi|ambos]" >&2; exit 2 ;; esac
pgrep -x llama-server >/dev/null && { echo "Hay un llama-server corriendo: qwen-stop primero." >&2; exit 1; }
[ -x "$D/lc/node_modules/.bin/little-coder" ] || { echo "Falta little-coder: (cd lc && npm ci --ignore-scripts)" >&2; exit 1; }

# mismo texto que PEDIDO en ../correr_web.sh y ../correr_qcode.sh
PEDIDO='una landing page de una cafetería ficticia llamada «Grano Sur»: cabecera con navegación, hero con llamado a la acción, menú de productos (al menos 9, con nombre, descripción corta y precio en pesos chilenos) filtrable por categoría (café, té, pastelería) con JavaScript, sección de horario y ubicación, pie de página, botón de modo oscuro que se recuerde con localStorage, y diseño responsive que se vea bien en celular y en escritorio. Archivos: index.html, styles.css y app.js, sin librerías ni CDNs. Cuida el diseño: tipografía, paleta coherente, espaciado y detalles.'

# ── servidor: el MISMO comando que arma el menú para el perfil activo (como correr_qcode.sh) ──
mapfile -d '' CMD < <(python3 - "$R" "$MID" <<'PY'
import os, sys; R, mid = sys.argv[1:]
sys.path.insert(0, os.path.join(R, "banco")); sys.argv = ["x"]
import prueba_corta as p
p.PUERTO = "8001"
c, _ = p.comando(mid, p.MODELOS[mid][1]); sys.stdout.write("\0".join(c) + "\0")
PY
)
[ "${#CMD[@]}" -gt 1 ] || { echo "no pude armar el comando del servidor" >&2; exit 1; }
arg() { local i; for ((i=0;i<${#CMD[@]};i++)); do [ "${CMD[i]}" = "$1" ] && { echo "${CMD[i+1]}"; return; }; done; }
mkdir -p "$D/logs"
printf '%q ' "${CMD[@]}" -c "$CTX" > "$D/logs/servidor-cmd.txt"   # para el registro: qué servidor corrió
"${CMD[@]}" -c "$CTX" > "$D/logs/servidor.log" 2>&1 & SPID=$!
trap 'kill $SPID 2>/dev/null; wait $SPID 2>/dev/null' EXIT
until curl -sf localhost:8001/health >/dev/null; do
  kill -0 $SPID 2>/dev/null || { echo "el servidor no cargó (logs/servidor.log)" | tee -a "$D/resumen.txt"; exit 1; }; sleep 1
done

archivos() { (cd "$1" && ls *.html *.css *.js 2>/dev/null | xargs -I{} sh -c 'printf "%s(%s) " {} $(wc -l < {})'); }
herramientas() { python3 -I - "$1" <<'PY'
import json, sys, collections
n = collections.Counter()
for l in open(sys.argv[1], errors="replace"):
    try: e = json.loads(l)
    except ValueError: continue
    if e.get("type") == "tool_execution_start": n[e.get("toolName", "?")] += 1
print(" ".join(f"{k}={v}" for k, v in n.items()) or "sin-tools")
PY
}

# ── G: little-coder tal cual. HOME y agente de Pi aislados en estado/: no toca ~/.pi, ~/.pi-qwen ni ~/.config ──
correr_lc() {
  local L="$D/logs/G" t0 rc seg
  rm -rf "$D/G" "$L" "$D/estado"; mkdir -p "$D/G" "$L" "$D/estado/home" "$D/estado/pi-agent"
  t0=$(date +%s)
  ( cd "$D/G" && HOME="$D/estado/home" PI_CODING_AGENT_DIR="$D/estado/pi-agent" \
      LITTLE_CODER_MODELS_FILE="$D/models-lc.json" LLAMACPP_API_KEY=local \
      LITTLE_CODER_NO_UPDATE_CHECK=1 PATH="$D/lc/node_modules/.bin:$PATH" \
      timeout 1800 little-coder --no-update-check -p --no-session --mode json \
        --model llamacpp/qwen3.8-27b "Crea $PEDIDO" ) > "$L/lc.jsonl" 2> "$L/lc.err"
  rc=$? seg=$(( $(date +%s) - t0 ))
  python3 -I "$R/evals/metricas.py" "$L/lc.jsonl" "$D/G" > "$L/metricas.json" 2>/dev/null
  echo "G little-coder 1.20.0: rc=$rc ${seg}s tools: $(herramientas "$L/lc.jsonl") archivos: $(archivos "$D/G")" | tee -a "$D/resumen.txt"
}

# ── F: Pi con la config del launcher (lib/pi.sh: maxTokens ctx/2, thinkingLevelMap) y el kit de oficio ──
correr_pi() {
  local L="$D/logs/F" t0 rc seg alias
  alias="$(arg --alias)"; alias="${alias:-qwen3.6-35b}"
  ( source "$R/lib/config.sh"; source "$R/lib/pi.sh"
    QWENX_TEMP=$(arg --temp) QWENX_TOPP=$(arg --top-p) QWENX_TOPK=$(arg --top-k) QWENX_MINP=$(arg --min-p) \
      _qwen_pi_prepare qwen-local "$alias" "$CTX" ) || { echo "F: no pude preparar Pi" | tee -a "$D/resumen.txt"; return 1; }
  rm -rf "$D/F" "$L"; mkdir -p "$D/F" "$L"
  t0=$(date +%s)
  ( cd "$D/F" && PI_CODING_AGENT_DIR="$HOME/.pi-qwen/agent" timeout 1800 \
      pi -p --no-session --mode json --provider qwen-local --model "$alias" --thinking medium \
        --tools read,grep,find,ls,edit,write,bash "Crea $PEDIDO" ) > "$L/pi.jsonl" 2> "$L/pi.err"
  rc=$? seg=$(( $(date +%s) - t0 ))
  python3 -I "$R/evals/metricas.py" "$L/pi.jsonl" "$D/F" > "$L/metricas.json" 2>/dev/null
  echo "F pi+kit medium: rc=$rc ${seg}s tools: $(herramientas "$L/pi.jsonl") archivos: $(archivos "$D/F")" | tee -a "$D/resumen.txt"
}

echo "== $(date '+%F %R') $QUE · ctx=$CTX · $MID: temp=$(arg --temp) budget=$(arg --reasoning-budget) effort=$(arg --reasoning-effort)" | tee -a "$D/resumen.txt"
case "$QUE" in
  lc) correr_lc ;;
  pi) correr_pi ;;
  ambos) correr_lc; correr_pi ;;
esac
