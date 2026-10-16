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

# ── Caché de HuggingFace (la usan laya/kev/voz vía huggingface_hub) ──
# Ya tiene los pesos descargados en el disco externo (kev-4b, kev-0.8b, sus
# bases Qwen3.5-*-Base, el modelo de laya, Kokoro, etc.). Sin esto, cada
# backend resuelve HF_HOME al default (~/.cache/huggingface) y, si no
# encuentra nada ahí, intenta volver a descargar lo que ya existe.
QWEN_HF_CACHE_DEFAULT="/run/media/xaski/7c0ba586-7758-4419-b3de-f524b9c9a1fb/!models/hf-cache"
if [ -z "${HF_HOME:-}" ] && [ -d "$QWEN_HF_CACHE_DEFAULT" ]; then
  HF_HOME="$QWEN_HF_CACHE_DEFAULT"
fi
[ -n "${HF_HOME:-}" ] && export HF_HOME
unset QWEN_HF_CACHE_DEFAULT

# ── llama.cpp / modelos ──
QWEN_LLAMA_BIN="${QWEN_LLAMA_BIN:-$HOME/llama.cpp/build/bin/llama-server}"
QWEN_MODELS_DIR="${QWEN_MODELS_DIR:-$HOME/models}"
QWEN_PORT="${QWEN_PORT:-8001}"
QWEN_ALIAS="${QWEN_ALIAS:-qwen3.6-35b}"

# Parámetros de llama-server (QWENX_* se conservan por compatibilidad)
QWENX_CTX="${QWENX_CTX:-120000}"
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
LAYA_BACKEND="${LAYA_BACKEND:-}"            # vacío = "backend" de laya/config.json (laya | kev)

# ── Kev (backend alternativo de laya: kev.serve en CPU, no toca VRAM) ──
KEV_DIR="${KEV_DIR:-$QWEN_ROOT/kev/kev-repo}"
KEV_PY="${KEV_PY:-$KEV_DIR/.venv/bin/python}"
KEV_RUN="${KEV_RUN:-jaredpalmer/kev-0.8b}"                 # con Qwen cargado (backend de laya): 0.8b, cabe en RAM
KEV_RUN_CLAUDE="${KEV_RUN_CLAUDE:-jaredpalmer/kev-4b}"      # flujo Claude / sin modelo grande: 4b
KEV_RUN_FAST="${KEV_RUN_FAST:-jaredpalmer/kev-0.8b}"        # claude-kev-08b: más rápido (~48 ms)
KEV_PORT="${KEV_PORT:-8009}"
KEV_TIMEOUT="${KEV_TIMEOUT:-300}"           # la primera vez descarga el modelo
KEV_LOG="${KEV_LOG:-$HOME/.cache/qwenx/kev.log}"

if [ -z "${LAYA_VENV:-}" ]; then
  if [ -x "$LAYA_DIR/.venv/bin/python" ]; then
    LAYA_VENV="$LAYA_DIR/.venv"             # venv ya existente en la repo
  else
    LAYA_VENV="$QWEN_DATA/laya-venv"
  fi
fi

# ── Voz (TTS con piper; opcional, solo lectura en voz alta, sin STT) ──
# Independiente de TTSiro: venv, modelo y puerto propios, sin compartir nada con ese repo.
QWEN_VOZ="${QWEN_VOZ:-0}"                   # opt-in: sin modelo .onnx no tiene sentido arrancarla gratis
VOZ_DIR="${VOZ_DIR:-$QWEN_ROOT/voz}"
VOZ_PORT="${VOZ_PORT:-8778}"
VOZ_SERVER="$VOZ_DIR/voz_server.py"
VOZ_TIMEOUT="${VOZ_TIMEOUT:-30}"
VOZ_MODEL="${VOZ_MODEL:-}"                  # vacío = resuelve por glob en QWEN_MODELS_DIR
VOZ_MODEL_GLOB="${VOZ_MODEL_GLOB:-*.onnx}"
VOZ_VELOCIDAD="${VOZ_VELOCIDAD:-1.0}"       # length_scale de piper
VOZ_RUIDO="${VOZ_RUIDO:-0.667}"             # noise_scale
VOZ_RUIDO_W="${VOZ_RUIDO_W:-0.8}"           # noise_w_scale
VOZ_PAUSA="${VOZ_PAUSA:-0.2}"               # sentence_silence

if [ -z "${VOZ_VENV:-}" ]; then
  if [ -x "$VOZ_DIR/.venv/bin/python" ]; then
    VOZ_VENV="$VOZ_DIR/.venv"               # venv ya existente en la repo
  else
    VOZ_VENV="$QWEN_DATA/voz-venv"
  fi
fi
# Motores extra (perfil con motor kokoro / f5 / s2), cada uno con su venv: se instalan con qwen-voz-motores
VOZ_KOKORO_VENV="${VOZ_KOKORO_VENV:-$QWEN_DATA/voz-kokoro-venv}"
VOZ_F5_VENV="${VOZ_F5_VENV:-$QWEN_DATA/voz-f5-venv}"           # f5-tts + torch (F5-Spanish)
VOZ_FISH_DIR="${VOZ_FISH_DIR:-$QWEN_DATA/fish-speech}"   # clon de fishaudio/fish-speech + .venv (S2 Pro)
VOZ_S2CPP_DIR="${VOZ_S2CPP_DIR:-$QWEN_DATA/s2.cpp}"      # rodrigomatta/s2.cpp compilado (S2 Pro GGUF)
VOZ_KOKORO_PY="$VOZ_KOKORO_VENV/bin/python"
VOZ_F5_PY="$VOZ_F5_VENV/bin/python"
# exportadas: las leen voz_server.py y también web_server.py (la UI de voz funciona con voz apagada)
export VOZ_KOKORO_PY VOZ_F5_PY VOZ_FISH_DIR VOZ_S2CPP_DIR

_voz_model_path() {   # ruta del .onnx: VOZ_MODEL si existe, si no el primer *.onnx en QWEN_MODELS_DIR
  [ -n "${VOZ_MODEL:-}" ] && [ -f "$VOZ_MODEL" ] && { printf '%s\n' "$VOZ_MODEL"; return 0; }
  _qwen_first_glob "$VOZ_MODEL_GLOB"
}

_voz_model_cfg_path() {   # piper necesita el .onnx.json al lado del .onnx
  local m; m="$(_voz_model_path)" || return 1
  [ -f "$m.json" ] && printf '%s\n' "$m.json"
}

# ── Web (UI local para la LAN de casa; arranque manual, sin autenticación) ──
WEB_DIR="${WEB_DIR:-$QWEN_ROOT/web}"
WEB_PORT="${WEB_PORT:-8780}"
WEB_WS_PORT="${WEB_WS_PORT:-8781}"       # WebSocket: adjuntar pi (fase 2)
WEB_SERVER="$WEB_DIR/web_server.py"

if [ -z "${WEB_VENV:-}" ]; then
  if [ -x "$WEB_DIR/.venv/bin/python" ]; then
    WEB_VENV="$WEB_DIR/.venv"             # venv ya existente en la repo
  else
    WEB_VENV="$QWEN_DATA/web-venv"
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

_qwen_model_path() {   # _qwen_model_path base|heretic|iq3|q9b|q4b|q2b|hermes3b
  case "${1:-base}" in
    base)    [ -n "${QWENX_MODEL:-}" ] && [ -f "$QWENX_MODEL" ] && { printf '%s\n' "$QWENX_MODEL"; return 0; }
             _qwen_first_glob 'Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf' '*Q4_K_XL*.gguf' ;;
    heretic) _qwen_first_glob '*35B*heretic*Q4_K_M*.gguf' ;;   # 35B: el 9B también es heretic Q4_K_M
    iq3)     _qwen_first_glob '*IQ3_XXS*.gguf' ;;
    q9b)     _qwen_first_glob '*9B*heretic*Q4_K_M*.gguf' ;;
    q4b)     _qwen_first_glob '*Qwen3.8-4B*Heretic*Q4_K_M*.gguf' ;;
    q2b)     _qwen_first_glob '*2B*Heretic*Q4_K_M*.gguf' ;;
    hermes3b) _qwen_first_glob '*Hermes-3-Llama-3.2-3B*Q4_K_M*.gguf' ;;
    *)       return 1 ;;
  esac
}

# Visión: cada familia usa SU mmproj (mismo criterio que menu/qwen_menu/config.py:MMPROJ).
_qwen_mmproj_path() {   # _qwen_mmproj_path [modelo]
  case "${1:-base}" in
    q4b) _qwen_first_glob 'mmproj-Qwen3.8-4B*.gguf' ;;
    *)   [ -n "${QWENX_MMPROJ:-}" ] && [ -f "$QWENX_MMPROJ" ] && { printf '%s\n' "$QWENX_MMPROJ"; return 0; }
         _qwen_first_glob 'mmproj-*35B*F16*.gguf' ;;
  esac
}
