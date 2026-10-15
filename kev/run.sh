#!/usr/bin/env bash
# Uso: ./run.sh gpu|cpu [modelo]     (modelo por defecto: jaredpalmer/kev-4b)
MODE="${1:-}"; MODEL="${2:-jaredpalmer/kev-4b}"; PORT=8009
cd "$(dirname "$0")"
[ "$MODE" = gpu ] || [ "$MODE" = cpu ] || { echo "Uso: ./run.sh gpu|cpu [modelo]"; exit 1; }
[ -f prompts.jsonl ] || { echo "Falta prompts.jsonl"; exit 1; }
vram() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' '; }
V0=$(vram)
if [ "$MODE" = gpu ]; then
  if [ "${V0:-0}" -gt 2000 ] 2>/dev/null; then
    echo "Hay ${V0} MiB de VRAM en uso: cierra qwen y Ollama (sudo systemctl stop ollama)"; exit 1
  fi
else
  export CUDA_VISIBLE_DEVICES=""
fi
echo "Modo: $MODE | Modelo: $MODEL | VRAM antes: ${V0} MiB"

cd kev-repo
.venv/bin/python -m kev.serve --run "$MODEL" --port $PORT > ../server.log 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null' EXIT
echo -n "Arrancando servidor (la primera vez descarga el modelo)"
for i in $(seq 1 360); do
  curl -sf localhost:$PORT/v1/models >/dev/null && break
  kill -0 $PID 2>/dev/null || { echo; echo "El servidor murió, últimas líneas de server.log:"; tail -n 15 ../server.log; exit 1; }
  sleep 5; echo -n .
done
echo
.venv/bin/python ../bench_kev.py "http://127.0.0.1:$PORT"
RC=$?
RAM=$(awk '/VmHWM/{printf "%.0f", $2/1024}' /proc/$PID/status 2>/dev/null)
echo "  RAM pico servidor  : ${RAM:-?} MB   (referencia: te quedan ~6600 MB libres con Q4 cargado)"
echo "  VRAM después       : $(vram) MiB (antes: ${V0} MiB)"
if [ $RC -ne 0 ]; then
  echo; echo "=== La prueba falló: líneas de error del servidor ==="
  grep -n -E "Error|error|Exception" ../server.log | tail -n 12
  echo "--- cola de server.log ---"; tail -n 25 ../server.log
fi
