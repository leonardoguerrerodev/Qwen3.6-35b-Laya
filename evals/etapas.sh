#!/usr/bin/env bash
# etapas.sh — tarea por etapas en UNA sesión de Pi: tras cada etapa se verifica y se pasa a la siguiente.
# Uso: etapas.sh <sonda> <etiqueta> <proyecto> <tarjeta.md> <modo> [args extra de pi...]
#   <tarjeta.md>: ruta RELATIVA al proyecto (ej. tareas/001b-wasd-etapas.md).
#   modo ciego     : siempre pasa a la siguiente etapa (el flujo de Leo a mano).
#   modo verificado: si la etapa no pasa, se le devuelve la salida del check (1 reintento) y luego sigue.
# Variables:
#   KIT=1     → usa el kit: SOLO la skill etapas (--no-skills --skill …; así no se cuelan ponytail ni voz),
#               arranca con "/skill:etapas <tarjeta> …" (carga forzada, §3.1 de la referencia) y sigue con "/sigue N".
#               KIT=0 (defecto) → línea base: pega la tarjeta y sigue con "continua"; corre con --no-skills.
#   DESDE=N   → empieza en la etapa N (para retomar tras un BLOQUEADA; la sesión es nueva).
#   LIMPIAR="index.html src test" → borra SOLO esas rutas (relativas) antes de empezar. Solo para evals; vacío = no borra nada.
# Checks en sondas/<sonda>/etapas.txt (N|comando). Una fila por etapa e intento en etapas.csv.
set -u
EVALS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SONDA=$1 ETQ=$2 PROY=$3 TARJETA=$4 MODO=$5; shift 5
KIT=${KIT:-0} LIMPIAR=${LIMPIAR:-}
export ORACULO="$EVALS/sondas/$SONDA/oraculo.test.js"
export QWENGAME_DIR="$PROY"   # los checks por etapa también miran ESTE proyecto (no el QwenGame por defecto)
CHECKS="$EVALS/sondas/$SONDA/etapas.txt"
CSV="$EVALS/etapas.csv"
[ -d "$PROY/.git" ] && [ -f "$PROY/AGENTS.md" ] && [ -f "$PROY/$TARJETA" ] || { echo "Proyecto o tarjeta inválidos: $PROY / $TARJETA" >&2; exit 2; }
ID="$SONDA-$ETQ-$(date +%Y%m%d-%H%M%S)"
OUT="$PROY/runs/$ID"; mkdir -p "$OUT/sesion"
SID=$(python3 -c 'import uuid;print(uuid.uuid4())')
for r in $LIMPIAR; do case "$r" in /*|*..*) echo "LIMPIAR solo acepta rutas relativas: $r" >&2; exit 2;; esac; rm -rf -- "${PROY:?}/$r"; done
[ -f "$CSV" ] || echo "id,etapa,intento,seg,check,dijo_lista,metricas_json" > "$CSV"
# Foto del proyecto antes de que Qwen toque nada: auditar con `diff -r` y revertir sin depender de commits
tar -C "$PROY" --exclude=./runs --exclude=./.git --exclude=./docs --exclude="*.mp4" --exclude="*.meshy" -czf "$OUT/antes.tar.gz" .

EXTRA=("$@")
if [ "$KIT" = 1 ]; then EXTRA+=(--no-skills --skill "$EVALS/../.pi-qwen/agent/skills/etapas"); else EXTRA+=(--no-skills --no-prompt-templates); fi
pi_msg() {  # $1 = archivo jsonl de salida, $2 = mensaje
  ( cd "$PROY" && PI_CODING_AGENT_DIR="$HOME/.pi-qwen/agent" timeout 1800 \
    pi -p --session-dir "$OUT/sesion" --session-id "$SID" --mode json \
    --tools read,grep,find,ls,edit,write,bash "${EXTRA[@]}" "$2" < /dev/null ) > "$1" 2>> "$OUT/pi.err"
}

primera=1
grep -v '^#' "$CHECKS" | while IFS='|' read -r N CMD; do
  [ "$N" -lt "${DESDE:-1}" ] && continue   # DESDE=N retoma una corrida cortada en la etapa N
  if [ "$primera" = 1 ]; then
    if [ "$KIT" = 1 ]; then msg="/skill:etapas Tarea: $TARJETA. Haz solo la etapa $N."; else msg="$(cat "$PROY/$TARJETA")"; fi
    primera=0
  else
    if [ "$KIT" = 1 ]; then msg="/sigue $N"; else msg="continua"; fi
  fi
  for intento in 1 2; do
    J="$OUT/e$N-$intento.jsonl"
    t0=$(date +%s); pi_msg "$J" "$msg"; seg=$(( $(date +%s) - t0 ))
    ( cd "$PROY" && bash -c "$CMD" < /dev/null ) > "$OUT/e$N-$intento.check" 2>&1 && ok=1 || ok=0
    m=$(python3 -I "$EVALS/metricas.py" "$J" "$PROY")
    lista=$(echo "$m" | grep -q "ETAPA $N LISTA" && echo 1 || echo 0)
    printf '%s,%s,%s,%s,%s,%s,"%s"\n' "$ID" "$N" "$intento" "$seg" "$ok" "$lista" "$(echo "$m" | sed 's/"/""/g')" >> "$CSV"
    echo "$ID etapa $N intento $intento: ${seg}s check=$ok lista=$lista"
    # BLOQUEADA = la tarjeta es ambigua o Qwen no puede: se corta la corrida para que Claude decida
    if echo "$m" | grep -q "ETAPA $N BLOQUEADA"; then echo "$ID BLOQUEADA en la etapa $N: corrida detenida"; exit 3; fi
    if [ "$ok" = 1 ] || [ "$MODO" = ciego ] || [ "$intento" = 2 ]; then break; fi
    msg="La etapa $N no pasa la verificación. Salida:
$(tail -n 25 "$OUT/e$N-$intento.check")
Corrige solo la etapa $N y responde ETAPA $N LISTA."
  done
done

if [ -f "$ORACULO" ]; then
  QWENGAME_DIR="$PROY" node --test "$ORACULO" > "$OUT/oraculo-final.txt" 2>&1
  echo "$ID FINAL oráculo: $(grep -oP '^# pass \K\d+' "$OUT/oraculo-final.txt")✓ $(grep -oP '^# fail \K\d+' "$OUT/oraculo-final.txt")✗"
fi
