"""Configuración: rutas, puertos, modelos, opciones."""
import os

HOME = os.path.expanduser("~")
MODELS_DIR = os.environ.get("QWEN_MODELS_DIR", os.path.join(HOME, "models"))
LLAMA_PORT = int(os.environ.get("QWEN_PORT") or os.environ.get("QWEN_LLAMA_PORT") or "8001")
LAYA_PORT = int(os.environ.get("LAYA_PORT", "8765"))
KEV_PORT = int(os.environ.get("KEV_PORT", "8009"))
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
     ["*heretic*Q4_K_M*.gguf"]),
    ("iq3", "IQ3", "ligero IQ3_XXS",
     ["*IQ3_XXS*.gguf"]),
]

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
]

# Opciones activadas por defecto la primera vez
DEFAULT_ON = ("edit", "laya")

WARN_EDIT = "! Pi podrá escribir y ejecutar bash: solo en proyectos de confianza"
