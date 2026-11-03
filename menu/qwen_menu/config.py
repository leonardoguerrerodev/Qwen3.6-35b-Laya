"""Configuración: rutas, puertos, modelos, opciones."""
import json
import os
import re

HOME = os.path.expanduser("~")

# Marca del menú (se puede cambiar con QWEN_MENU_TITLE / QWEN_MENU_TAGLINE)
APP_NAME = os.environ.get("QWEN_MENU_TITLE", "SiroAI-Local")
APP_TAGLINE = os.environ.get("QWEN_MENU_TAGLINE", "modelos locales con llama.cpp")
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
    ("base", "Base", "Qwen3.6 · 35B-A3B · MoE",
     ["Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf", "*Q4_K_XL*.gguf"]),
    ("heretic", "Heretic", "Qwen3.6 · 35B-A3B · MoE · sin censura",
     ["*35B*heretic*Q4_K_M*.gguf"]),   # 35B: el 9B también es heretic Q4_K_M
    ("q9b", "Qwen 9B", "Qwen3.8 · 9B · sin censura · en GPU",
     ["*9B*heretic*Q4_K_M*.gguf"]),
    ("q4b", "Qwen 4B", "Qwen3.8 · 4B · sin censura · visión",
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
CHAT_MODELS = set()   # ids con "modo": "chat" en models.json: al elegirlos el menú activa Chat solo
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
        if it.get("modo") == "chat":
            CHAT_MODELS.add(mid)
        if it.get("mmproj"):
            MMPROJ[mid] = str(it["mmproj"])
        else:
            NO_VISION = NO_VISION + (mid,)


_load_custom_models()

# clave, tecla, etiqueta, descripción
OPTIONS = [
    ("edit", "e", "Edición", "escribe archivos y ejecuta comandos"),
    ("vision", "v", "Visión", "entiende imágenes"),
    ("incognito", "i", "Incógnito", "no guarda la sesión"),
    ("chat", "f", "Chat", "conversación libre · sin herramientas · incógnito"),
    ("ollama", "o", "Ollama", "usa Ollama en vez de llama.cpp (respaldo)"),
    ("laya", "s", "Laya", "clasifica cada mensaje antes del modelo (CPU)"),
    ("kev", "y", "Kev", "laya usa Kev como clasificador"),
    ("kevgpu", "g", "Kev GPU", "Kev en la GPU (CUDA) en vez de la CPU"),
    ("claude", "h", "Claude", "abre Claude Code filtrado por Kev"),
    ("voz", "z", "Voz", "respuestas habladas (TTS) con etiquetas de voz"),
]

# Parámetros de lanzamiento de llama-server: clave, tecla, etiqueta, valores, por defecto, descripción
PARAMS = [
    ("ctx", "t", "Contexto", ("auto", "8192", "16384", "32768", "65536", "85000", "100000", "120000"), "auto",
     "tokens · auto: 120k"),
    ("temp", "T", "Temp.", ("0.2", "0.4", "0.6", "0.8", "1.0", "1.2"), "0.6",
     "más alta = más creativa"),
    ("harness", "H", "Agente", ("pi", "qwen-code"), "pi",
     "con qué se usa el modelo: pi o qwen-code"),
    ("kev", "K", "Kev", ("auto", "0.8b", "4b"), "auto",
     "auto elige 4b sin modelo y 0.8b con modelo"),
    ("idioma", "L", "Idioma", ("auto", "español", "inglés"), "auto",
     "de las respuestas · auto sigue tu idioma"),
    ("kvq", "C", "KV cache", ("auto", "f16", "q8_0", "q4_0"), "auto",
     "cuantización del KV · auto: q8_0 (DarkForest: q4_0) · f16 = sin cuantizar"),
]
# «auto» por modelo (id → ctx). Ausente = QWENX_CTX del shell (120k: los Qwen, de atención
# híbrida, aguantan con poco KV). Un modelo denso que no lo aguante se añade aquí.
CTX_AUTO = {"q27h": "32768", "8": "8192"}   # 27B de 10 GB: con 32k de KV q8 (~1 GB) cabe entero en los 12 GB

KV_AUTO = {"8": "q4_0"}   # KV por modelo (id → tipo); ausente = QWENX_KV del shell (q8_0)

# Opciones activadas por defecto la primera vez
DEFAULT_ON = ("edit", "laya")

WARN_EDIT = "! Escribe y ejecuta comandos: solo en proyectos de confianza"
