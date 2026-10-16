"""Configuración: rutas, puertos, modelos, opciones."""
import os

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
    ("iq3", "IQ3", "ligero IQ3_XXS",
     ["*IQ3_XXS*.gguf"]),
    ("q9b", "Qwen 9B", "Qwen3.8 heretic · denso, entero en GPU",
     ["*9B*heretic*Q4_K_M*.gguf"]),
    ("q4b", "Qwen 4B", "Qwen3.8 heretic distill · liviano, con visión",
     ["*Qwen3.8-4B*Heretic*Q4_K_M*.gguf"]),
    ("q2b", "Qwen 2B", "Qwen3.5 heretic distill · mínimo",
     ["*2B*Heretic*Q4_K_M*.gguf"]),
    ("hermes3b", "Hermes 3B", "Llama 3.2 abliterado · chat/rol, sin visión",
     ["*Hermes-3-Llama-3.2-3B*Q4_K_M*.gguf"]),
]
# Visión: cada familia necesita SU mmproj (el del 35B no sirve con otros modelos).
MMPROJ = {"q4b": "mmproj-Qwen3.8-4B*.gguf"}   # el resto: el del 35B
MMPROJ_DEFAULT = "mmproj-*35B*F16*.gguf"
NO_VISION = ("q9b", "q2b", "hermes3b")

# clave, tecla, etiqueta, descripción
OPTIONS = [
    ("edit", "e", "Edición", "write · edit · bash"),
    ("vision", "v", "Visión", "mmproj F16"),
    ("incognito", "i", "Incógnito", "sin guardar sesión"),
    ("ollama", "o", "Ollama", "respaldo · ignora el modelo"),
    ("laya", "s", "Laya", "system 1 · clasifica prompts en CPU"),
    ("kev", "y", "Kev", "backend de laya: kev-0.8b (con Qwen)"),
    ("kevgpu", "g", "Kev GPU", "kev-4b en CUDA · solo o con Claude · «Ninguno»"),
    ("claude", "h", "Claude", "Claude Code + kev-4b · CPU, o CUDA + Kev GPU"),
    ("voz", "z", "Voz", "TTS piper/kokoro/f5/s2 · Pi responde con etiquetas de voz"),
]

# Parámetros de lanzamiento de llama-server: clave, tecla, etiqueta, valores, por defecto, descripción
PARAMS = [
    ("ctx", "t", "Contexto", ("auto", "8192", "16384", "32768", "65536", "120000"), "auto",
     "tokens · auto: 120k Qwen, 32k Hermes"),
    ("temp", "T", "Temp.", ("0.2", "0.4", "0.6", "0.8", "1.0", "1.2"), "0.6",
     "más alta = más creativa"),
    ("idioma", "L", "Idioma", ("auto", "español", "inglés"), "auto",
     "de la respuesta (Pi y Claude) · auto: el de tu mensaje · la voz va aparte"),
]
# «auto» por modelo. Los Qwen (atención híbrida) aguantan 120k con poco KV; un Llama denso
# a 120k pide ~7 GB de VRAM solo de KV (Hermes no cargaba). Ausente = QWENX_CTX del shell.
CTX_AUTO = {"hermes3b": "32768"}

# Opciones activadas por defecto la primera vez
DEFAULT_ON = ("edit", "laya")

WARN_EDIT = "! Pi podrá escribir y ejecutar bash: solo en proyectos de confianza"
