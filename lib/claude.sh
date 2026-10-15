# lib/claude.sh — Claude Code (API) + filtro kev/laya, sin modelo grande cargado.
# claude-kev [args de claude]   kev-4b, CUDA por defecto (si la GPU está ocupada o falla: kev-4b en CPU)
# claude-kev-cpu               kev-4b en CPU
# claude-kev-08b               kev-0.8b (más rápido, menos acuerdo)

# Genera el settings de SESIÓN (no toca ~/.claude ni el .claude del proyecto).
_qwen_claude_settings() {
  local dir="${XDG_STATE_HOME:-$HOME/.local/state}/qwen" f
  mkdir -p "$dir"; f="$dir/claude-kev-settings.json"
  LAYA_DIR="$LAYA_DIR" python3 - "$f" <<'PY' || return 1
import json, os, shlex, sys
d = os.environ["LAYA_DIR"]
def cmd(name): return "python3 " + shlex.quote(os.path.join(d, name))
hooks = {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": cmd("laya_hook.py")}]}]}
if os.path.exists(os.path.join(d, "laya_guard.py")):   # fase 2: se activa solo al existir
    hooks["PreToolUse"] = [{"matcher": "Bash", "hooks": [{"type": "command", "command": cmd("laya_guard.py")}]}]
json.dump({"hooks": hooks}, open(sys.argv[1], "w"), indent=2)
PY
  printf '%s' "$f"
}

_qwen_run_claude() {
  command -v claude >/dev/null 2>&1 || { echo "No encuentro 'claude' en el PATH" >&2; return 1; }
  local rc=0 st used _lb="${LAYA_BACKEND:-}" _kd="${KEV_DEVICE:-cuda}" _kd0="${KEV_DEVICE:-}" _kr0="$KEV_RUN"
  used="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -n1)"
  if [ "${used:-0}" -gt 2000 ] 2>/dev/null; then
    echo "aviso: GPU con ${used} MiB en uso (¿qwen cargado?); kev irá a CPU" >&2; _kd=cpu
  fi
  [ -n "${KEV_RUN_LOCK:-}" ] || KEV_RUN="$KEV_RUN_CLAUDE"   # Claude: kev-4b (sin Qwen cargado sobra RAM)
  LAYA_BACKEND=kev; QWEN_LAYA=1; KEV_DEVICE="$_kd"; export LAYA_BACKEND QWEN_LAYA KEV_DEVICE
  if ! _laya_up; then
    if [ "$_kd" = cuda ]; then
      echo "aviso: kev no arrancó en CUDA; reintento en CPU" >&2
      _laya_down; KEV_DEVICE=cpu; export KEV_DEVICE
      _laya_up || echo "aviso: filtro kev no disponible; Claude Code sigue sin filtro" >&2
    else
      echo "aviso: filtro kev no disponible; Claude Code sigue sin filtro" >&2
    fi
  fi
  if st="$(_qwen_claude_settings)" && [ -n "$st" ]; then set -- --settings "$st" "$@"; fi
  claude "$@"; rc=$?
  _laya_down
  LAYA_BACKEND="$_lb"; KEV_RUN="$_kr0"
  if [ -n "$_kd0" ]; then KEV_DEVICE="$_kd0"; else unset KEV_DEVICE; fi
  return "$rc"
}

claude-kev()     { _qwen_run_claude "$@"; }
claude-kev-cpu() { KEV_DEVICE=cpu _qwen_run_claude "$@"; }
claude-kev-08b() { KEV_RUN_LOCK=1 KEV_RUN="$KEV_RUN_FAST" _qwen_run_claude "$@"; }   # kev-0.8b, más rápido
