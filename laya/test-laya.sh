#!/usr/bin/env bash
# test-laya.sh — prueba laya bajo carga real de qwen y mide su costo en RAM, CPU y en la velocidad de qwen.
#
# Uso (qwen ya cargado, llama-server en :8001; cierra Brave y apps pesadas):
#   ./test-laya.sh                      4 configuraciones x 2 repeticiones
#   TAG=cram2048 ./test-laya.sh         etiqueta la corrida (para comparar antes/después de tocar qwen)
#   MODEL=typed-decisions ./test-laya.sh
#   ROUTER_CORES=4 REPS=3 ./test-laya.sh
#
# Configuraciones:
#   qwen-solo    carga de qwen sin router        -> línea base de tok/s y RAM
#   idle         router sin qwen generando       -> latencia/precisión de referencia
#   carga-libre  router mientras qwen genera     -> el caso real
#   carga-pin    igual, con el router fijado a los últimos K núcleos y K hilos (taskset + OMP_NUM_THREADS)
#
# Resultados: tabla al final, filas en <repo>/results/laya-test.csv y salida de cada bench en <repo>/results/laya-test-logs/.
# Rutas relativas: este script vive en <repo>/laya/ (junto a bench_laya.py y .venv); LAYA_DIR, CSV y LOGDIR se pueden sobrescribir.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$HERE/.." && pwd)"
LAYA_DIR="${LAYA_DIR:-$HERE}"
PY="$LAYA_DIR/.venv/bin/python"
MODEL="${MODEL:-multilingual}"
PORT="${PORT:-8001}"
K="${ROUTER_CORES:-2}"
REPS="${REPS:-2}"
TAG="${TAG:-base}"
LOAD_SECS="${LOAD_SECS:-25}"
CSV="${CSV:-$REPO_DIR/results/laya-test.csv}"
LOGDIR="$(dirname "$CSV")/laya-test-logs/$TAG-$(date +%H%M%S)"

[ -x "$PY" ] || { echo "No encuentro $PY (¿está instalado laya en $LAYA_DIR?)"; exit 1; }
[ -f "$LAYA_DIR/bench_laya.py" ] || { echo "No encuentro $LAYA_DIR/bench_laya.py"; exit 1; }
command -v taskset >/dev/null || { echo "Falta taskset (paquete util-linux)"; exit 1; }
curl -sf "http://localhost:$PORT/health" >/dev/null || { echo "qwen no responde en :$PORT. Ábrelo (qwen) y vuelve a correr."; exit 1; }

NCPU=$(nproc)
[ "$K" -lt "$NCPU" ] || { echo "ROUTER_CORES ($K) debe ser menor que los núcleos ($NCPU)"; exit 1; }
PIN="$((NCPU - K))-$((NCPU - 1))"

mkdir -p "$LOGDIR"
FLAGS=$(mktemp -d)
LOAD_PID=""
RAM_PID=""

cleanup() {
  rm -f "$FLAGS/on" "$FLAGS/ram"
  [ -n "$LOAD_PID" ] && kill "$LOAD_PID" 2>/dev/null
  [ -n "$RAM_PID" ] && kill "$RAM_PID" 2>/dev/null
  rm -rf "$FLAGS"
}
trap cleanup EXIT
trap 'echo; echo "cancelado"; exit 130' INT TERM

meminfo_mb() { awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo; }

# --- carga sintética de qwen: peticiones seguidas a /completion; guarda los tok/s de cada una ---
load_start() {
  : > "$1"
  touch "$FLAGS/on"
  (
    while [ -f "$FLAGS/on" ]; do
      curl -s "http://localhost:$PORT/completion" \
        -d '{"prompt":"Escribe un ensayo largo y detallado sobre la historia de la orfebrería en Chile.","n_predict":256,"temperature":0.6,"cache_prompt":false}' \
        | python3 -c 'import sys, json
try:
    print(json.load(sys.stdin)["timings"]["predicted_per_second"])
except Exception:
    pass' >> "$1"
    done
  ) &
  LOAD_PID=$!
}
load_stop() {
  rm -f "$FLAGS/on"
  wait "$LOAD_PID" 2>/dev/null
  LOAD_PID=""
}

# --- muestreo de RAM disponible del sistema (MB) cada 0,3 s ---
ram_start() {
  : > "$1"
  touch "$FLAGS/ram"
  ( while [ -f "$FLAGS/ram" ]; do meminfo_mb >> "$1"; sleep 0.3; done ) &
  RAM_PID=$!
}
ram_stop() {
  rm -f "$FLAGS/ram"
  wait "$RAM_PID" 2>/dev/null
  RAM_PID=""
}

# --- bench de laya (sin pin o fijado a los últimos K núcleos con K hilos) ---
run_router() {  # $1 = pin (0/1), $2 = archivo de salida
  if [ "$1" = 1 ]; then
    ( cd "$LAYA_DIR" && OMP_NUM_THREADS="$K" MKL_NUM_THREADS="$K" taskset -c "$PIN" "$PY" bench_laya.py "$MODEL" ) >"$2" 2>&1
  else
    ( cd "$LAYA_DIR" && "$PY" bench_laya.py "$MODEL" ) >"$2" 2>&1
  fi
}

# salida: acuerdo,lat_mediana,p95,ram_proc
parse_bench() {
  python3 - "$1" <<'PYEOF'
import re, sys
t = open(sys.argv[1], encoding="utf-8", errors="replace").read()
def g(p):
    m = re.search(p, t)
    return m.group(1) if m else "?"
print(",".join([g(r"acuerdo total\s*:\s*(\d+)%"),
                g(r"latencia mediana\s*:\s*(\d+) ms"),
                g(r"p95 (\d+) ms"),
                g(r"RAM pico del proc\.\s*:\s*(\d+) MB")]))
PYEOF
}

avg_file() {
  python3 - "$1" <<'PYEOF'
import sys
v = [float(x) for x in open(sys.argv[1]).read().split() if x.strip()]
print(f"{sum(v)/len(v):.1f}" if v else "?")
PYEOF
}

ROWS=()
[ -f "$CSV" ] || echo "tag,config,rep,acuerdo_pct,lat_med_ms,lat_p95_ms,ram_router_mb,ram_disp_min_mb,qwen_tps" > "$CSV"

one() {  # $1 nombre  $2 carga(0/1)  $3 pin(0/1)  $4 router(0/1)  $5 rep
  local name="$1" load="$2" pin="$3" router="$4" rep="$5"
  local rlog="$LOGDIR/$name.$rep.log" lfile="$FLAGS/$name.$rep.tps" mfile="$FLAGS/$name.$rep.ram"
  local met="?,?,?,?" tps="n/a" ramin ac lat p95 ramr
  echo "-> $name (rep $rep)"
  ram_start "$mfile"
  if [ "$load" = 1 ]; then load_start "$lfile"; sleep 6; fi   # el router arranca con qwen ya generando
  if [ "$router" = 1 ]; then
    run_router "$pin" "$rlog"
    met=$(parse_bench "$rlog")
  else
    sleep "$LOAD_SECS"
  fi
  if [ "$load" = 1 ]; then load_stop; tps=$(avg_file "$lfile"); fi
  ram_stop
  ramin=$(sort -n "$mfile" | head -n 1)
  IFS=, read -r ac lat p95 ramr <<< "$met"
  if [ "$router" = 1 ] && [ "$ac" = "?" ]; then echo "   aviso: no pude leer el resultado, mira $rlog"; fi
  echo "$TAG,$name,$rep,$ac,$lat,$p95,$ramr,$ramin,$tps" >> "$CSV"
  if [ "$router" = 1 ]; then
    ROWS+=("$(printf '%-12s %-4s %7s %9s %8s %10s %12s %9s' "$name" "$rep" "${ac}%" "${lat} ms" "${p95} ms" "${ramr} MB" "${ramin} MB" "$tps")")
  else
    ROWS+=("$(printf '%-12s %-4s %7s %9s %8s %10s %12s %9s' "$name" "$rep" "-" "-" "-" "-" "${ramin} MB" "$tps")")
  fi
}

echo "laya/$MODEL | tag=$TAG | $NCPU núcleos | router fijado a $PIN ($K hilos) | RAM disponible ahora: $(meminfo_mb) MB"
echo "Logs en $LOGDIR"
echo

CONFIGS=("qwen-solo 1 0 0" "idle 0 0 1" "carga-libre 1 0 1" "carga-pin 1 1 1")
for rep in $(seq 1 "$REPS"); do
  for c in "${CONFIGS[@]}"; do
    read -r cname cload cpin crouter <<< "$c"
    one "$cname" "$cload" "$cpin" "$crouter" "$rep"
    sleep 3
  done
done

echo
echo "===== resumen (tag=$TAG) ====="
printf '%-12s %-4s %7s %9s %8s %10s %12s %9s\n' config rep acuerdo "lat med" p95 "RAM router" "RAM disp min" "qwen tok/s"
for r in "${ROWS[@]}"; do echo "$r"; done
echo
echo "Qué mirar:"
echo "  - latencia mediana del router <= 500 ms en carga-libre y carga-pin"
echo "  - RAM disp min >= 4096 MB (piso del plan)"
echo "  - qwen tok/s con router vs qwen-solo: la baja es lo que le cuesta el router a qwen (umbral del plan: >= 20)"
echo "  - carga-pin vs carga-libre: si pin baja la latencia sin bajar los tok/s de qwen, déjalo fijo"
echo "  (las peticiones de carga que cruzan el borde de la corrida diluyen un poco los tok/s: es aproximado)"
echo
echo "Para probar -cram: reabre qwen con 'QWENX_CRAM=2048 qwen' y corre: TAG=cram2048 ./test-laya.sh"
echo "(compara con las filas tag=base en $CSV)"
