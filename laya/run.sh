#!/usr/bin/env bash
# Compara los checkpoints de laya y kev (CPU) con laya/prompts.jsonl y muestra una tabla al final.
#   ./run.sh          typed-decisions, multilingual y kev
#   ./run.sh laya     solo los de laya        ./run.sh kev   solo kev
cd "$(dirname "$0")"
export QWEN_ROOT="$(cd .. && pwd)"
. "$QWEN_ROOT/lib/config.sh"
. "$QWEN_ROOT/lib/laya.sh"
WHAT="${1:-all}"
vram() { nvidia-smi --query-gpu=memory.used --format=csv,noheader 2>/dev/null || echo "n/d"; }
ram() { free -m | awk '/^Mem:/{m=$7} /^Swap:/{s=$3} END{print m" MB disp., swap usado "s" MB"}'; }
OUT="$(mktemp)"
trap 'rm -f "$OUT"; _kev_down' EXIT
echo "VRAM antes: $(vram) | RAM: $(ram)"
if [ "$WHAT" != kev ]; then
  for m in typed-decisions multilingual; do
    .venv/bin/python bench_laya.py "$m" 2>&1 | grep -v -i warn | tee -a "$OUT"
  done
fi
if [ "$WHAT" != laya ]; then
  if _kev_up; then
    .venv/bin/python bench_laya.py kev 2>&1 | grep -v -i warn | tee -a "$OUT"
  else
    echo "kev: no se pudo arrancar (log: $KEV_LOG)"
  fi
fi
echo; echo "VRAM después: $(vram)  (debe ser igual que antes) | RAM: $(ram)"
echo; echo "== Resumen (umbrales: acuerdo >= 80%, mediana <= 500 ms, RAM <= 2048 MB) =="
printf '%-34s %7s %8s %8s %8s  %s\n' modelo acuerdo med_ms p95_ms ram_mb "aciertos(compl/destr/inj)"
grep '^RESUMEN' "$OUT" | awk -F'\t' '{printf "%-34s %7s %8s %8s %8s  %s\n", $2, $3, $4, $5, $6, $7}'
