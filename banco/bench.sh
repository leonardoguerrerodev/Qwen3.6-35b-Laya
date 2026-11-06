#!/usr/bin/env bash
# bench.sh TAG GGUF CTX KV UB [DRAFT] — llama-server con MTP como el launcher; mide tok/s, aceptación MTP, contexto lleno y VRAM.
# Ej.: ./bench.sh q38-48k ~/models/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-mtp.gguf 49152 q4_0 256 2   (EXTRA="-flags" opcional)
# Probar siempre con el contexto lleno: que cargue no garantiza que aguante.
S="$(dirname "$0")/salida"; mkdir -p "$S"; [ -s "$S/texto.txt" ] || "$(dirname "$0")/perplejidad.sh" --solo-texto; TAG=$1 GGUF=$2 CTX=$3 KV=$4 UB=$5 DR=${6:-2}
B=~/llama.cpp/build/bin/llama-server; PORT=8077
$B -m "$GGUF" --host 127.0.0.1 --port $PORT -ngl 99 -c $CTX -b 2048 -ub $UB \
  -fa on -ctk $KV -ctv $KV --load-mode none --jinja --temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.0 \
  --spec-type draft-mtp --spec-draft-n-max $DR -np 1 -cram 2048 $EXTRA > "$S/srv-$TAG.log" 2>&1 &
PID=$!
for i in $(seq 300); do curl -sf localhost:$PORT/health >/dev/null && break; kill -0 $PID 2>/dev/null || { echo "$TAG: NO CARGA"; grep -m2 ' E ' "$S/srv-$TAG.log"; exit 1; }; sleep 0.5; done
for p in "Escribe en Python una función que valide un RUT chileno, con docstring y 3 tests con assert." \
         "Explica en español, en cuatro párrafos, por qué una joya de plata 950 se oxida y cómo cuidarla."; do
  curl -s localhost:$PORT/v1/chat/completions -H 'Content-Type: application/json' -d "$(python3 -c '
import json,sys;print(json.dumps({"messages":[{"role":"user","content":sys.argv[1]}],"max_tokens":600,"seed":42,"chat_template_kwargs":{"enable_thinking":False}}))' "$p")" \
  | python3 -c "import json,sys;t=json.load(sys.stdin)['timings'];print('%.1f tok/s  acept=%s/%s  n=%s'%(t['predicted_per_second'],t.get('draft_n_accepted',0),t.get('draft_n',0),t['predicted_n']))"
done 2>&1 | sed "s/^/$TAG: /" | grep -v Traceback
python3 -c "
import json;t=open('$S/texto.txt').read()*4
print(json.dumps({'messages':[{'role':'user','content':t[:int(($CTX-800)*3.3)]+'\n\nResume lo anterior en una frase.'}],'max_tokens':40,'chat_template_kwargs':{'enable_thinking':False}}))" > "$S/largo.json"
curl -s localhost:$PORT/v1/chat/completions -H 'Content-Type: application/json' -d @"$S/largo.json" \
  | python3 -c "import json,sys;d=json.load(sys.stdin);t=d.get('timings');print('LLENO: ' + ('%d tok prompt a %.0f tok/s, gen %.1f tok/s'%(t['prompt_n'],t['prompt_per_second'],t['predicted_per_second']) if t else str(d)[:200]))" 2>&1 | sed "s/^/$TAG: /" | tail -1
kill -0 $PID 2>/dev/null || echo "$TAG: SERVIDOR MURIÓ"
echo "$TAG: VRAM $(nvidia-smi --query-gpu=memory.used --format=csv,noheader)"
kill $PID 2>/dev/null; wait $PID 2>/dev/null
