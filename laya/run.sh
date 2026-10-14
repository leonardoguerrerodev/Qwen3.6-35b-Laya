#!/usr/bin/env bash
cd "$(dirname "$0")"
vram() { nvidia-smi --query-gpu=memory.used --format=csv,noheader 2>/dev/null || echo "n/d"; }
echo "VRAM antes: $(vram)"
for m in typed-decisions multilingual; do
  .venv/bin/python bench_laya.py "$m" 2>&1 | grep -v -i warn
done
echo; echo "VRAM después: $(vram)  (debe ser igual que antes)"
