source ~/.bashrc
QWENX_NOTHINK=1 qwen

con eso se supone que no me tira error 500 


matar llama
pkill -TERM -f '/home/xaski/llama.cpp/build/bin/llama-server'


python3 - <<'PY'
import json, time, urllib.request
url = "http://127.0.0.1:8001/slots"
def active():
    with urllib.request.urlopen(url) as r:
        slots = json.load(r)
    return next((s for s in slots if s.get("is_processing")), None)

try:
    previous = active()
    if not previous:
        print("Esperando una tarea activa...")
        task = None
        tokens = 0
    else:
        task = previous.get("id_task")
        tokens = previous.get("next_token", [{}])[0].get("n_decoded", 0)
        print(f"Midiendo tarea {task}...")

    while True:
        time.sleep(1)
        current = active()

        if not current:
            print("\rSin tareas activas. Esperando...", end="", flush=True)
            task = None
            continue

        new_task = current.get("id_task")
        new_tokens = current.get("next_token", [{}])[0].get("n_decoded", 0)

        if new_task != task:
            task = new_task
            tokens = new_tokens
            print(f"\nMidiendo tarea {task}...")
            continue

        speed = max(0, new_tokens - tokens)
        print(f"\rTarea {task} | Tokens generados: {new_tokens} | Velocidad: {speed} tokens/s   ", end="", flush=True)
        tokens = new_tokens

except KeyboardInterrupt:
    print("\nMonitor cerrado. Qwen sigue funcionando.")
PY



# heretics

# 1) Descargar (el nombre real del archivo será otro; ajústalo en los pasos 3 y 4)
huggingface-cli download llmfan46/Qwen3.6-35B-A3B-uncensored-heretic-Native-MTP-Preserved-GGUF \
  --include "*Q4_K_M*.gguf" --local-dir /home/xaski/models

# 2) Ver el nombre exacto
ls -lh /home/xaski/models/*.gguf

# 3) Prueba directa (cierra antes cualquier qwen/llama-server abierto)
QWENX_MODEL=/home/xaski/models/Qwen3.6-35B-A3B-uncensored-heretic-Native-MTP-Preserved-Q4_K_M.gguf qwen

# 4) Dejarlo fijo en ~/.bashrc
cat >> ~/.bashrc <<'EOF'

# Qwen heretic
qwenh() { QWENX_MODEL="$HOME/models/Qwen3.6-35B-A3B-uncensored-heretic-Native-MTP-Preserved-Q4_K_M.gguf" qwen "$@"; }
EOF
source ~/.bashrc

# 5) Usarlo
qwenh

# 6) Medir VRAM y RAM con el modelo cargado (en otra terminal)
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
qwen-mem
