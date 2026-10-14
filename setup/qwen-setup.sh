#!/usr/bin/env bash
# qwen-setup.sh — config local de Qwen para Claude Code (separada de tu `claude` de Pro)
#
# Uso:
#   ./qwen-setup.sh          instala o actualiza la config (idempotente)
#   ./qwen-setup.sh --check  muestra el estado sin cambiar nada
#
# Qué deja instalado:
#   ~/.claude-local/settings.json   config propia de Claude Code (sin plugins): fix de caché, plan mode, reglas deny/ask (WebSearch, rm -rf, git push --force, DROP, .env)
#   ~/.qwen-local.sh                funciones `qwen` (llama.cpp), `qwen-ollama` (Ollama, respaldo), `qwen-incognito` y `qwenh-incognito` + las que usa bench-qwen.sh
#   una línea al final de ~/.bashrc que carga ~/.qwen-local.sh
#   ~/.claude-local/hooks/laya_hook.py + su registro como hook UserPromptSubmit (avisos de laya en pantalla; sin servicio no hace nada)
#
# Versión: 6.5 (2026-10-14)
# Cambios:
#   v1  Reconstruido desde el plan: qwen (Ollama, plan mode) + qwenx (llama.cpp, plan mode).
#   v2  `qwen` ajustada a tu definición real de ~/.bashrc: precarga el modelo en segundo
#       plano (curl a /api/generate) y hace `ollama stop` al salir. Puerto, token y modelo
#       coincidían.
#   v3  Plan mode confirmado en ~/.claude-local/settings.json (permissions.defaultMode = plan).
#       El script lo fija solo si falta y se quita el flag --permission-mode (una sola fuente).
#   v4  qwenx avisa si no encuentra el .gguf (p. ej. disco de modelos sin montar) en vez de fallar mudo.
#   v4.1 qwenx: `--no-mmap` ya no existe en tu build de llama.cpp (11606); se usa `--load-mode none`.
#   v4.2 qwenx: NCMOE=28 y UB=2048 (barrido de la Fase 4 + prueba a 32k).
#   v4.3 qwenx: CTX=65536 (a 32k una sesión real llegó a 41814 tokens: error 400) y CLAUDE_CODE_AUTO_COMPACT_WINDOW=56000.
#   v4.4 qwenx: /autocompact mostró 100k con 56000 fijado; ahora ventana 100000 + CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=55 (umbral ~55k).
#   v4.5 qwenx: barra de carga del modelo (lee los puntos que llama.cpp escribe en el log al cargar los tensores)
#        y solo abre Claude Code al llegar al 100 % (servidor listo).
#   v5  Refactor para bench-qwen.sh: funciones _qwen_up/_qwen_down (Ollama) y _qwenx_up/_qwenx_down (llama.cpp) que
#       fijan QWEN_URL, QWEN_TOKEN y QWEN_MODEL; `qwen` y `qwenx` pasan a ser envoltorios de ellas.
#       Logs de llama-server con fecha en ~/.cache/qwenx/ (se guardan los últimos 20); /tmp/llama-server.log
#       sigue existiendo como enlace al último. WebSearch denegado en settings.json (no funciona con backends
#       locales). Ajustes por variable de entorno para la Fase 6: QWENX_MODEL, QWENX_NCMOE, QWENX_UB, QWENX_CTX,
#       QWENX_NOTHINK=1 (el umbral de autocompactado se recalcula solo con QWENX_CTX).
#   v6  Fase 6 cerrada: gana q4-base (Q4_K_XL, thinking activado). `qwenx` pasa a llamarse `qwen` (llama.cpp) y la
#       de Ollama queda como `qwen-ollama`. Las variables siguen llamándose QWENX_* y las funciones internas _qwenx_*.
#   v6.1 qwen: CTX=131072 por defecto (VRAM medida 11262 MiB, bajo el umbral de 11500). QWEN_PCT limitado a 90
#       (con 131072 la fórmula daba 110). --check avisa si queda alguna definición de qwenx() o qwen() duplicada.
#   v6.2 qwen: la RAM de llama-server pasó de ~14,5 GiB recién cargado a ~22 GiB (8 GiB en swap) con el uso: se sospecha de
#       la caché de prompts (-cram, 8192 MiB por defecto). Nuevas variables opcionales, sin cambiar el comportamiento
#       por defecto: QWENX_CRAM=2048 (pasa -cram) y QWENX_LOADMODE=none|mmap|mlock|mmap+mlock (por defecto none, como antes).
#       Nueva función `qwen-mem`: muestra RSS y swap de llama-server para medir antes y después.
#   v6.3 laya (opcional, encendido por defecto): QWENX_LAYA=1 qwen arranca laya/laya_server.py (CPU, 127.0.0.1:8765) en segundo plano
#       y lo apaga al salir. El hook laya/laya_hook.py se copia a ~/.claude-local/hooks/ y se registra en settings.json; solo AVISA al
#       usuario (systemMessage), nunca bloquea y falla en silencio si el servicio no está. El instalador quita los hooks de prueba
#       (los que contienen hook-stdin o hook-test). Sin QWENX_LAYA=1 el comportamiento de qwen no cambia.
#   v6.4 Red de seguridad y puerto libre. (a) settings.json: reglas de permisos deny = WebSearch, rm -rf, git push --force; ask = DROP TABLE/DATABASE
#       y editar .env. Se definen al principio de este script (DENY_RULES / ASK_RULES); el instalador solo AÑADE las que falten, nunca quita las tuyas.
#       Son una red de seguridad, no una barrera: Claude Code compara el texto del comando (ver «Límites» en el aviso del instalador).
#       (b) _qwenx_up comprueba que el puerto 8001 esté libre antes de lanzar llama-server: antes un segundo arranque moría a los 28 ms y
#       /tmp/llama-server.log pasaba a apuntar a ese log inútil, y un segundo `qwen` se enganchaba al servidor del primero.
#       --check muestra las reglas, cuáles faltan y si el puerto está libre.
#   v6.5 Modo incógnito. `qwen-incognito` (y `qwenh-incognito`, que pasa por tu alias `qwenh` de ~/.bashrc) = `qwen` con QWENX_INCOG=1: Claude Code
#       arranca con una config temporal en /dev/shm (RAM) con copia de settings.json y .claude.json de ~/.claude-local; transcripciones,
#       historial de prompts, file-history y todo lo demás se escriben ahí y se borran al salir. Antes `_qwen_claude` fijaba CLAUDE_CONFIG_DIR a
#       ~/.claude-local con `env` y pisaba el de la función incógnito (seguía guardando en ~/.claude-local/projects), y la función copiaba
#       ~/.claude.json (el de tu cuenta Pro) en vez del de ~/.claude-local. `_qwen_claude` ahora usa QWEN_CONFIG_DIR si está definida.
#       Un `qwen` posterior borra los restos de una sesión incógnito que haya terminado sin limpiar (terminal cerrada a la fuerza).
#       Las llama-server logs (~/.cache/qwenx) no son transcripciones. --check cuenta qwen-incognito() (debe ser 1).

set -euo pipefail

CONF_DIR="$HOME/.claude-local"
SETTINGS="$CONF_DIR/settings.json"
FUNCS="$HOME/.qwen-local.sh"
BASHRC="$HOME/.bashrc"
SOURCE_LINE='[ -f "$HOME/.qwen-local.sh" ] && source "$HOME/.qwen-local.sh"'
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAYA_DIR="$(cd "$SCRIPT_DIR/../laya" 2>/dev/null && pwd || true)"
HOOKS_DIR="$CONF_DIR/hooks"

# Reglas de permisos de la config de Qwen (una por línea). Edítalas aquí y vuelve a ejecutar el instalador:
# solo se AÑADEN las que falten; las que ya tengas en settings.json no se tocan.
# Sintaxis según la documentación de Claude Code: Bash(...) acepta * en cualquier posición y las rutas de archivos se escriben
# con Edit(...) (una regla de ruta sobre Write no se consulta). deny gana a ask y ask gana a allow.
#   deny: patrones estrechos, casi siempre destructivos de verdad.
#   ask:  patrones que también pueden coincidir con algo legítimo (leer migraciones con grep, editar la config de .env).
DENY_RULES='WebSearch
Agent
Task
Bash(rm -rf*)
Bash(rm -fr*)
Bash(rm * -rf*)
Bash(rm * -fr*)
Bash(git push --force*)
Bash(git push -f*)
Bash(git push * --force*)
Bash(git push * -f*)'
ASK_RULES='Bash(*DROP TABLE*)
Bash(*DROP DATABASE*)
Bash(*drop table*)
Bash(*drop database*)
Edit(.env)
Edit(.env.*)'
export DENY_RULES ASK_RULES

check() {
  echo "== Estado de la config local de Qwen =="
  if [ -f "$SETTINGS" ]; then
    echo "settings.json: existe"
    python3 - <<'EOF'
import json, os
p = os.path.expanduser("~/.claude-local/settings.json")
d = json.load(open(p))
print("  CLAUDE_CODE_ATTRIBUTION_HEADER =", d.get("env", {}).get("CLAUDE_CODE_ATTRIBUTION_HEADER", "(no definido)"))
print("  permissions.defaultMode =", d.get("permissions", {}).get("defaultMode", "(no definido)"))
perm = d.get("permissions", {})
for k in ("deny", "ask"):
    print("  permissions.%s =" % k, perm.get(k, "(no definido)"))
def lista(n):
    return [l.strip() for l in os.environ.get(n, "").splitlines() if l.strip()]
esperadas = [(k, r) for k in ("deny", "ask") for r in lista(k.upper() + "_RULES")]
faltan = [(k, r) for k, r in esperadas if r not in perm.get(k, [])]
print("  reglas del instalador: %d de %d presentes" % (len(esperadas) - len(faltan), len(esperadas)))
for k, r in faltan:
    print("    falta en %s: %s" % (k, r))
EOF
  else
    echo "settings.json: NO existe"
  fi
  [ -f "$HOOKS_DIR/laya_hook.py" ] && echo "hook de laya: copiado en $HOOKS_DIR" || echo "hook de laya: NO copiado"
  grep -q laya_hook "$SETTINGS" 2>/dev/null && echo "hook de laya: registrado en settings.json" || echo "hook de laya: NO registrado en settings.json"
  [ -n "$LAYA_DIR" ] && [ -f "$LAYA_DIR/laya_server.py" ] && echo "laya_server.py: presente en $LAYA_DIR" || echo "laya_server.py: NO encontrado (se espera en <repo>/laya/)"
  [ -f "$FUNCS" ] && echo "~/.qwen-local.sh: existe" || echo "~/.qwen-local.sh: NO existe"
  if [ -f "$FUNCS" ]; then
    grep -q '_qwenx_up' "$FUNCS" && echo "  funciones de bench-qwen.sh (v5+): presentes" || echo "  funciones de bench-qwen.sh (v5+): FALTAN (vuelve a ejecutar el instalador)"
    local nq nqo nqx nqi
    nq=$(grep -cE '^qwen\(\) \{' "$FUNCS" || true)
    nqo=$(grep -cE '^qwen-ollama\(\) \{' "$FUNCS" || true)
    nqx=$(grep -cE '^qwenx\(\) \{' "$FUNCS" || true)
    nqi=$(grep -cE '^qwen-incognito\(\) \{' "$FUNCS" || true)
    echo "  qwen(): $nq (debe ser 1) | qwen-ollama(): $nqo (debe ser 1) | qwenx(): $nqx (debe ser 0) | qwen-incognito(): $nqi (debe ser 1)"
    grep -nE 'QWENX_CTX:-' "$FUNCS" | sed 's/^/  ctx por defecto: /' || true
  fi
  grep -qF "$SOURCE_LINE" "$BASHRC" 2>/dev/null && echo "~/.bashrc: carga ~/.qwen-local.sh" || echo "~/.bashrc: NO carga ~/.qwen-local.sh"
  echo "-- Definiciones de qwen en ~/.bashrc (si hay otras, la última en cargarse gana) --"
  grep -n 'qwen' "$BASHRC" 2>/dev/null || echo "  (ninguna)"
  [ -x "$HOME/llama.cpp/build/bin/llama-server" ] && echo "llama-server: compilado" || echo "llama-server: aún no compilado"
  if (exec 3<>/dev/tcp/127.0.0.1/8001) 2>/dev/null; then
    h=$(pgrep -a llama-server | head -n 1 || true); echo "puerto 8001: OCUPADO${h:+ ($h)}"
  else
    echo "puerto 8001: libre"
  fi
  ls "$HOME"/models/*.gguf 2>/dev/null | sed 's/^/modelo: /' || true
  echo "-- Logs de llama-server (más reciente primero) --"
  ls -t "$HOME"/.cache/qwenx/llama-*.log 2>/dev/null | head -n 3 | sed 's/^/  /' || true
}

if [ "${1:-}" = "--check" ]; then
  check
  exit 0
fi

# 0) hook de laya: se copia a ~/.claude-local/hooks/ para que funcione aunque el disco del repo no esté montado
mkdir -p "$CONF_DIR"
if [ -n "$LAYA_DIR" ] && [ -f "$LAYA_DIR/laya_hook.py" ]; then
  mkdir -p "$HOOKS_DIR"
  cp "$LAYA_DIR/laya_hook.py" "$HOOKS_DIR/laya_hook.py"
  echo "hook de laya copiado"
else
  echo "aviso: no encuentro laya/laya_hook.py junto al repo; se omite el hook de laya"
fi

# 1) settings.json propio, sin tocar lo que ya tenga
python3 - <<'EOF'
import json, os
p = os.path.expanduser("~/.claude-local/settings.json")
d = json.load(open(p)) if os.path.exists(p) else {}
d.setdefault("env", {})["CLAUDE_CODE_ATTRIBUTION_HEADER"] = "0"
perm = d.setdefault("permissions", {})
perm.setdefault("defaultMode", "plan")                 # plan mode solo si no hay valor
def lista(n):
    return [l.strip() for l in os.environ.get(n, "").splitlines() if l.strip()]
for clave, reglas in (("deny", lista("DENY_RULES")), ("ask", lista("ASK_RULES"))):
    actuales = perm.setdefault(clave, [])
    for r in reglas:                                   # solo añade las que falten; no quita las del usuario
        if r not in actuales:
            actuales.append(r)
# (WebSearch va en DENY_RULES: el incorporado lo ejecuta Anthropic y con backend local no hace nada)
# hook de laya (UserPromptSubmit): quita los hooks de prueba y registra el de laya una sola vez
hook_path = os.path.expanduser("~/.claude-local/hooks/laya_hook.py")
ups = d.get("hooks", {}).get("UserPromptSubmit", [])
ups = [e for e in ups if not any(("hook-stdin" in h.get("command", "") or "hook-test" in h.get("command", "")) for h in e.get("hooks", []))]
if os.path.exists(hook_path):
    cmd = 'python3 "%s"' % hook_path
    if not any(h.get("command") == cmd for e in ups for h in e.get("hooks", [])):
        ups.append({"hooks": [{"type": "command", "command": cmd, "timeout": 3}]})
if ups:
    d.setdefault("hooks", {})["UserPromptSubmit"] = ups
elif "hooks" in d:
    d["hooks"].pop("UserPromptSubmit", None)
    if not d["hooks"]:
        del d["hooks"]
json.dump(d, open(p, "w"), indent=2)
print("settings.json OK")
EOF

# 2) funciones (se reescribe entero en cada ejecución: edita ESTE script, no el destino)
cat > "$FUNCS" <<'FUNCS_EOF'
# Generado por qwen-setup.sh — no editar a mano, edita el script y vuelve a ejecutarlo.
#
# Contrato con bench-qwen.sh: cada motor tiene _X_up (arranca y deja listos QWEN_URL, QWEN_TOKEN y
# QWEN_MODEL) y _X_down (lo apaga). `qwen` y `qwen-ollama` son solo: up → Claude Code → down.

# Lanza Claude Code contra un servidor local, con config aparte (~/.claude-local).
# El plan mode (solo lectura) viene de permissions.defaultMode en su settings.json;
# se sale con Shift+Tab cuando quieras que edite.
# Uso: _qwen_claude <base_url> <token> <modelo> [args de claude...]
# Si QWEN_COMPACT está definida (la fija _qwenx_up), se aplica el autocompactado para el contexto del servidor.
# Si QWEN_CONFIG_DIR está definida (la fija _qwen_incog_up), Claude Code usa esa config en vez de ~/.claude-local.
_qwen_claude() {
  local url="$1" token="$2" model="$3"; shift 3
  local cfg="${QWEN_CONFIG_DIR:-$HOME/.claude-local}"
  local x=()
  if [ -n "${QWEN_COMPACT:-}" ]; then
    x=(CLAUDE_CODE_AUTO_COMPACT_WINDOW="$QWEN_COMPACT" CLAUDE_AUTOCOMPACT_PCT_OVERRIDE="${QWEN_PCT:-55}")
  fi
  env ${x[@]+"${x[@]}"} \
    CLAUDE_CONFIG_DIR="$cfg" \
    ANTHROPIC_BASE_URL="$url" \
    ANTHROPIC_AUTH_TOKEN="$token" \
    ANTHROPIC_API_KEY="" \
    ANTHROPIC_DEFAULT_OPUS_MODEL="$model" \
    ANTHROPIC_DEFAULT_SONNET_MODEL="$model" \
    ANTHROPIC_DEFAULT_HAIKU_MODEL="$model" \
    claude --model "$model" "$@"
}

# --- Ollama --------------------------------------------------------------------------
# Precarga el modelo en segundo plano (la carga real ocurre mientras abre Claude Code).
_qwen_up() {
  QWEN_URL="http://localhost:11434"; QWEN_TOKEN="ollama"; QWEN_MODEL="qwen3.6:35b"
  unset QWEN_COMPACT QWEN_PCT
  (curl -s "$QWEN_URL/api/generate" -d "{\"model\":\"$QWEN_MODEL\"}" >/dev/null 2>&1 &)
  return 0
}
_qwen_down() { ollama stop "$QWEN_MODEL" 2>/dev/null; return 0; }

# qwen-ollama: Ollama (anterior, queda de respaldo). Descartada en la Fase 6: timeout en la etapa 1 y tests rotos en la 2.
qwen-ollama() {
  _qwen_up
  _qwen_claude "$QWEN_URL" "$QWEN_TOKEN" "$QWEN_MODEL" "$@"
  _qwen_down
}

# --- llama.cpp -------------------------------------------------------------------------
# Barra de carga para llama-server. llama.cpp escribe 1 punto en el log por cada 1 % de tensores cargados
# (línea de solo puntos); se cuentan y se muestran. Se llega a 100 % cuando /health responde (modelo + contexto listos).
# Uso interno: _qwen_wait_ready <pid> <log> <puerto>
_qwen_wait_ready() {
  local pid="$1" log="$2" port="$3" w=30 t0=$SECONDS i=0 raw=0 pct=0 f label
  local spin='|/-\' tty=0
  [ -t 1 ] && tty=1
  until curl -sf "http://localhost:$port/health" >/dev/null; do
    if ! kill -0 "$pid" 2>/dev/null; then
      [ $tty = 1 ] && printf '\n'
      if [ -n "${QWENX_INT:-}" ]; then echo "cancelado"; return 130; fi
      echo "llama-server falló, mira $log"; return 1
    fi
    raw=$(grep -aE '^\.+$' "$log" 2>/dev/null | tr -d '\n' | wc -c)
    pct=$raw; [ "$pct" -gt 99 ] && pct=99
    if   [ "$raw" -eq 0 ];  then label="leyendo el modelo"
    elif [ "$raw" -lt 100 ]; then label="cargando el modelo"
    else                         label="preparando el contexto"; fi
    if [ $tty = 1 ]; then
      f=$(( pct * w / 100 ))
      printf '\r\033[K  %s Qwen [%s%s] %3d%%  %s (%ds)' "${spin:i%4:1}" \
        "$(printf '%*s' "$f" '' | tr ' ' '#')" "$(printf '%*s' $((w - f)) '' | tr ' ' '-')" \
        "$pct" "$label" $((SECONDS - t0))
    fi
    i=$((i + 1)); sleep 0.2
  done
  if [ $tty = 1 ]; then
    printf '\r\033[K  * Qwen [%s] 100%%  listo en %ds\n' "$(printf '%*s' "$w" '' | tr ' ' '#')" $((SECONDS - t0))
  else
    echo "Qwen listo en $((SECONDS - t0))s"
  fi
}

# Arranca llama-server y espera a que esté listo. NCMOE y UB medidos en la Fase 4 (Q4_K_XL): VRAM ~10,4 GB a 64k, ~11,3 GB a 128k.
# Ajustes opcionales por entorno (los nombres siguen siendo QWENX_*):
#   QWENX_MODEL=ruta.gguf  QWENX_NCMOE=28  QWENX_UB=2048  QWENX_CTX=131072  QWENX_NOTHINK=1
#   QWENX_CRAM=2048        (limita la caché de prompts en RAM; sin definir, llama-server usa su valor por defecto)
#   QWENX_LOADMODE=none    (none | mmap | mlock | mmap+mlock; por defecto none)
# Si a 131072 la VRAM pasa de ~11500 MiB: QWENX_NCMOE=30 qwen   (o QWENX_CTX=98304 qwen)
# Si la RAM disponible se hunde y aparece swap: QWENX_CRAM=2048 qwen   (y mide con `qwen-mem`)
_qwenx_up() {
  local model="${QWENX_MODEL:-$HOME/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf}"
  local ncmoe="${QWENX_NCMOE:-28}" ub="${QWENX_UB:-2048}" ctx="${QWENX_CTX:-131072}" port=8001
  local lm="${QWENX_LOADMODE:-none}"
  local logdir="$HOME/.cache/qwenx" log rc extra=()
  [ -f "$model" ] || { echo "No encuentro $model (¿está montado el disco de los modelos?)"; return 1; }
  # Puerto libre ANTES de tocar logs o lanzar nada. Con el puerto ocupado un segundo llama-server muere a los 28 ms,
  # /tmp/llama-server.log pasaría a apuntar a ese log inútil y _qwen_wait_ready daría por bueno el /health del servidor ajeno
  # (cerrar una sesión apagaría el servidor de las dos).
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    echo "El puerto $port ya está en uso: no arranco otro llama-server."
    pgrep -a llama-server | head -n 1 | sed 's/^/  llama-server activo: /' || true
    echo "  Si es otra sesión de qwen, ciérrala primero. Si lo usa otro proceso: ss -ltnp 'sport = :$port'"
    return 1
  fi
  pgrep -x ollama >/dev/null && echo "aviso: Ollama activo, puede ocupar VRAM"
  [ "${QWENX_NOTHINK:-0}" = 1 ] && extra=(--chat-template-kwargs '{"enable_thinking": false}')
  [ -n "${QWENX_CRAM:-}" ] && extra+=(-cram "$QWENX_CRAM")
  # Log con fecha (se conservan los últimos 20); /tmp/llama-server.log apunta siempre al último
  mkdir -p "$logdir"
  log="$logdir/llama-$(date +%Y%m%d-%H%M%S).log"
  ln -sf "$log" /tmp/llama-server.log
  ls -t "$logdir"/llama-*.log 2>/dev/null | tail -n +21 | xargs -r rm -f --
  "$HOME/llama.cpp/build/bin/llama-server" -m "$model" --alias qwen3.6-35b --port "$port" \
    -ngl 99 --n-cpu-moe "$ncmoe" -c "$ctx" -b "$ub" -ub "$ub" -fa on \
    -ctk q8_0 -ctv q8_0 --load-mode "$lm" --jinja \
    --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0.0 ${extra[@]+"${extra[@]}"} \
    >"$log" 2>&1 &
  QWENX_SPID=$!
  QWEN_URL="http://localhost:$port"; QWEN_TOKEN="local"; QWEN_MODEL="qwen3.6-35b"
  # Claude Code asume una ventana de 200k con modelos locales y /autocompact mostró 100k aunque se fijara menos:
  # ventana fija 100000 y umbral = ~84 % del contexto del servidor, con tope 90 (65536 → 55; 131072 → 90, o sea ~90k).
  QWEN_PCT=$(( ctx * 84 / 100000 )); [ "$QWEN_PCT" -gt 90 ] && QWEN_PCT=90
  export QWEN_COMPACT=100000 QWEN_PCT
  _qwen_wait_ready "$QWENX_SPID" "$log" "$port"; rc=$?
  if [ $rc -eq 0 ]; then _laya_up; else _qwenx_down; fi
  return $rc
}
_qwenx_down() {
  _laya_down
  if [ -n "${QWENX_SPID:-}" ]; then
    kill "$QWENX_SPID" 2>/dev/null; wait "$QWENX_SPID" 2>/dev/null
  fi
  unset QWENX_SPID QWEN_COMPACT QWEN_PCT
  return 0
}

# --- laya (opcional): QWENX_LAYA=0 qwen --------------------------------------------------
# Servicio local en CPU (127.0.0.1:$LAYA_PORT, 8765 por defecto) que el hook laya_hook.py consulta. Se arranca en segundo plano
# DESPUÉS de que llama-server esté listo (la primera vez descarga el checkpoint). Log: ~/.cache/qwenx/laya.log
_laya_up() {
  [ "${QWENX_LAYA:-1}" = 1 ] || return 0
  local dir="${QWEN_LAYA_DIR:-}" port="${LAYA_PORT:-8765}" log="$HOME/.cache/qwenx/laya.log"
  if [ ! -x "$dir/.venv/bin/python" ] || [ ! -f "$dir/laya_server.py" ]; then
    echo "aviso: laya no disponible (falta $dir/.venv o laya_server.py); sigo sin laya"; return 0
  fi
  if curl -sf "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
    echo "aviso: ya hay un servicio en 127.0.0.1:$port; no arranco otro"; return 0
  fi
  mkdir -p "$HOME/.cache/qwenx"
  "$dir/.venv/bin/python" "$dir/laya_server.py" >"$log" 2>&1 &
  QWENX_LPID=$!
  echo "laya arrancando en segundo plano (log: $log)"
  return 0
}
_laya_down() {
  if [ -n "${QWENX_LPID:-}" ]; then
    kill "$QWENX_LPID" 2>/dev/null; wait "$QWENX_LPID" 2>/dev/null
  fi
  unset QWENX_LPID
  return 0
}

# qwen-mem: RAM de llama-server (RSS y swap) y estado general. Úsalo recién cargado y tras una sesión larga.
qwen-mem() {
  local pid; pid=$(pgrep -x llama-server | head -n 1)
  if [ -n "$pid" ]; then
    grep -E 'VmRSS|VmSwap' "/proc/$pid/status" | awk '{printf "  %s %.2f GiB\n", $1, $2/1048576}'
  else
    echo "  llama-server no está corriendo"
  fi
  free -m | awk 'NR==1 || /Mem|Swap/'
}

# --- incógnito (QWENX_INCOG=1) ---------------------------------------------------------
# Config temporal de Claude Code en /dev/shm (RAM): copia settings.json y .claude.json de ~/.claude-local; todo lo que Claude Code
# escriba (projects/*.jsonl, history.jsonl, file-history, todos, shell-snapshots...) queda ahí y se borra al salir.
# Solo puede haber una sesión qwen a la vez (puerto 8001), así que los restos de una sesión anterior se borran sin riesgo.
_qwen_incog_up() {
  local d
  rm -rf /dev/shm/claude-incog.* 2>/dev/null
  d=$(mktemp -d /dev/shm/claude-incog.XXXXXX) || { echo "no pude crear el directorio temporal en /dev/shm"; return 1; }
  cp "$HOME/.claude-local/settings.json" "$d/" 2>/dev/null
  cp "$HOME/.claude-local/.claude.json" "$d/" 2>/dev/null
  QWEN_CONFIG_DIR="$d"
  echo "modo incógnito: nada se guarda en disco (config temporal en $d)"
  return 0
}
_qwen_incog_down() {
  case "${QWEN_CONFIG_DIR:-}" in /dev/shm/claude-incog.*) rm -rf -- "$QWEN_CONFIG_DIR" ;; esac
  unset QWEN_CONFIG_DIR
  return 0
}

# qwen: llama.cpp (Q4_K_XL, decidido en la Fase 6). Ctrl+C durante la carga apaga el servidor.
# Con QWENX_INCOG=1 (o vía qwen-incognito) la sesión de Claude Code no deja nada en disco.
qwen() {
  local rc
  unset QWENX_INT
  trap 'QWENX_INT=1; _qwenx_down' INT
  _qwenx_up; rc=$?
  trap - INT
  unset QWENX_INT
  [ $rc -eq 0 ] || return $rc
  if [ "${QWENX_INCOG:-0}" = 1 ]; then
    _qwen_incog_up || { _qwenx_down; return 1; }
  fi
  _qwen_claude "$QWEN_URL" "$QWEN_TOKEN" "$QWEN_MODEL" "$@"
  _qwen_incog_down
  _qwenx_down
}

# qwen-incognito: qwen sin transcripción ni sesión guardada.
qwen-incognito() { QWENX_INCOG=1 qwen "$@"; }

# qwenh-incognito: lo mismo pasando por tu alias qwenh (definido en ~/.bashrc, con su modelo propio).
qwenh-incognito() {
  type qwenh >/dev/null 2>&1 || { echo "qwenh no está definida (va en ~/.bashrc)"; return 1; }
  QWENX_INCOG=1 qwenh "$@"
}
FUNCS_EOF
printf '\n# Ruta de laya en el repo (la fija qwen-setup.sh)\nQWEN_LAYA_DIR=%q\n' "$LAYA_DIR" >> "$FUNCS"
echo "~/.qwen-local.sh OK"

# 3) línea en ~/.bashrc (una sola vez, al final para que gane sobre definiciones antiguas)
if ! grep -qF "$SOURCE_LINE" "$BASHRC" 2>/dev/null; then
  printf '\n# Config local de Qwen (qwen-setup.sh)\n%s\n' "$SOURCE_LINE" >> "$BASHRC"
  echo "~/.bashrc: línea añadida"
else
  echo "~/.bashrc: ya cargaba ~/.qwen-local.sh"
fi

echo
echo "Listo. Ejecuta: source ~/.bashrc"
echo "Si antes tenías un alias o función 'qwen' en ~/.bashrc, bórrala para evitar confusiones (bash setup/qwen-setup.sh --check las lista)."
echo
echo "Reglas de permisos (v6.4): deny = WebSearch, rm -rf, git push --force; ask = DROP TABLE/DATABASE y editar .env."
echo "Límites: Claude Code compara el texto del comando. No detiene /bin/rm, bash -c 'rm -rf ...', git -C . push --force ni un script que borre por dentro;"
echo "  tampoco el DROP en mayúsculas/minúsculas mezcladas. Para eso están el plan mode y, si hace falta, un hook PreToolUse o el sandbox."
echo "Compruébalas dentro de qwen con /permissions y con una orden de prueba (p. ej. pedirle un rm -rf en una carpeta temporal desechable)."
