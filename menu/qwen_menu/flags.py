"""Comando de llama-server: vista previa (la arma lib/llama.sh, no una copia), catálogo de flags y portapapeles."""
import os
import re
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LLAMA_BIN = os.environ.get("QWEN_LLAMA_BIN", os.path.expanduser("~/llama.cpp/build/bin/llama-server"))

# Mismo armado que al lanzar: _qwenx_with_menu mapea P_* → QWENX_* y _qwenx_cmd arma QWENX_CMD.
_SH = '. "$1/lib/config.sh" && . "$1/lib/llama.sh" && _qwenx_with_menu _qwenx_cmd && printf "%s\\0" "${QWENX_CMD[@]}"'


def build_cmd(menu_vars):
    """(palabras, aviso) del comando que lanzaría lib/llama.sh con las variables del menú; error → ([], texto)."""
    try:
        r = subprocess.run(["bash", "-c", _SH, "_", ROOT], env={**os.environ, **menu_vars},
                           capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        return [], str(e)
    err = r.stderr.decode("utf-8", "replace").strip().splitlines()
    if r.returncode:
        return [], err[-1] if err else f"lib/llama.sh salió con {r.returncode}"
    return r.stdout.decode("utf-8", "replace").split("\0")[:-1], (err[-1] if err else "")


def is_flag(w):
    return bool(re.match(r"--?[A-Za-z]", w))


def groups(words):
    """[binario, '-flag valor…', …]: cada flag con sus valores, para mostrar o editar uno por línea."""
    out = []
    for w in words:
        if out and not is_flag(w) and len(out) > 1:
            out[-1].append(w)
        else:
            out.append([w])
    return out


def copy(text):
    """Al portapapeles (wl-copy en Wayland, xclip en X11). Devuelve el programa usado o ''."""
    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text.encode(), timeout=5, check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return cmd[0]
            except (OSError, subprocess.SubprocessError):
                pass
    return ""


# ── catálogo: llama-server --help ──
_CAT = None


def catalog():
    """[(sección, [alias], uso, descripción en inglés)] leído del propio binario: siempre al día con el build."""
    global _CAT
    if _CAT is not None:
        return _CAT
    try:
        txt = subprocess.run([LLAMA_BIN, "--help"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        txt = ""
    _CAT, sec = [], ""
    for ln in txt.splitlines():
        m = re.match(r"-{5} (.+?) -{5}", ln)
        if m:
            sec = m.group(1)
        elif ln.startswith("-"):
            # nombres en las columnas 0-39 y descripción desde la 40; si los nombres no caben, todo es nombre
            names, desc = (ln[:40].strip(), ln[40:].strip()) if ln[38:40] == "  " else (ln.strip(), "")
            alias = [p.split()[0] for p in names.split(",") if p.strip().startswith("-")]
            _CAT.append([sec, alias, names, desc])
        elif ln.startswith(" " * 20) and _CAT and not ln.strip().startswith("(env:"):
            _CAT[-1][3] = (_CAT[-1][3] + " " + ln.strip()).strip()
    _CAT = [tuple(x) for x in _CAT]
    return _CAT


def es(alias):
    """Explicación corta en español, si la hay (los flags que importan en este proyecto)."""
    return next((ES[a] for a in alias if a in ES), "")


ES = {
    # modelo y memoria
    "-m": "ruta del .gguf a cargar",
    "-c": "tamaño del contexto en tokens (lo que el modelo «recuerda»); más contexto = más VRAM para el KV",
    "-ngl": "capas del modelo en la GPU; 99 = todas, auto = que --fit reparta GPU/RAM",
    "-ncmoe": "deja en la CPU/RAM los expertos MoE de las primeras N capas: así el 35B-A3B cabe en 12 GB",
    "-cmoe": "todos los expertos MoE en la CPU (lo más lento, lo que menos VRAM usa)",
    "-ot": "decide a mano en qué dispositivo va cada tensor (patrón=buffer); avanzado, choca con --fit",
    "-fit": "ajusta solo los parámetros no fijados para que quepan en la memoria del dispositivo",
    "-fitc": "contexto mínimo que --fit puede elegir al ajustar",
    "-lm": "cómo cargar el modelo: none/mmap/mlock (mlock lo fija en RAM, sin swap)",
    "-b": "batch lógico: tokens del prompt procesados por paso; más grande = prefill más rápido y más memoria",
    "-ub": "batch físico (micro-batch) que va a la GPU; 256-512 suele ser el punto dulce en 12 GB",
    "-fa": "Flash Attention: menos memoria y más velocidad en atención; necesario para cuantizar el KV",
    "-ctk": "tipo del KV cache (K): f16 sin pérdida, q8_0 casi igual y la mitad, q4_0 un cuarto",
    "-ctv": "tipo del KV cache (V); igual que -ctk",
    "-kvo": "KV cache en la GPU (por defecto); --no-kv-offload lo deja en RAM, más lento",
    "-cram": "MiB de RAM para caché de prompts (reusar conversaciones); -1 sin límite, 0 apagada",
    "-kvu": "un solo KV compartido entre todos los slots (con -np >1)",
    "-np": "slots (peticiones a la vez); 1 = todo el contexto para una sola conversación, lo que pide MTP",
    "-cb": "batching continuo entre slots (por defecto activo)",
    "--swa-full": "KV completo para capas de ventana deslizante (Gemma): más memoria, sin recomputar",
    "--context-shift": "al llenar el contexto descarta lo viejo en vez de cortar (puede degradar)",
    "--cache-reuse": "reusa trozos del KV por desplazamiento cuando el prompt cambia poco",
    "--no-warmup": "salta la pasada de calentamiento al cargar (arranca antes)",
    "-t": "hilos de CPU para generar (afecta mucho a los expertos MoE en RAM)",
    "-tb": "hilos de CPU para procesar el prompt",
    "--numa": "optimizaciones para máquinas con varios nodos NUMA",
    "-dev": "qué GPU(s) usar",
    "-sm": "cómo repartir entre varias GPU",
    "-ts": "proporción por GPU al repartir",
    # visión
    "-mm": "proyector de visión (mmproj) para que el modelo entienda imágenes",
    "--mmproj-offload": "proyector de visión en la GPU; --no-mmproj-offload lo deja en CPU y ahorra VRAM",
    "--image-max-tokens": "tokens máximos por imagen (más = más detalle y más contexto gastado)",
    # muestreo
    "--temp": "temperatura: 0 determinista, 0.6 código, 1.0+ creativo",
    "--top-k": "solo elige entre los K tokens más probables (0 = sin límite)",
    "--top-p": "solo elige dentro del P de probabilidad acumulada",
    "--min-p": "descarta tokens con probabilidad < min-p × la del mejor",
    "--repeat-penalty": "castiga repetir tokens recientes (1.0 = nada)",
    "--presence-penalty": "castiga tokens ya aparecidos: empuja a temas nuevos (Qwen recomienda 0-1.5)",
    "--frequency-penalty": "castiga según cuántas veces apareció un token",
    "--dry-multiplier": "DRY: castiga repetir secuencias largas (anti-bucles); 0 = apagado",
    "--xtc-probability": "XTC: a veces quita los tokens más obvios (más creatividad)",
    "-s": "semilla del azar (-1 = aleatoria); fija para repetir resultados",
    "-n": "tokens máximos a generar por respuesta (-1 = sin límite)",
    "--samplers": "orden de los muestreadores",
    "-j": "fuerza la salida a cumplir un JSON schema",
    "--grammar": "fuerza la salida a una gramática GBNF",
    # especulativo / MTP
    "--spec-type": "tipo de decodificación especulativa; draft-mtp usa la cabeza MTP del propio GGUF",
    "--spec-draft-n-max": "tokens que propone el borrador por paso (MTP: 2-4 es el rango útil)",
    "--spec-draft-n-min": "mínimo de tokens del borrador para intentar especular",
    "--spec-draft-p-min": "confianza mínima del borrador para seguir proponiendo (0.6-0.75 ayuda en GPUs modestas)",
    "--spec-draft-p-split": "probabilidad para abrir ramas en el borrador",
    "--spec-draft-sampling": "greedy (rápido) o probabilistic (respeta la temperatura)",
    "-md": "modelo borrador aparte (otro .gguf pequeño) para especular",
    "-ngld": "capas del modelo borrador en la GPU",
    "-ctkd": "tipo del KV del borrador (K)",
    "-ctvd": "tipo del KV del borrador (V)",
    # plantilla y razonamiento
    "--jinja": "usa la plantilla de chat del GGUF (necesario para herramientas y razonamiento)",
    "--chat-template": "plantilla de chat a mano (nombre o jinja)",
    "--chat-template-file": "plantilla de chat desde un archivo",
    "--chat-template-kwargs": "variables extra para la plantilla, en JSON: '{\"enable_thinking\":false}'",
    "-rea": "razonamiento on/off/auto; off = responde sin pensar (más rápido)",
    "--reasoning-effort": "nivel de razonamiento que se le pasa a la plantilla (Qwen3.8 GSQ: low/medium/xhigh)",
    "--reasoning-budget": "tope de tokens para pensar: -1 sin tope, 0 corta de inmediato",
    "--reasoning-budget-message": "texto que se inyecta al agotar el presupuesto de razonamiento",
    "--reasoning-format": "dónde va el pensamiento: reasoning_content (deepseek) o en el texto (none)",
    "--reasoning-preserve": "conserva el razonamiento previo en el historial",
    "--prefill-assistant": "si el último mensaje es del asistente, continúa desde ahí",
    # servidor
    "-a": "nombre del modelo que ve la API (Pi lo usa como id)",
    "--host": "dirección donde escucha; 127.0.0.1 = solo esta máquina",
    "--port": "puerto de la API (Pi, laya y la web se conectan al 8001)",
    "--api-key": "exige una clave en cada petición",
    "-to": "timeout de lectura/escritura del servidor, en segundos",
    "--metrics": "expone /metrics (Prometheus)",
    "--slots": "expone /slots con el estado de cada slot",
    "--ui": "interfaz web propia de llama-server en el puerto",
    "--sleep-idle-seconds": "descarga el modelo tras N segundos sin uso",
    "--log-file": "guarda el log en un archivo",
    "-v": "log detallado",
    "--lora": "aplica un adaptador LoRA",
}
