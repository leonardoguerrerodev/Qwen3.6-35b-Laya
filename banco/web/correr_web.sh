#!/usr/bin/env bash
# correr_web.sh [modelo] — el Qwen (por Pi, como lo usa Leo) hace la misma página web de dos formas:
#   A/ todo en un solo prompt     B/ por etapas: base que funcione primero, luego mejoras (4 llamadas)
# Lanza llama-server en :8001 con el perfil activo del modelo (q38 por defecto) y lo apaga al final.
# Abrir después: A/index.html y B/index.html. Métricas en */metricas-*.json y resumen.txt.
set -u
D="$(cd "$(dirname "$0")" && pwd)"; R="$D/../.."; MID="${1:-q38}"
pgrep -x llama-server >/dev/null && { echo "Hay un llama-server corriendo: qwen-stop primero." >&2; exit 1; }

PEDIDO='una landing page de una cafetería ficticia llamada «Grano Sur»: cabecera con navegación, hero con llamado a la acción, menú de productos (al menos 9, con nombre, descripción corta y precio en pesos chilenos) filtrable por categoría (café, té, pastelería) con JavaScript, sección de horario y ubicación, pie de página, botón de modo oscuro que se recuerde con localStorage, y diseño responsive que se vea bien en celular y en escritorio. Archivos: index.html, styles.css y app.js, sin librerías ni CDNs. Cuida el diseño: tipografía, paleta coherente, espaciado y detalles.'

# servidor con el MISMO comando que el menú
mapfile -d '' CMD < <(python3 - "$R" "$MID" <<'PY'
import os, sys; R, mid = sys.argv[1:]
sys.path.insert(0, os.path.join(R, "banco")); sys.argv = ["x"]
import prueba_corta as p
p.PUERTO = "8001"  # comando() fija QWEN_PORT desde p.PUERTO
c, _ = p.comando(mid, p.MODELOS[mid][1]); sys.stdout.write("\0".join(c) + "\0")
PY
)
# Pi igual que el launcher: maxTokens = ctx/4 y muestreo del perfil (_qwen_pi_prepare de lib/pi.sh)
arg() { local i; for ((i=0;i<${#CMD[@]};i++)); do [ "${CMD[i]}" = "$1" ] && { echo "${CMD[i+1]}"; return; }; done; }
CTX="${CTX:-$(arg -c)}"
( source "$R/lib/config.sh"; source "$R/lib/pi.sh"
  QWENX_TEMP=$(arg --temp) QWENX_TOPP=$(arg --top-p) QWENX_TOPK=$(arg --top-k) QWENX_MINP=$(arg --min-p) \
    _qwen_pi_prepare qwen-local qwen3.6-35b "$CTX" ) || { echo "no pude preparar Pi"; exit 1; }
"${CMD[@]}" -c "$CTX" > "$D/servidor.log" 2>&1 & SPID=$!
trap 'kill $SPID 2>/dev/null; wait $SPID 2>/dev/null' EXIT
until curl -sf localhost:8001/health >/dev/null; do kill -0 $SPID 2>/dev/null || { echo "el servidor no cargó"; exit 1; }; sleep 1; done

pi_en() {  # pi_en CARPETA ETIQUETA PROMPT
  local t0=$(date +%s) L="$D/logs/$(basename "$1")"; mkdir -p "$L"   # logs fuera: el modelo no los lee
  ( cd "$1" && PI_CODING_AGENT_DIR="$HOME/.pi-qwen/agent" timeout 1800 \
    pi -p --no-session --mode json --tools read,grep,find,ls,edit,write,bash "$3" ) > "$L/pi-$2.jsonl" 2> "$L/pi-$2.err"
  local rc=$? seg=$(( $(date +%s) - t0 ))
  python3 -I "$R/evals/metricas.py" "$L/pi-$2.jsonl" "$1" > "$L/metricas-$2.json"
  echo "$(basename "$1") $2: pi=$rc ${seg}s archivos: $(cd "$1" && ls *.html *.css *.js 2>/dev/null | xargs -I{} sh -c 'printf "%s(%s) " {} $(wc -l < {})')" | tee -a "$D/resumen.txt"
}

rm -rf "$D/A" "$D/B" "$D/logs"; mkdir -p "$D/A" "$D/B"; : > "$D/resumen.txt"
echo "ctx=$CTX maxTokens=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.pi-qwen/agent/models.json')))['providers']['qwen-local']['models'][0]['maxTokens'])")" | tee -a "$D/resumen.txt"
pi_en "$D/A" todo "Crea $PEDIDO"

pi_en "$D/B" 1-base "Vamos a construir por etapas $PEDIDO
ETAPA 1 de 4, solo esto: crea YA los tres archivos con una base mínima que funcione (estructura HTML semántica completa con todas las secciones y contenido real, CSS básico de layout, app.js vacío salvo un comentario). No hagas diseño fino ni JavaScript todavía. Escribe los archivos cuanto antes; no planees las etapas siguientes."
pi_en "$D/B" 2-diseno "Lee index.html y styles.css. ETAPA 2 de 4: mejora SOLO el diseño en styles.css: paleta coherente con variables CSS, tipografía, espaciado, tarjetas del menú, hero atractivo, detalles visuales. No toques JavaScript. Edita el archivo; no lo reescribas entero si no hace falta."
pi_en "$D/B" 3-js "Lee los tres archivos. ETAPA 3 de 4: en app.js implementa el filtro del menú por categoría (café, té, pastelería, todos) y el botón de modo oscuro recordado en localStorage. Agrega en styles.css las variables del tema oscuro y en index.html lo mínimo que haga falta."
pi_en "$D/B" 4-pulido "Lee los tres archivos. ETAPA 4 de 4: revisa que todo funcione y pule: responsive en celular (menú de navegación, grilla), estados hover/focus, accesibilidad básica (contraste, aria, alt). Corrige errores que encuentres."
echo listo | tee -a "$D/resumen.txt"
