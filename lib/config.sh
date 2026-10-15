# lib/config.sh — rutas, puertos, valores por defecto y resolución de modelos.
# Se carga con `source` desde qwen-local.sh. No ejecuta nada ni arranca procesos.
# Todo es sobreescribible por variables de entorno.

# ── Raíz de la repo (la define qwen-local.sh; este fallback resuelve symlinks) ──
if [ -z "${QWEN_ROOT:-}" ]; then
  QWEN_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
fi
export QWEN_ROOT

# ── Datos de usuario (venvs y estado: fuera de la repo) ──
QWEN_DATA="${QWEN_DATA:-$HOME/.local/share/qwen}"

# ── llama.cpp / modelos ──
QWEN_LLAMA_BIN="${QWEN_LLAMA_BIN:-$HOME/llama.cpp/build/bin/llama-server}"
QWEN_MODELS_DIR="${QWEN_MODELS_DIR:-$HOME/models}"
QWEN_PORT="${QWEN_PORT:-8001}"
QWEN_ALIAS="${QWEN_ALIAS:-qwen3.6-35b}"

# Parámetros de llama-server (QWENX_* se conservan por compatibilidad)
QWENX_CTX="${QWENX_CTX:-100000}"
QWENX_NCMOE="${QWENX_NCMOE:-28}"
QWENX_BATCH="${QWENX_BATCH:-2048}"
QWENX_UB="${QWENX_UB:-512}"
QWENX_CRAM="${QWENX_CRAM:-2048}"
QWENX_LOADMODE="${QWENX_LOADMODE:-none}"
QWENX_READY_TIMEOUT="${QWENX_READY_TIMEOUT:-900}"

# ── Pi ──
QWEN_PI_DIR="${QWEN_PI_DIR:-$HOME/.pi-qwen/agent}"
QWEN_PI_PROVIDER="${QWEN_PI_PROVIDER:-qwen-local}"
QWEN_PI_TOOLS_RO="${QWEN_PI_TOOLS_RO:-read,grep,find,ls}"
QWEN_PI_TOOLS_EDIT="${QWEN_PI_TOOLS_EDIT:-read,write,edit,bash,grep,find,ls}"

# ── Ollama (respaldo) ──
QWEN_OLLAMA_URL="${QWEN_OLLAMA_URL:-http://127.0.0.1:11434}"
QWEN_OLLAMA_MODEL="${QWEN_OLLAMA_MODEL:-qwen3.6:35b}"
QWEN_OLLAMA_CTX="${QWEN_OLLAMA_CTX:-32768}"

# ── Laya (clasificador de prompts en CPU) ──
QWEN_LAYA="${QWEN_LAYA:-1}"                 # 0 = no arrancar laya
LAYA_DIR="${LAYA_DIR:-$QWEN_ROOT/laya}"
LAYA_PORT="${LAYA_PORT:-8765}"
LAYA_MODEL="${LAYA_MODEL:-}"                # vacío = usa "model" de laya/config.json
LAYA_SERVER="$LAYA_DIR/laya_server.py"
LAYA_TIMEOUT="${LAYA_TIMEOUT:-30}"
if [ -z "${LAYA_VENV:-}" ]; then
  if [ -x "$LAYA_DIR/.venv/bin/python" ]; then
    LAYA_VENV="$LAYA_DIR/.venv"             # venv ya existente en la repo
  else
    LAYA_VENV="$QWEN_DATA/laya-venv"
  fi
fi

# ── Menú ──
QWEN_MENU="${QWEN_MENU:-$QWEN_ROOT/menu/qwen-menu.py}"

# ── Modelos: id → archivo ──
# Los patrones glob coinciden con los de menu/qwen-menu.py.
_qwen_first_glob() {   # _qwen_first_glob patrón...  → imprime el primer archivo existente
  local pat f
  for pat in "$@"; do
    for f in "$QWEN_MODELS_DIR"/$pat; do
      [ -f "$f" ] && { printf '%s\n' "$f"; return 0; }
    done
  done
  return 1
}

_qwen_model_path() {   # _qwen_model_path base|heretic|iq3
  case "${1:-base}" in
    base)    [ -n "${QWENX_MODEL:-}" ] && [ -f "$QWENX_MODEL" ] && { printf '%s\n' "$QWENX_MODEL"; return 0; }
             _qwen_first_glob 'Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf' '*Q4_K_XL*.gguf' ;;
    heretic) _qwen_first_glob '*heretic*Q4_K_M*.gguf' ;;
    iq3)     _qwen_first_glob '*IQ3_XXS*.gguf' ;;
    *)       return 1 ;;
  esac
}

_qwen_mmproj_path() {
  [ -n "${QWENX_MMPROJ:-}" ] && [ -f "$QWENX_MMPROJ" ] && { printf '%s\n' "$QWENX_MMPROJ"; return 0; }
  _qwen_first_glob 'mmproj-*F16*.gguf'
}
