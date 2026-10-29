#!/usr/bin/env bash
# correr.sh — una corrida de una sonda: limpia el proyecto, llama a Qwen con pi -p, corre el oráculo y anota en resultados.csv.
# Uso: correr.sh <sonda> <etiqueta> <proyecto> <prompt> [args extra de pi...]
#   <prompt> es el texto que recibe pi (ej. "$(cat tareas/001-wasd.md)" o "/tarea tareas/001-wasd.md").
# Antes de correr borra SOLO las rutas de $LIMPIAR (relativas al proyecto). Nunca borra nada más.
set -u
EVALS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SONDA=$1 ETQ=$2 PROY=$3 PROMPT=$4; shift 4
ORACULO="$EVALS/sondas/$SONDA/oraculo.test.js"
CSV="$EVALS/resultados.csv"
# La limpieza borra archivos: solo en un proyecto con .git y AGENTS.md
[ -d "$PROY/.git" ] && [ -f "$PROY/AGENTS.md" ] || { echo "No parece un proyecto de sonda: $PROY" >&2; exit 2; }
ID="$SONDA-$ETQ-$(date +%Y%m%d-%H%M%S)"
OUT="$PROY/runs/$ID"
mkdir -p "$OUT"

LIMPIAR=${LIMPIAR:-}  # ej. LIMPIAR="index.html src test": borra SOLO esas rutas; vacío = no borra nada
for r in $LIMPIAR; do case "$r" in /*|*..*) echo "LIMPIAR solo acepta rutas relativas: $r" >&2; exit 2;; esac; rm -rf -- "${PROY:?}/$r"; done

t0=$(date +%s)
( cd "$PROY" && PI_CODING_AGENT_DIR="$HOME/.pi-qwen/agent" timeout 1800 \
  pi -p --no-session --mode json --tools read,grep,find,ls,edit,write,bash "$@" "$PROMPT" ) \
  > "$OUT/pi.jsonl" 2> "$OUT/pi.err"
salida=$?
seg=$(( $(date +%s) - t0 ))

QWENGAME_DIR="$PROY" node --test "$ORACULO" > "$OUT/oraculo.txt" 2>&1
ok_or=$(grep -oP '^# pass \K\d+' "$OUT/oraculo.txt" || echo 0)
ko_or=$(grep -oP '^# fail \K\d+' "$OUT/oraculo.txt" || echo "?")
( cd "$PROY" && node --test test/*.test.js ) > "$OUT/tests-propios.txt" 2>&1 && propios=ok || propios=falla
# Archivos que dejó (fuera de los conservados) → para ver si se salió de la lista permitida
( cd "$PROY" && find . -type f ! -path './.git/*' ! -path './runs/*' ! -path './tareas/*' ! -name AGENTS.md ! -name .gitignore | sort ) > "$OUT/archivos.txt"
mkdir -p "$OUT/src"; cp "$PROY"/src/*.js "$OUT/src/" 2>/dev/null; cp -r "$PROY"/{index.html,test} "$OUT/" 2>/dev/null  # solo código: src/ puede tener modelos pesados

m=$(python3 -I "$EVALS/metricas.py" "$OUT/pi.jsonl" "$PROY")
echo "$m" > "$OUT/metricas.json"
[ -f "$CSV" ] || echo "id,sonda,etiqueta,salida_pi,seg_reloj,oraculo_pass,oraculo_fail,tests_propios,archivos,metricas_json" > "$CSV"
printf '%s,%s,%s,%s,%s,%s,%s,%s,"%s","%s"\n' "$ID" "$SONDA" "$ETQ" "$salida" "$seg" "$ok_or" "$ko_or" "$propios" \
  "$(paste -sd' ' "$OUT/archivos.txt")" "$(echo "$m" | sed 's/"/""/g')" >> "$CSV"
echo "$ID  pi=$salida  ${seg}s  oráculo ${ok_or}✓ ${ko_or}✗  tests propios: $propios"
