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
