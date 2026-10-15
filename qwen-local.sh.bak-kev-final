# qwen-local.sh — punto de entrada: Qwen3.6-35B-A3B local con Pi + llama.cpp + laya.
# Se carga desde ~/.bashrc a través del symlink ~/.qwen-local.sh → este archivo.
# Para bash interactivo. No usa `set -e` (se hace `source`, no debe afectar tu shell).
#
# Comandos (sin argumentos abren el menú; con argumentos lanzan directo y pasan todo a pi):
#   qwen / qwen-edit / qwen-incognito / qwen-edit-incognito / qwen-vision / qwen-vision-incognito
#   qwenh …  (mismas variantes con el modelo heretic uncensored)
#   qwen-lite   (IQ3_XXS)     qwen-ollama (respaldo)     qwen-mem   qwen-status

# ── Raíz de la repo (resuelve el symlink) ──
_qwen_self="$(readlink -f "${BASH_SOURCE[0]}")"
QWEN_ROOT="$(cd "$(dirname "$_qwen_self")" && pwd)"
export QWEN_ROOT
unset _qwen_self

for _qwen_mod in config laya llama pi claude; do
  if [ -f "$QWEN_ROOT/lib/$_qwen_mod.sh" ]; then
    # shellcheck source=/dev/null
    . "$QWEN_ROOT/lib/$_qwen_mod.sh"
  else
    echo "qwen-local: falta $QWEN_ROOT/lib/$_qwen_mod.sh" >&2
    return 1 2>/dev/null || exit 1
  fi
done
unset _qwen_mod

# ── Estado ──
qwen-status() {
  local id p
  echo "== Estado de Qwen + Pi =="
  echo "repo:          $QWEN_ROOT"
  if command -v pi >/dev/null 2>&1; then echo "pi:            $(command -v pi)"; else echo "pi:            NO encontrado en PATH"; fi
  [ -x "$QWEN_LLAMA_BIN" ] && echo "llama-server:  $QWEN_LLAMA_BIN" || echo "llama-server:  NO encontrado ($QWEN_LLAMA_BIN)"
  for id in base heretic iq3; do
    if p="$(_qwen_model_path "$id")"; then printf 'modelo %-7s %s\n' "$id:" "$p"; else printf 'modelo %-7s no encontrado\n' "$id:"; fi
  done
  if p="$(_qwen_mmproj_path)"; then echo "mmproj:        $p"; else echo "mmproj:        no encontrado"; fi
  _qwen_port_open "$QWEN_PORT" && echo "puerto $QWEN_PORT:   ocupado" || echo "puerto $QWEN_PORT:   libre"
  if [ -f "$LAYA_SERVER" ]; then
    [ -x "$LAYA_VENV/bin/python" ] && echo "laya:          $LAYA_SERVER (venv OK)" || echo "laya:          $LAYA_SERVER (venv se creará al arrancar)"
  else
    echo "laya:          NO encontrado ($LAYA_SERVER)"
  fi
  _laya_port_open && echo "puerto $LAYA_PORT:   laya activo" || echo "puerto $LAYA_PORT:   libre"
  if [ -x "$KEV_PY" ]; then echo "kev:           $KEV_RUN (venv OK; backend de laya: $(_laya_backend))"; else echo "kev:           venv NO encontrado ($KEV_PY)"; fi
  _kev_port_open && echo "puerto $KEV_PORT:   kev activo" || echo "puerto $KEV_PORT:   libre"
  for p in models.json settings.json; do
    if [ -f "$QWEN_PI_DIR/$p" ]; then
      python3 -m json.tool "$QWEN_PI_DIR/$p" >/dev/null 2>&1 && echo "pi/$p: JSON OK" || echo "pi/$p: ERROR de JSON"
    else
      echo "pi/$p: no existe (se crea al lanzar o con el instalador)"
    fi
  done
}

# ── Lanzamiento directo (sin menú) ──
# _qwen_launch  modelo(base|heretic|iq3)  edit  vision  incognito  ollama  -- args de pi...
_qwen_launch() {
  local model="$1" edit="$2" vision="$3" incog="$4" ollama="$5"; shift 5
  local profile=readonly mmproj="" path=""
  [ "$edit" = 1 ] && profile=edit
  [ "$incog" = 1 ] && export QWEN_PI_NO_SESSION=1 || export QWEN_PI_NO_SESSION=0

  if [ "$ollama" = 1 ]; then
    _qwen_run_ollama "$profile" "$@"; return $?
  fi
  path="$(_qwen_model_path "$model")" || { echo "No encuentro el modelo '$model' en $QWEN_MODELS_DIR" >&2; return 1; }
  if [ "$vision" = 1 ]; then
    mmproj="$(_qwen_mmproj_path)" || { echo "No encuentro mmproj-*F16*.gguf en $QWEN_MODELS_DIR" >&2; return 1; }
  fi
  QWENX_MODEL="$path" QWENX_MMPROJ="$mmproj" _qwen_run_local "$profile" "$@"
}

# ── Menú TUI ──
_qwen_menu() {
  command -v python3 >/dev/null 2>&1 || { echo "Falta python3" >&2; return 1; }
  [ -f "$QWEN_MENU" ] || { echo "No encuentro el menú: $QWEN_MENU" >&2; return 1; }

  local out ACTION MODEL_ID MODEL_PATH OPT_EDIT OPT_VISION OPT_INCOGNITO OPT_OLLAMA OPT_LAYA OPT_KEV OPT_NOMODEL OPT_CLAUDE OPT_KEVGPU MMPROJ_PATH PI_ARGS _lb_prev rc=0
  local monitor=0
  [[ $- == *m* ]] && monitor=1
  set +m   # evita avisos de jobs de bash mientras llama-server corre en segundo plano

  out="$(QWEN_MENU_MODEL="${QWEN_MENU_MODEL:-}" QWEN_MENU_OPTS="${QWEN_MENU_OPTS:-}" python3 "$QWEN_MENU")" || out="ACTION=quit"
  # La salida la genera qwen-menu.py con shlex.quote: es seguro evaluarla.
  eval "$out"

  case "${ACTION:-quit}" in
    launch)
      _qwen_split_args "$PI_ARGS" || { [ "$monitor" = 1 ] && set -m; return 1; }
      QWEN_PI_NO_SESSION=0
      [ "$OPT_INCOGNITO" = 1 ] && QWEN_PI_NO_SESSION=1
      export QWEN_PI_NO_SESSION
      QWEN_LAYA="${OPT_LAYA:-1}"; export QWEN_LAYA
      _lb_prev="${LAYA_BACKEND:-}"        # el menú manda sobre laya/config.json solo en esta sesión
      if [ "${OPT_KEV:-0}" = 1 ]; then LAYA_BACKEND=kev; else LAYA_BACKEND=laya; fi
      if [ "${OPT_NOMODEL:-0}" = 1 ]; then
        local _kd=cpu; [ "${OPT_KEVGPU:-0}" = 1 ] && _kd=cuda
        if [ "${OPT_CLAUDE:-0}" = 1 ]; then
          KEV_DEVICE="$_kd" _qwen_run_claude "${_QWEN_ARGV[@]}"; rc=$?
        else
          KEV_DEVICE="$_kd" _laya_standalone; rc=$?
        fi
        LAYA_BACKEND="$_lb_prev"
        [ "$monitor" = 1 ] && set -m
        return "$rc"
      fi
      local profile=readonly
      [ "$OPT_EDIT" = 1 ] && profile=edit
      if [ "$OPT_OLLAMA" = 1 ]; then
        _qwen_run_ollama "$profile" "${_QWEN_ARGV[@]}"; rc=$?
      else
        QWENX_MODEL="$MODEL_PATH" QWENX_MMPROJ="$MMPROJ_PATH" \
          _qwen_run_local "$profile" "${_QWEN_ARGV[@]}"; rc=$?
      fi
      LAYA_BACKEND="$_lb_prev" ;;
    mem)    qwen-mem ;;
    status) qwen-status ;;
    laya)   _laya_standalone; rc=$? ;;
    *)      : ;;
  esac
  [ "$monitor" = 1 ] && set -m
  return "$rc"
}

# ── Entrada común: sin args → menú (con presets); con args → directo ──
# _qwen_entry  modelo  opciones(csv: edit,vision,incognito,ollama)  [args de pi...]
_qwen_entry() {
  local model="$1" opts="$2"; shift 2
  [ "${1:-}" = "--menu" ] && { shift; set -- ; }
  if [ $# -eq 0 ]; then
    QWEN_MENU_MODEL="$([ "$model" != base ] && printf '%s' "$model")" \
    QWEN_MENU_OPTS="$opts" _qwen_menu
    return $?
  fi
  local edit=0 vision=0 incog=0 ollama=0
  [[ ",$opts," == *,edit,* ]] && edit=1
  [[ ",$opts," == *,vision,* ]] && vision=1
  [[ ",$opts," == *,incognito,* ]] && incog=1
  [[ ",$opts," == *,ollama,* ]] && ollama=1
  _qwen_launch "$model" "$edit" "$vision" "$incog" "$ollama" "$@"
}

# ── Comandos públicos ──
qwen()                        { _qwen_entry base ""               "$@"; }
qwen-edit()                   { _qwen_entry base "edit"           "$@"; }
qwen-incognito()              { _qwen_entry base "incognito"      "$@"; }
qwen-edit-incognito()         { _qwen_entry base "edit,incognito" "$@"; }
qwen-vision()                 { _qwen_entry base "vision"         "$@"; }
qwen-vision-incognito()       { _qwen_entry base "vision,incognito" "$@"; }

qwenh()                       { _qwen_entry heretic ""               "$@"; }
qwenh-edit()                  { _qwen_entry heretic "edit"           "$@"; }
qwenh-incognito()             { _qwen_entry heretic "incognito"      "$@"; }
qwenh-edit-incognito()        { _qwen_entry heretic "edit,incognito" "$@"; }
qwenh-vision()                { _qwen_entry heretic "vision"         "$@"; }
qwenh-vision-incognito()      { _qwen_entry heretic "vision,incognito" "$@"; }

qwen-lite()                   { _qwen_entry iq3 "" "$@"; }
qwen-ollama()                 { _qwen_entry base "ollama" "$@"; }
qwen-claude() { QWEN_MENU_MODEL=none QWEN_MENU_OPTS="claude,kev,kevgpu,laya" _qwen_menu; }
