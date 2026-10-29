"""Configuración: rutas, puertos, modelos, opciones."""
import json
import os
import re

HOME = os.path.expanduser("~")
MODELS_DIR = os.environ.get("QWEN_MODELS_DIR", os.path.join(HOME, "models"))
LLAMA_PORT = int(os.environ.get("QWEN_PORT") or os.environ.get("QWEN_LLAMA_PORT") or "8001")
LAYA_PORT = int(os.environ.get("LAYA_PORT", "8765"))
KEV_PORT = int(os.environ.get("KEV_PORT", "8009"))
VOZ_PORT = int(os.environ.get("VOZ_PORT", "8778"))
WEB_PORT = int(os.environ.get("WEB_PORT", "8780"))
# Perfiles de voz (los edita web/voz.html; el menú solo cambia cuál está activo con Z)
VOZ_PERFILES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "voz", "perfiles.json")
STATE_FILE = os.path.join(
    os.environ.get("XDG_STATE_HOME", os.path.join(HOME, ".local", "state")),
    "qwen", "menu.json",
)
WIDTH_DEFAULT = 72  # ancho máximo de la caja
MIN_COLS, MIN_ROWS = 30, 6  # mínimo para dibujar (móvil)

# id, etiqueta, descripción, patrones glob (el primero que exista gana)
MODELS = [
    ("base", "Base", "Q4_K_XL · MoE 35B-A3B",
     ["Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf", "*Q4_K_XL*.gguf"]),
    ("heretic", "Heretic", "uncensored Q4_K_M",
     ["*35B*heretic*Q4_K_M*.gguf"]),   # 35B: el 9B también es heretic Q4_K_M
    ("q9b", "Qwen 9B", "Qwen3.8 heretic · denso, entero en GPU",
     ["*9B*heretic*Q4_K_M*.gguf"]),
    ("q4b", "Qwen 4B", "Qwen3.8 heretic distill · liviano, con visión",
     ["*Qwen3.8-4B*Heretic*Q4_K_M*.gguf"]),
]
# Visión: cada familia necesita SU mmproj (el del 35B no sirve con otros modelos).
MMPROJ = {"q4b": "mmproj-Qwen3.8-4B*.gguf"}   # el resto: el del 35B
MMPROJ_DEFAULT = "mmproj-*35B*F16*.gguf"
NO_VISION = ("q9b",)

# ── Modelos propios: los gestiona `qwen-model` y viven fuera de la repo ──
# JSON = lista de {id, label, desc, pattern, mmproj}. Se añaden AL FINAL de MODELS
# (el menú recuerda el modelo por posición: no reordenar los de arriba). Sin mmproj → sin visión.
BUILTIN_IDS = tuple(m[0] for m in MODELS)
QWEN_DATA = os.environ.get("QWEN_DATA", os.path.join(HOME, ".local", "share", "qwen"))
CUSTOM_MODELS_FILE = os.path.join(QWEN_DATA, "models.json")


def _load_custom_models():
    global NO_VISION
    try:
        with open(CUSTOM_MODELS_FILE, encoding="utf-8") as f:
            items = json.load(f)
    except (OSError, ValueError):
        return
    if not isinstance(items, list):
        return
    for it in items:
        try:
            mid, label, pat = str(it["id"]), str(it["label"]), str(it["pattern"])
        except (KeyError, TypeError):
            continue
        # MODEL_ID se imprime sin comillas hacia el shell: solo ids seguros; «none» está reservado
        if (not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", mid) or mid == "none"
                or any(m[0] == mid for m in MODELS)):
            continue
        MODELS.append((mid, label, str(it.get("desc", "")), [pat]))
        if it.get("mmproj"):
            MMPROJ[mid] = str(it["mmproj"])
        else:
            NO_VISION = NO_VISION + (mid,)


_load_custom_models()

# clave, tecla, etiqueta, descripción
OPTIONS = [
    ("edit", "e", "Edición", "write · edit · bash"),
    ("vision", "v", "Visión", "mmproj F16"),
    ("incognito", "i", "Incógnito", "sin guardar sesión"),
    ("ollama", "o", "Ollama", "respaldo · ignora el modelo grande"),
    ("laya", "s", "Laya", "system 1 · clasifica prompts en CPU"),
    ("kev", "y", "Kev", "backend de laya: kev en vez del checkpoint"),
    ("kevgpu", "g", "Kev GPU", "kev en CUDA en vez de CPU · con cualquier modelo o «Ninguno»"),
    ("claude", "h", "Claude", "abre Claude Code con kev de filtro (System One) · con cualquier modelo"),
    ("voz", "z", "Voz", "TTS piper/kokoro/f5/s2 · Pi responde con etiquetas de voz"),
]

# Parámetros de lanzamiento de llama-server: clave, tecla, etiqueta, valores, por defecto, descripción
PARAMS = [
    ("ctx", "t", "Contexto", ("auto", "8192", "16384", "32768", "65536", "100000", "120000"), "auto",
     "tokens · auto: 120k"),
    ("temp", "T", "Temp.", ("0.2", "0.4", "0.6", "0.8", "1.0", "1.2"), "0.6",
     "más alta = más creativa"),
    ("kev", "K", "Kev", ("auto", "0.8b", "4b"), "auto",
     "tamaño de kev · auto: 4b sin modelo grande, 0.8b con modelo (cabe en RAM/VRAM)"),
    ("idioma", "L", "Idioma", ("auto", "español", "inglés"), "auto",
     "de la respuesta (Pi y Claude) · auto: el de tu mensaje · la voz va aparte"),
]
# «auto» por modelo (id → ctx). Ausente = QWENX_CTX del shell (120k: los Qwen, de atención
# híbrida, aguantan con poco KV). Un modelo denso que no lo aguante se añade aquí.
CTX_AUTO = {}

# Opciones activadas por defecto la primera vez
DEFAULT_ON = ("edit", "laya")

WARN_EDIT = "! Pi podrá escribir y ejecutar bash: solo en proyectos de confianza"
