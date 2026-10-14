#!/usr/bin/env bash
# fase6.sh — corre todo lo que falta de la Fase 6 sin intervención (secuencial: la GPU es una sola)
# Rutas relativas al repo: este script vive en <repo>/scripts/ y deja todo en <repo>/results/.
# Uso: bash scripts/fase6.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RESULTS="$REPO_DIR/results"
export BENCH_DIR="${BENCH_DIR:-$RESULTS/bench-qwen}"   # lo lee bench-qwen.sh
BENCH="$SCRIPT_DIR/bench-qwen.sh"
SETUP="$REPO_DIR/setup/qwen-setup.sh"
CSV="$BENCH_DIR/resultados.csv"
OUT="$RESULTS/fase6-resumen.txt"
LLB="$HOME/llama.cpp/build/bin/llama-bench"
mkdir -p "$RESULTS"

# sudo vivo durante toda la corrida
sudo -v || exit 1
( while true; do sudo -n true; sleep 50; done ) & KEEP=$!
trap 'kill $KEEP 2>/dev/null' EXIT

echo "##### 1. Estado de la config (--check) y WebSearch denegado"
bash "$SETUP" --check
python3 -c "import json,os;d=json.load(open(os.path.expanduser('~/.claude-local/settings.json')));print('permissions.deny =',d.get('permissions',{}).get('deny'))"

echo; echo "##### 2. Q4: sin thinking y contexto 32k"
sudo systemctl stop ollama; sleep 5
QWENX_NOTHINK=1 bash "$BENCH" llama q4-nothink;  sleep 10
QWENX_CTX=32768 bash "$BENCH" llama q4-ctx32k;   sleep 10

echo; echo "##### 3. IQ3_XXS: barrido de --n-cpu-moe (ub 2048) y benchmark"
M3=$(ls "$HOME"/models/*IQ3_XXS*.gguf 2>/dev/null | head -1)
BEST=""
for n in 28 24 20 16 12; do
  out=$("$LLB" -m "$M3" -ngl 99 -ncmoe $n -b 2048 -ub 2048 -fa 1 -ctk q8_0 -ctv q8_0 -p 4096 -n 128 -r 1 2>&1 | grep -E 'pp4096|tg128|error')
  echo "== iq3 ncmoe=$n"; echo "$out"
  echo "== iq3 ncmoe=$n"$'\n'"$out" >> "$RESULTS/bench-iq3.txt"
  if echo "$out" | grep -q 'tg128' && ! echo "$out" | grep -qi 'error'; then BEST=$n; else break; fi
done
if [ -n "$BEST" ]; then NC3=$((BEST + 2)); else NC3=40; fi
echo "== IQ3_XXS: suelo del barrido = ${BEST:-ninguno}; el servidor usa --n-cpu-moe $NC3 (margen +2 por el contexto de 64k)"
sleep 10
QWENX_MODEL="$M3" QWENX_NCMOE=$NC3 bash "$BENCH" llama iq3xxs; sleep 10

echo; echo "##### 4. Ollama (con el fix de la Fase 1)"
sudo systemctl start ollama; sleep 8
bash "$BENCH" ollama base-ollama
ollama stop qwen3.6:35b 2>/dev/null
sudo systemctl stop ollama

echo; echo "##### 5. Resumen"
column -s, -t "$CSV"
for E in q4-base q4-nothink q4-ctx32k iq3xxs base-ollama; do
  D=$(ls -d "$BENCH_DIR"/runs/$E-*/ 2>/dev/null | tail -1)
  [ -n "$D" ] || continue
  echo; echo "===== $E ====="
  L="${D}llama-server.log"
  [ -f "$L" ] || { echo "(sin llama-server.log)"; continue; }
  echo "-- frío (primer prompt) --";    grep 'prompt eval time' "$L" | head -1
  echo "-- contexto máximo --";         grep -oE 'n_tokens = [0-9]+' "$L" | sort -t= -k2 -n | tail -1
  echo "-- generación mín / máx --";    grep ' eval time' "$L" | grep -v prompt | grep -oE '[0-9.]+ tokens per second' | sort -n | sed -n '1p;$p'
done
