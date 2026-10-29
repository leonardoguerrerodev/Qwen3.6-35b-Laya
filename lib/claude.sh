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

# System prompt extra de Claude: idioma de respuesta + aviso del filtro System One (kev vía laya).
_qwen_claude_sysprompt() {
  local i; i="$(_qwen_idioma_prompt)"
  printf '%s%s' "${i:+$i }" "Hay un filtro local System One (kev, vía laya) activo: avisa de prompts riesgosos y te pide confirmar ante comandos Bash destructivos. Para una pregunta cerrada barata (sí/no u opciones) puedes consultar: python3 $LAYA_DIR/kev_ask.py \"texto\" -q \"question\" [-o opción]... Es orientativo, nunca la decisión final."
}

# Ventana de Claude en un terminal nuevo, con el settings del filtro (laya_hook + laya_guard).
# Espera a que laya responda (kev arranca antes que laya) y sigue sin filtro pasado KEV_TIMEOUT.
#   QWEN_TERMINAL    emulador (konsole por defecto; kitty/alacritty/xterm sirven; gnome-terminal usa `--`)
#   QWEN_CLAUDE_ENV  variables extra para claude
# _qwen_claude_window  carpeta  [args de claude...]
_qwen_claude_window() {
  local dir="$1"; shift
  local term="${QWEN_TERMINAL:-konsole}" cmd st sp args_q=""
  [ -d "$dir" ] || { echo "No existe la carpeta de Claude: $dir" >&2; return 1; }
  command -v "$term" >/dev/null 2>&1 || { echo "No encuentro el terminal '$term' (QWEN_TERMINAL)" >&2; return 1; }
  command -v claude >/dev/null 2>&1 || { echo "No encuentro el comando 'claude' en el PATH" >&2; return 1; }
  if st="$(_qwen_claude_settings)" && [ -n "$st" ]; then args_q+="$(printf -- '--settings %q ' "$st")"; fi
  sp="$(_qwen_claude_sysprompt)"
  [ -n "$sp" ] && args_q+="$(printf -- '--append-system-prompt %q ' "$sp")"
  [ $# -gt 0 ] && args_q+="$(printf '%q ' "$@")"
  cmd="cd $(printf '%q' "$dir") || exit 1
echo 'esperando al filtro (laya :${LAYA_PORT})…'
_t=\$SECONDS
until (exec 3<>/dev/tcp/127.0.0.1/${LAYA_PORT}) 2>/dev/null || (( SECONDS - _t > ${KEV_TIMEOUT} )); do sleep 0.5; done
${QWEN_CLAUDE_ENV:-} claude ${args_q}
exec bash -i"
  setsid "$term" -e bash -lc "$cmd" >/dev/null 2>&1 &
  disown 2>/dev/null || true
  echo "Claude se abre en otra terminal: $dir"
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
  set -- --append-system-prompt "$(_qwen_claude_sysprompt)" "$@"
  claude "$@"; rc=$?
  _laya_down
  LAYA_BACKEND="$_lb"; KEV_RUN="$_kr0"
  if [ -n "$_kd0" ]; then KEV_DEVICE="$_kd0"; else unset KEV_DEVICE; fi
  return "$rc"
}

claude-kev()     { _qwen_run_claude "$@"; }
claude-kev-cpu() { KEV_DEVICE=cpu _qwen_run_claude "$@"; }
claude-kev-08b() { KEV_RUN_LOCK=1 KEV_RUN="$KEV_RUN_FAST" _qwen_run_claude "$@"; }   # kev-0.8b, más rápido
