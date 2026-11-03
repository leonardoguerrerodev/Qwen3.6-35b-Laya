# qwen-local.sh — punto de entrada: Qwen3.6-35B-A3B local con Pi + llama.cpp + laya.
# Se carga desde ~/.bashrc a través del symlink ~/.qwen-local.sh → este archivo.
# Para bash interactivo. No usa `set -e` (se hace `source`, no debe afectar tu shell).
#
# Comandos (sin argumentos abren el menú; con argumentos lanzan directo y pasan todo a pi):
#   qwen / qwen-edit / qwen-incognito / qwen-edit-incognito / qwen-vision / qwen-vision-incognito
#   qwenh …  (mismas variantes con el modelo heretic uncensored)
#   qwen-ollama (respaldo)     qwen-claude (kev GPU + Claude, sin modelo)     qwen-mem   qwen-status

# ── Raíz de la repo (resuelve el symlink) ──
_qwen_self="$(readlink -f "${BASH_SOURCE[0]}")"
QWEN_ROOT="$(cd "$(dirname "$_qwen_self")" && pwd)"
export QWEN_ROOT
unset _qwen_self

for _qwen_mod in config laya voz llama pi claude qwencode; do
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
  for id in base heretic q9b q4b $(_qwen_custom_models | cut -f1); do
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
  if [ -f "$VOZ_SERVER" ]; then
    [ -x "$VOZ_VENV/bin/python" ] && echo "voz:           $VOZ_SERVER (venv OK)" || echo "voz:           $VOZ_SERVER (venv se creará al arrancar)"
  else
    echo "voz:           NO encontrado ($VOZ_SERVER)"
  fi
  _voz_port_open && echo "puerto $VOZ_PORT:   voz activa" || echo "puerto $VOZ_PORT:   libre"
  if p="$(_voz_model_path)"; then echo "modelo voz:    $p"; else echo "modelo voz:    no encontrado ($VOZ_MODEL_GLOB en $QWEN_MODELS_DIR)"; fi
  for p in models.json settings.json; do
    if [ -f "$QWEN_PI_DIR/$p" ]; then
      python3 -m json.tool "$QWEN_PI_DIR/$p" >/dev/null 2>&1 && echo "pi/$p: JSON OK" || echo "pi/$p: ERROR de JSON"
    else
      echo "pi/$p: no existe (se crea al lanzar o con el instalador)"
    fi
  done
}

# ── Lanzamiento directo (sin menú) ──
# _qwen_launch  modelo(base|heretic|q9b|q4b)  edit  vision  incognito  ollama  -- args de pi...
_qwen_launch() {
  local model="$1" edit="$2" vision="$3" incog="$4" ollama="$5"; shift 5
  local profile=readonly mmproj="" path=""
  [ "$edit" = 1 ] && profile=edit
  [ "$incog" = 1 ] && export QWEN_PI_NO_SESSION=1 || export QWEN_PI_NO_SESSION=0
  export QWEN_CHAT=0   # el modo Chat solo sale del menú

  if [ "$ollama" = 1 ]; then
    _qwen_run_ollama "$profile" "$@"; return $?
  fi
  path="$(_qwen_model_path "$model")" || { echo "No encuentro el modelo '$model' en $QWEN_MODELS_DIR" >&2; return 1; }
  if [ "$vision" = 1 ]; then
    mmproj="$(_qwen_mmproj_path "$model")" || { echo "No encuentro el mmproj de '$model' en $QWEN_MODELS_DIR" >&2; return 1; }
  fi
  QWENX_MODEL="$path" QWENX_MMPROJ="$mmproj" _qwen_run_local "$profile" "$@"
}

# ── Menú TUI ──
_qwen_menu() {
  command -v python3 >/dev/null 2>&1 || { echo "Falta python3" >&2; return 1; }
  [ -f "$QWEN_MENU" ] || { echo "No encuentro el menú: $QWEN_MENU" >&2; return 1; }

  local out ACTION MODEL_ID MODEL_PATH OPT_EDIT OPT_VISION OPT_INCOGNITO OPT_CHAT OPT_OLLAMA OPT_LAYA OPT_KEV OPT_VOZ OPT_NOMODEL OPT_CLAUDE OPT_KEVGPU MMPROJ_PATH PI_ARGS CLAUDE_DIR P_CTX P_TEMP P_IDIOMA P_KEV P_KVQ P_TOPP P_TOPK P_MINP P_NCMOE P_NGL P_LOADMODE P_BATCH P_UB P_EXTRA _lb_prev _kr_prev _kd_prev rc=0
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
      QWEN_VOZ="${OPT_VOZ:-0}"; export QWEN_VOZ
      QWEN_CHAT="${OPT_CHAT:-0}"; export QWEN_CHAT   # Chat: _qwen_pi quita herramientas, skills y prompt de código
      QWEN_IDIOMA="${P_IDIOMA:-auto}"; export QWEN_IDIOMA   # idioma de respuesta: _qwen_idioma_prompt
      _lb_prev="${LAYA_BACKEND:-}"        # el menú manda sobre laya/config.json solo en esta sesión
      if [ "${OPT_KEV:-0}" = 1 ]; then LAYA_BACKEND=kev; else LAYA_BACKEND=laya; fi
      # Kev (tamaño y CPU/CUDA) y Claude valen con cualquier modelo, Ollama o «Ninguno»; solo esta sesión
      _kr_prev="$KEV_RUN"; _kd_prev="${KEV_DEVICE:-}"
      _kev_pick "${P_KEV:-auto}" "$((1 - ${OPT_NOMODEL:-0}))"
      if [ "${OPT_KEVGPU:-0}" = 1 ]; then KEV_DEVICE=cuda; else KEV_DEVICE=cpu; fi
      export KEV_DEVICE
      if [ "${OPT_NOMODEL:-0}" = 1 ]; then
        # Sin modelo grande: los args son de claude; kev/laya quedan aquí hasta pulsar Enter
        [ "${OPT_CLAUDE:-0}" = 1 ] && { _qwen_claude_window "${CLAUDE_DIR:-$PWD}" "${_QWEN_ARGV[@]}" || true; }
        _laya_standalone; rc=$?
        LAYA_BACKEND="$_lb_prev"; KEV_RUN="$_kr_prev"
        if [ -n "$_kd_prev" ]; then KEV_DEVICE="$_kd_prev"; else unset KEV_DEVICE; fi
        [ "$monitor" = 1 ] && set -m
        return "$rc"
      fi
      # Con modelo: Claude en su ventana (espera a laya, que arranca con el backend) y Pi aquí
      [ "${OPT_CLAUDE:-0}" = 1 ] && { _qwen_claude_window "${CLAUDE_DIR:-$PWD}" || true; }
      local profile=readonly
      [ "$OPT_EDIT" = 1 ] && profile=edit
      if [ "$OPT_OLLAMA" = 1 ]; then
        _qwen_run_ollama "$profile" "${_QWEN_ARGV[@]}"; rc=$?
      else
        # P_CTX vacío = QWENX_CTX del shell (120k); los Parámetros del menú solo valen esta sesión
        QWENX_MODEL="$MODEL_PATH" QWENX_MMPROJ="$MMPROJ_PATH" \
          QWENX_CTX="${P_CTX:-$QWENX_CTX}" QWENX_TEMP="${P_TEMP:-0.6}" QWENX_KV="${P_KVQ:-$QWENX_KV}" \
          QWENX_TOPP="${P_TOPP:-}" QWENX_TOPK="${P_TOPK:-}" QWENX_MINP="${P_MINP:-}" \
          QWENX_NCMOE="${P_NCMOE:-$QWENX_NCMOE}" QWENX_NGL="${P_NGL:-${QWENX_NGL:-}}" \
          QWENX_LOADMODE="${P_LOADMODE:-$QWENX_LOADMODE}" QWENX_BATCH="${P_BATCH:-$QWENX_BATCH}" \
          QWENX_UB="${P_UB:-$QWENX_UB}" QWENX_EXTRA="${P_EXTRA:-${QWENX_EXTRA:-}}" \
          _qwen_run_harness "$profile" "${_QWEN_ARGV[@]}"; rc=$?
      fi
      LAYA_BACKEND="$_lb_prev"; KEV_RUN="$_kr_prev"
      if [ -n "$_kd_prev" ]; then KEV_DEVICE="$_kd_prev"; else unset KEV_DEVICE; fi ;;
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

qwen-ollama()                 { _qwen_entry base "ollama" "$@"; }
qwen-claude() { QWEN_MENU_MODEL=none QWEN_MENU_OPTS="claude,kev,kevgpu,laya" _qwen_menu; }
qwen-voz()    { _voz_standalone; }
qwen-model()  { QWEN_DATA="$QWEN_DATA" python3 "$QWEN_ROOT/menu/qwen-model.py" "$@"; }   # agrega/edita/quita modelos del menú
qwen-voz-motores() { _voz_motores_install; }   # kokoro + f5 + s2 + GPU de piper (una vez)

# qwen-pin [nuevo]  ·  muestra el PIN de Pi, o lo cambia por uno elegido.
#
# El PIN se genera al azar la primera vez y después persiste, así que en teoría
# alcanza con mirarlo una vez. En la práctica, estando lejos de la PC no había
# forma de recuperarlo. Poder elegir uno memorable resuelve eso sin publicar el
# PIN en la web, que lo volvería inútil: el PIN se canjea por el token, y el
# token da una shell a cualquiera que esté en la red.
#
# Cambiar el PIN NO da de baja los dispositivos ya enrolados: el token sigue
# siendo el mismo, y es el token lo que guarda el navegador.
qwen-pin() {
  local auth_file="$QWEN_DATA/web-pi-auth.json" nuevo="${1:-}"
  if [ -n "$nuevo" ] && ! [[ "$nuevo" =~ ^[0-9]{4,12}$ ]]; then
    echo "El PIN tiene que ser de 4 a 12 dígitos." >&2
    return 1
  fi
  mkdir -p "$(dirname "$auth_file")" 2>/dev/null || true
  python3 - "$auth_file" "$nuevo" <<'PY'
import json, os, secrets, sys
path, nuevo = sys.argv[1:3]
data = {}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
if not data.get("token"):
    data["token"] = secrets.token_urlsafe(18)
if nuevo:
    data["password"] = nuevo
elif not data.get("password"):
    data["password"] = f"{secrets.randbelow(1000000):06d}"
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f)
os.chmod(path, 0o600)
print(("PIN cambiado a: " if nuevo else "PIN actual: ") + data["password"])
if nuevo:
    print("Reiniciá qwen-web para que tome el PIN nuevo.")
PY
}

# ── UI web (LAN de casa; arranque manual, Ctrl+C para apagar) ──
# El venv con `websockets` es para adjuntar pi (fase 2: terminal en el navegador);
# si no se puede preparar (sin red, etc.), sigue con python3 del sistema y esa
# parte queda deshabilitada — el resto de la web (fase 1) no depende de él.
qwen-web() {
  command -v python3 >/dev/null 2>&1 || { echo "Falta python3" >&2; return 1; }
  [ -f "$WEB_SERVER" ] || { echo "No encuentro $WEB_SERVER" >&2; return 1; }
  local py=python3
  if [ -x "$WEB_VENV/bin/python" ]; then
    py="$WEB_VENV/bin/python"
  elif ! python3 -c "import websockets" 2>/dev/null; then
    echo "web: preparando venv con 'websockets' (adjuntar pi) ..." >&2
    if mkdir -p "$(dirname "$WEB_VENV")" 2>/dev/null \
       && python3 -m venv "$WEB_VENV" 2>/dev/null \
       && "$WEB_VENV/bin/pip" install --quiet websockets 2>&1 | tail -n 1 >&2 \
       && [ -x "$WEB_VENV/bin/python" ]; then
      py="$WEB_VENV/bin/python"
      echo "web: venv listo." >&2
    else
      echo "web: no se pudo preparar el venv; sigue sin adjuntar pi (fase 2 deshabilitada)" >&2
    fi
  fi
  # Token para adjuntar pi: ahora persiste entre arranques de qwen-web (antes
  # era uno nuevo cada vez, así que el token guardado en el navegador quedaba
  # viejo apenas reiniciabas). Se guarda junto a un PIN corto en
  # $QWEN_DATA/web-pi-auth.json (modo 600): el navegador pide el PIN una sola
  # vez por dispositivo (POST /api/pi-unlock) y a partir de ahí entra solo con
  # el token guardado — el PIN es la capa simple, el token sigue siendo el que
  # de verdad autentica el WebSocket. Sin seguridad extrema a propósito: red
  # de confianza, mismo criterio que el resto de esta web (ver web/README.md).
  local token="${WEB_PI_TOKEN:-}" password="${WEB_PI_PASSWORD:-}" auth_file="$QWEN_DATA/web-pi-auth.json"
  if "$py" -c "import websockets" 2>/dev/null; then
    if [ -z "$token" ] || [ -z "$password" ]; then
      mkdir -p "$(dirname "$auth_file")" 2>/dev/null || true
      read -r token password < <(python3 - "$auth_file" "$token" "$password" <<'PY'
import json, os, secrets, sys
path, tok_env, pass_env = sys.argv[1:4]
data = {}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
token = tok_env or data.get("token") or secrets.token_urlsafe(18)
password = pass_env or data.get("password") or f"{secrets.randbelow(1000000):06d}"
if data.get("token") != token or data.get("password") != password:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"token": token, "password": password}, f)
    os.chmod(path, 0o600)
print(token, password)
PY
      )
    fi
    echo "web: PIN para entrar a Pi desde el navegador: $password  (una vez por dispositivo; después entra solo)" >&2
  fi
  QWEN_ROOT="$QWEN_ROOT" WEB_PORT="$WEB_PORT" WEB_WS_PORT="$WEB_WS_PORT" \
    WEB_PI_TOKEN="$token" WEB_PI_PASSWORD="$password" \
    "$py" "$WEB_SERVER"
}

# ── Lanzador del escritorio (qwen-web.desktop) ──
# El servidor vive mientras viva la ventana: cerrarla le manda SIGHUP y se apaga
# (los backends que prendió desde la web siguen, como siempre: «Apagar» o qwen-stop).
# Si ya hay uno abierto, pregunta si mantenerlo o cerrarlo, en vez de chocar por el puerto.
qwen-web-desktop() {
  local pid r
  if _qwen_port_open "$WEB_PORT"; then
    # quién escucha en el puerto (ss solo muestra el PID de procesos de esta cuenta)
    pid="$(ss -ltnpH "sport = :$WEB_PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | head -n 1 | cut -d= -f2)"
    [ -n "$pid" ] && ! grep -qa "web_server.py" "/proc/$pid/cmdline" 2>/dev/null && pid=""
    echo "El servidor web ya está abierto en el puerto $WEB_PORT${pid:+ (PID $pid)}."
    if [ -z "$pid" ]; then
      echo "Lo abrió otra cuenta o no es qwen-web: no lo puedo cerrar desde aquí."
    else
      read -r -p "¿Mantenerlo abierto [m] o cerrarlo [c]? [m] " r
      if [[ "$r" == [cC]* ]]; then
        kill "$pid" 2>/dev/null
        local n=0
        while _qwen_port_open "$WEB_PORT" && (( n++ < 25 )); do sleep 0.2; done
        _qwen_port_open "$WEB_PORT" && echo "No se cerró (sigue ocupado el puerto $WEB_PORT)." || echo "Servidor web cerrado."
      else
        echo "Se mantiene abierto."
      fi
    fi
    read -r -p "Enter para cerrar esta ventana. " _
    return 0
  fi
  local barra web k
  _qwen_voz_barra & barra=$!
  # qwen-web en segundo plano para leer teclas aquí: «s» salta el audio de voz en curso.
  # Ctrl+C (o cerrar la ventana) apaga el servidor igual que antes.
  qwen-web </dev/null & web=$!
  # qwen-web es una función: corre en un subshell cuyo hijo es web_server.py → se le manda
  # SIGINT al hijo (como el Ctrl+C de antes) y luego se cierra el subshell.
  trap 'pkill -INT -P "$web" 2>/dev/null; kill "$web" 2>/dev/null' INT HUP TERM
  echo "  s = saltar el audio de voz en curso · Ctrl+C = apagar"
  while kill -0 "$web" 2>/dev/null; do
    if read -rsn1 -t 1 k && [[ "$k" == [sS] ]]; then
      curl -sf -m 3 -X POST "http://127.0.0.1:$WEB_PORT/api/voz/saltar" >/dev/null \
        || curl -sf -m 3 -X POST "http://127.0.0.1:$VOZ_PORT/api/saltar" >/dev/null || true
    fi
  done
  wait "$web" 2>/dev/null
  trap - INT HUP TERM
  kill "$barra" 2>/dev/null; wait "$barra" 2>/dev/null
  printf '\e7\033[r\e8'   # devuelve la pantalla entera al scroll
  read -r -p "Servidor web detenido. Enter para cerrar esta ventana. " _
}

# Barra fija en la última fila de la terminal: % de la síntesis de voz en curso (GET
# /api/progreso de voz_server). Reserva esa fila achicando la región de scroll.
# ponytail: comparte la tty con los logs de qwen-web; solo redibuja cuando cambia.
_qwen_voz_barra() {
  local filas cols filas0=0 previa="" linea a pct seg motor perfil w n relleno
  while kill -0 $$ 2>/dev/null; do
    read -r filas cols < <(stty size </dev/tty 2>/dev/null) || { sleep 1; continue; }
    if [ "$filas" != "$filas0" ]; then
      printf '\e7\033[1;%dr\e8' "$((filas - 1))"; filas0=$filas; previa=""
    fi
    if read -r a pct seg motor perfil < <(curl -sf -m 0.5 "http://127.0.0.1:$VOZ_PORT/api/progreso"); then
      if [ "$a" = 1 ] && [ "$pct" = - ]; then
        linea="voz ▸ $motor generando… ${seg}s (sin %)"
      elif [ "$a" = 1 ]; then
        w=$(( cols - 30 )); (( w < 10 )) && w=10; n=$(( pct * w / 100 ))
        printf -v relleno '%*s' "$n" ''; relleno=${relleno// /█}
        printf -v linea 'voz ▸ %s [%s%*s] %3d%% %ss' "$motor" "$relleno" "$((w - n))" '' "$pct" "$seg"
      else
        linea="voz ▸ lista · ${perfil:-?} ($motor)"
      fi
    else
      linea="voz ▸ apagada"
    fi
    if [ "$linea" != "$previa" ]; then
      printf '\e7\033[%d;1H\033[2K\033[7m %s \033[0m\e8' "$filas" "${linea:0:cols-2}"
      previa=$linea
    fi
    sleep 0.3
  done
}
