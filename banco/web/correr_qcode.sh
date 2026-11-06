#!/usr/bin/env bash
# correr_qcode.sh [modelo] [presupuesto] — variante E: el mismo pedido «todo junto» de A (correr_web.sh),
# pero con Qwen Code (qcode) y el razonamiento con tope en llama-server (--reasoning-budget).
# Presupuesto 0 = sin tope. Qwen Code solo puede editar archivos (auto-edit): shell queda denegado.
# Resultado en E/, logs en logs/E/, una línea en resumen.txt.
set -u
D="$(cd "$(dirname "$0")" && pwd)"; R="$D/../.."; MID="${1:-q38}"; BUD="${2:-6000}"
MSG="Basta de planear: crea o edita el archivo ahora con la herramienta y mejóralo después."
QWEN_CLI="$HOME/.npm-global/bin/qwen"   # el binario; `qwen` en la shell de Leo es el launcher
pgrep -x llama-server >/dev/null && { echo "Hay un llama-server corriendo: qwen-stop primero." >&2; exit 1; }

# mismo texto que PEDIDO en correr_web.sh
PEDIDO='una landing page de una cafetería ficticia llamada «Grano Sur»: cabecera con navegación, hero con llamado a la acción, menú de productos (al menos 9, con nombre, descripción corta y precio en pesos chilenos) filtrable por categoría (café, té, pastelería) con JavaScript, sección de horario y ubicación, pie de página, botón de modo oscuro que se recuerde con localStorage, y diseño responsive que se vea bien en celular y en escritorio. Archivos: index.html, styles.css y app.js, sin librerías ni CDNs. Cuida el diseño: tipografía, paleta coherente, espaciado y detalles.'

mapfile -d '' CMD < <(python3 - "$R" "$MID" <<'PY'
import os, sys; R, mid = sys.argv[1:]
sys.path.insert(0, os.path.join(R, "banco")); sys.argv = ["x"]
import prueba_corta as p
p.PUERTO = "8001"
c, _ = p.comando(mid, p.MODELOS[mid][1]); sys.stdout.write("\0".join(c) + "\0")
PY
)
[ "$BUD" != 0 ] && CMD+=(--reasoning-budget "$BUD" --reasoning-budget-message "$MSG")
"${CMD[@]}" > "$D/servidor-E.log" 2>&1 & SPID=$!
trap 'kill $SPID 2>/dev/null; wait $SPID 2>/dev/null' EXIT
until curl -sf localhost:8001/health >/dev/null; do kill -0 $SPID 2>/dev/null || { echo "E: el servidor no cargó" | tee -a "$D/resumen.txt"; exit 1; }; sleep 1; done

L="$D/logs/E"; rm -rf "$D/E" "$L"; mkdir -p "$D/E" "$L"
t0=$(date +%s)
( cd "$D/E" && OPENAI_API_KEY=local timeout 1800 "$QWEN_CLI" "Crea $PEDIDO" --approval-mode auto-edit \
    -o stream-json --openai-logging --openai-logging-dir "$L/api" ) > "$L/qcode.jsonl" 2> "$L/qcode.err"
rc=$? seg=$(( $(date +%s) - t0 ))
tools=$(python3 -I - "$L/qcode.jsonl" <<'PY'
import json, sys, collections
n = collections.Counter()
for l in open(sys.argv[1], errors="replace"):
    try: e = json.loads(l)
    except ValueError: continue
    for c in (e.get("message") or {}).get("content") or []:
        if isinstance(c, dict) and c.get("type") == "tool_use": n[c.get("name")] += 1
print(" ".join(f"{k}={v}" for k, v in n.items()) or "sin-tools")
PY
)
echo "E qcode budget=$BUD: rc=$rc ${seg}s tools: $tools archivos: $(cd "$D/E" && ls *.html *.css *.js 2>/dev/null | xargs -I{} sh -c 'printf "%s(%s) " {} $(wc -l < {})')" | tee -a "$D/resumen.txt"
