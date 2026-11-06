#!/usr/bin/env bash
# bench-compare.sh — comparación limpia A vs B con llama-server (mismas condiciones)
# Uso: ./bench-compare.sh            (corre A y luego B, ambos prompts)
#      MODEL_B=/ruta/otro.gguf ./bench-compare.sh
# Resultados: ~/bench-compare/<fecha>/  (salidas .txt, reloj .html, resumen)
set -u

# Binario: LLAMA_SERVER explícito > QWEN_LLAMA_BIN > el de ~/.qwen-local.sh > llama-server del PATH
if [ -z "${LLAMA_SERVER:-}" ]; then
  if [ -n "${QWEN_LLAMA_BIN:-}" ]; then
    LLAMA_SERVER="$QWEN_LLAMA_BIN"
  elif [ -f "$HOME/.qwen-local.sh" ]; then
    LLAMA_SERVER="$(bash -c '. "$HOME/.qwen-local.sh" >/dev/null 2>&1; printf %s "$QWEN_LLAMA_BIN"' 2>/dev/null)"
  fi
  LLAMA_SERVER="${LLAMA_SERVER:-llama-server}"
fi
PORT="${PORT:-8099}"

# --- Modelos (ajusta rutas si difieren) ---
MODEL_A="${MODEL_A:-/run/media/xaski/7c0ba586-7758-4419-b3de-f524b9c9a1fb/!models/Qwen3.6/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf}"
MODEL_B="${MODEL_B:-/run/media/xaski/7c0ba586-7758-4419-b3de-f524b9c9a1fb/!models/Qwen3.8/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-mtp.gguf}"
TAG_A="${TAG_A:-q36-35b-a3b}"
TAG_B="${TAG_B:-q38-27b-iq3xxs}"

# --- Flags comunes (idénticos para ambos) ---
COMMON="${COMMON:--b 2048 -ub 512 -c 16384 -np 1 --jinja --cache-type-k q8_0 --cache-type-v q8_0}"
# --- Flags propios de cada modelo (A es MoE: expertos a RAM; B es denso: todo en GPU) ---
ARGS_A="${ARGS_A:--ngl 99 --n-cpu-moe 28}"
ARGS_B="${ARGS_B:--ngl 99}"

# --- Sampling idéntico ---
SEED="${SEED:-42}"
TEMP="${TEMP:-0.6}"
TOP_P="${TOP_P:-0.95}"
TOP_K="${TOP_K:-20}"
MAX_TOKENS="${MAX_TOKENS:-12000}"

OUT="${OUT:-$HOME/bench-compare/$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT"
SERVER_PID=""

cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
}
trap cleanup EXIT INT TERM

vram_used() {
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -n1 | tr -d ' '
  else
    echo 0
  fi
}

# --- Prompts ---
cat > "$OUT/prompt_reloj.txt" <<'EOF'
Crea un único archivo HTML con un reloj analógico animado: segundero con movimiento suave, números del 1 al 12 bien posicionados, hora actual real, y un botón que alterne tema claro/oscuro. Sin librerías externas. Responde solo con el bloque de código HTML.
EOF
cat > "$OUT/prompt_cajas.txt" <<'EOF'
Tengo 3 cajas etiquetadas "Manzanas", "Naranjas" y "Mezcla". Todas las etiquetas están mal puestas. Puedo sacar una sola fruta de una caja, sin mirar dentro. ¿De cuál caja la saco y cómo deduzco el contenido de las tres? Explica brevemente.
EOF

# --- Cliente: envía un prompt y registra métricas ---
cat > "$OUT/client.py" <<'EOF'
import json, sys, time, re, urllib.request

port, tag, name, prompt_file, out_dir, seed, temp, top_p, top_k, max_tokens, vram = sys.argv[1:12]
prompt = open(prompt_file, encoding="utf-8").read().strip()
body = {
    "messages": [{"role": "user", "content": prompt}],
    "seed": int(seed), "temperature": float(temp), "top_p": float(top_p),
    "top_k": int(top_k), "max_tokens": int(max_tokens),
    "cache_prompt": False, "stream": False,
}
req = urllib.request.Request(
    f"http://127.0.0.1:{port}/v1/chat/completions",
    data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=1800) as r:
        data = json.load(r)
except Exception as e:
    print(f"ERROR en {tag}/{name}: {e}", file=sys.stderr)
    sys.exit(1)
wall = time.time() - t0

msg = data["choices"][0]["message"]
content = msg.get("content") or ""
reasoning = msg.get("reasoning_content") or ""
tm = data.get("timings", {})

with open(f"{out_dir}/{tag}_{name}.txt", "w", encoding="utf-8") as f:
    f.write("=== RAZONAMIENTO ===\n" + reasoning + "\n\n=== RESPUESTA ===\n" + content + "\n")

if name == "reloj":
    m = re.search(r"```html\s*(.*?)```", content, re.S)
    html = m.group(1) if m else content
    with open(f"{out_dir}/{tag}_reloj.html", "w", encoding="utf-8") as f:
        f.write(html)

row = {
    "tag": tag, "prompt": name,
    "prompt_n": tm.get("prompt_n"), "pp_tps": tm.get("prompt_per_second"),
    "gen_n": tm.get("predicted_n"), "tg_tps": tm.get("predicted_per_second"),
    "wall_s": round(wall, 1),
    "reasoning_chars": len(reasoning), "answer_chars": len(content),
    "finish": data["choices"][0].get("finish_reason"),
    "vram_mib": int(vram or 0),
}
with open(f"{out_dir}/results.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps(row) + "\n")
print(f"  {tag}/{name}: {row['gen_n']} tok a {row['tg_tps']:.1f} tok/s, {row['wall_s']} s, finish={row['finish']}"
      if row["tg_tps"] else f"  {tag}/{name}: sin timings, {row['wall_s']} s")
EOF

# --- Resumen ---
cat > "$OUT/summary.py" <<'EOF'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1] + "/results.jsonl")]
hdr = ["modelo", "prompt", "pp t/s", "gen tok", "tg t/s", "total s", "razon. chars", "resp. chars", "fin", "VRAM MiB"]
print("\n" + " | ".join(hdr))
print("-" * 100)
f = lambda v, d=1: "-" if v is None else (f"{v:.{d}f}" if isinstance(v, float) else str(v))
for r in rows:
    print(" | ".join([r["tag"], r["prompt"], f(r["pp_tps"]), f(r["gen_n"]), f(r["tg_tps"]),
                      f(r["wall_s"]), f(r["reasoning_chars"]), f(r["answer_chars"]), str(r["finish"]), f(r["vram_mib"])]))
EOF

wait_ready() {
  local i
  for i in $(seq 1 300); do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      echo "El servidor murió al arrancar. Últimas líneas del log:" >&2
      tail -n 25 "$OUT/server_$1.log" >&2
      return 1
    fi
    if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  echo "Timeout esperando al servidor." >&2
  return 1
}

run_model() {
  local tag="$1" model="$2" args="$3"
  echo
  echo "=== $tag ==="
  if [ ! -f "$model" ]; then echo "No existe: $model" >&2; return 1; fi
  if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    echo "El puerto $PORT ya está en uso. Cierra ese servidor o cambia PORT." >&2
    return 1
  fi
  local vbase
  vbase="$(vram_used)"
  # shellcheck disable=SC2086
  "$LLAMA_SERVER" -m "$model" --host 127.0.0.1 --port "$PORT" $COMMON $args \
    > "$OUT/server_$tag.log" 2>&1 &
  SERVER_PID=$!
  wait_ready "$tag" || { cleanup; SERVER_PID=""; return 1; }

  # Backend: aborta solo si el log delata ROCm/HIP/Vulkan sin CUDA; si no, verifica por VRAM.
  if grep -qE 'found [0-9]+ (ROCm|HIP|Vulkan)' "$OUT/server_$tag.log" \
     && ! grep -qE 'found [0-9]+ CUDA' "$OUT/server_$tag.log"; then
    echo "Este llama-server NO está usando CUDA (ver $OUT/server_$tag.log)." >&2
    echo "Pásale tu build CUDA con LLAMA_SERVER=/ruta/al/llama-server" >&2
    cleanup; SERVER_PID=""; return 1
  fi
  local vnow
  vnow="$(vram_used)"
  if [ "${vnow:-0}" -gt 0 ] && [ $(( vnow - vbase )) -lt 1500 ]; then
    echo "AVISO: la VRAM casi no subió al cargar (+$(( vnow - vbase )) MiB): el modelo podría no estar en la GPU NVIDIA." >&2
  fi
  echo "  calentando..."
  python3 - "$PORT" <<'EOF'
import json, sys, urllib.request
req = urllib.request.Request(f"http://127.0.0.1:{sys.argv[1]}/v1/chat/completions",
    data=json.dumps({"messages":[{"role":"user","content":"Hola"}],"max_tokens":16,"cache_prompt":False}).encode(),
    headers={"Content-Type":"application/json"})
urllib.request.urlopen(req, timeout=600).read()
EOF

  local p
  for p in reloj cajas; do
    python3 "$OUT/client.py" "$PORT" "$tag" "$p" "$OUT/prompt_$p.txt" "$OUT" \
      "$SEED" "$TEMP" "$TOP_P" "$TOP_K" "$MAX_TOKENS" "$(vram_used)"
  done

  cleanup
  SERVER_PID=""
  sleep 3   # deja que la GPU libere VRAM antes del siguiente modelo
}

# --- Detecta la sintaxis de flags de ESTE binario ---
if ! command -v "$LLAMA_SERVER" >/dev/null 2>&1 && [ ! -x "$LLAMA_SERVER" ]; then
  echo "No encuentro llama-server: $LLAMA_SERVER" >&2
  exit 1
fi
HELP="$("$LLAMA_SERVER" --help 2>&1)"
if grep -qE -- 'flash-attn[^\n]*\[on\|off\|auto\]' <<<"$HELP"; then FA_FLAG="--flash-attn on"; else FA_FLAG="-fa"; fi
if grep -q -- '--load-mode' <<<"$HELP"; then LOAD_FLAG="--load-mode none"
elif grep -q -- '--no-mmap' <<<"$HELP"; then LOAD_FLAG="--no-mmap"
else LOAD_FLAG=""; fi
if ! grep -q -- '--n-cpu-moe' <<<"$HELP"; then
  echo "AVISO: este llama-server no tiene --n-cpu-moe; el modelo A no se podrá repartir GPU/RAM." >&2
fi
COMMON="$COMMON $FA_FLAG $LOAD_FLAG"

echo "Salida en: $OUT"
echo "Binario: $LLAMA_SERVER"
echo "Flags comunes: $COMMON"
used="$(vram_used)"
echo "VRAM en uso antes de empezar: ${used} MiB"
if [ "${used:-0}" -gt 700 ]; then
  echo "AVISO: hay VRAM ocupada (Ollama, otro llama-server, navegador). Ciérralo para un test limpio." >&2
fi

run_model "$TAG_A" "$MODEL_A" "$ARGS_A"
run_model "$TAG_B" "$MODEL_B" "$ARGS_B"

[ -f "$OUT/results.jsonl" ] && python3 "$OUT/summary.py" "$OUT"
echo
echo "Abre los relojes: $OUT/${TAG_A}_reloj.html y $OUT/${TAG_B}_reloj.html"
