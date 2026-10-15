# lib/pi.sh — Pi como harness: configuración, perfiles de herramientas y ejecución.
# Requiere lib/config.sh, lib/laya.sh y lib/llama.sh.
# No toca ~/.pi/agent ni ~/.claude-local: Pi usa un directorio separado (QWEN_PI_DIR).
#
# Sin subagentes: el perfil se pasa a Pi con --tools (lista cerrada). Solo existen las
# herramientas listadas en QWEN_PI_TOOLS_RO / QWEN_PI_TOOLS_EDIT; ninguna delega en
# subagentes, así que todo ocurre en la sesión principal.
# Perfiles:  readonly → lectura (read,grep,find,ls)
#            edit     → + write,edit,bash   (¡solo en proyectos de confianza!)

# ── Genera/actualiza models.json, settings.json y AGENTS.md (idempotente, conserva lo demás) ──
_qwen_pi_init() {
  mkdir -p "$QWEN_PI_DIR" || return 1
  python3 - "$QWEN_PI_DIR" "$QWEN_PI_PROVIDER" "$QWEN_ALIAS" "$QWEN_PORT" \
            "$QWEN_OLLAMA_URL" "$QWEN_OLLAMA_MODEL" "$QWENX_CTX" "$QWEN_PI_TOOLS_RO" <<'PY' || return $?
import json, os, sys, tempfile
root, provider, alias, port, oll_url, oll_model, ctx, tools_ro = sys.argv[1:9]
ctx = int(ctx)

def read_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError(f"{path}: el documento raíz debe ser un objeto JSON")
    return obj

def atomic_json(path, obj):
    fd, tmp = tempfile.mkstemp(prefix=".qwen-pi-", dir=root, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2); f.write("\n")
        os.chmod(tmp, 0o600); os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

zero = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}
compat = {"supportsDeveloperRole": False, "supportsReasoningEffort": False}

models_path = os.path.join(root, "models.json")
models = read_json(models_path)
models.setdefault("$schema", "https://pi.dev/schemas/models.schema.json")
providers = models.setdefault("providers", {})
providers[provider] = {
    "baseUrl": f"http://127.0.0.1:{port}/v1", "api": "openai-completions",
    "apiKey": "local", "compat": compat,
    "models": [{"id": alias, "name": "Qwen3.6 35B A3B (llama.cpp local)",
                "reasoning": True, "input": ["text"], "contextWindow": ctx,
                "maxTokens": 8192, "cost": zero,
                "samplingParams": {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0.0}}]}
providers["qwen-ollama"] = {
    "baseUrl": f"{oll_url}/v1", "api": "openai-completions",
    "apiKey": "ollama", "compat": compat,
    "models": [{"id": oll_model, "name": "Qwen3.6 35B (Ollama, respaldo)",
                "reasoning": True, "input": ["text"], "contextWindow": 32768,
                "maxTokens": 8192, "cost": zero}]}
atomic_json(models_path, models)

settings_path = os.path.join(root, "settings.json")
s = read_json(settings_path)
s.setdefault("$schema", "https://pi.dev/schemas/settings.schema.json")
s["defaultProvider"] = provider
s["defaultModel"] = alias
s["defaultThinkingLevel"] = "medium"
s["defaultTools"] = tools_ro.split(",")
c = s.setdefault("compaction", {})
c["enabled"] = True
c["reserveTokens"] = 8192
c["keepRecentTokens"] = 20000
atomic_json(settings_path, s)
print("models.json y settings.json de Pi actualizados")
PY
  _qwen_pi_context
}

# ── Aviso para el modelo: su carpeta de agente es QWEN_PI_DIR, no ~/.pi/agent ──
# Pi carga <carpeta de agente>/AGENTS.md como instrucciones de usuario. Sin este aviso el
# modelo asume ~/.pi/agent (la ruta por defecto de Pi) y crea ahí sus archivos.
# Mantiene un bloque marcado (idempotente); conserva el resto del archivo.
_qwen_pi_context() {
  mkdir -p "$QWEN_PI_DIR" || return 1
  python3 - "$QWEN_PI_DIR" <<'PY'
import os, sys, tempfile
root = sys.argv[1]
path = os.path.join(root, "AGENTS.md")
BEGIN = "<!-- qwen-local:begin (lo gestiona lib/pi.sh; no edites dentro del bloque) -->"
END = "<!-- qwen-local:end -->"
body = ("## Configuración de Pi en este entorno\n\n"
        "Pi se lanza con PI_CODING_AGENT_DIR=" + root + " (NO con ~/.pi/agent).\n"
        "Esa es la carpeta de agente real: ahí van keybindings.json, settings.json, models.json,\n"
        "extensions/, skills/, prompts/ y themes/.\n"
        "Nunca crees ni edites configuración de Pi en ~/.pi/agent: en esta instalación Pi no la lee.")
block = BEGIN + "\n" + body + "\n" + END
legacy = body.replace("## ", "# ", 1)   # versión anterior pegada a mano, sin marcas
text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
i, j = text.find(BEGIN), text.find(END)
if i >= 0 and j > i:
    new = text[:i] + block + text[j + len(END):]
elif legacy in text:
    new = text.replace(legacy, block, 1)
else:
    if not text or text.endswith("\n\n"):
        sep = ""
    elif text.endswith("\n"):
        sep = "\n"
    else:
        sep = "\n\n"
    new = text + sep + block + "\n"
if new != text:
    fd, tmp = tempfile.mkstemp(prefix=".qwen-agents-", dir=root, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new)
        os.chmod(tmp, 0o644); os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    print("AGENTS.md de Pi actualizado: " + path)
PY
}

# ── Sincroniza el contexto que conoce Pi con el que recibe llama-server ──
_qwen_pi_prepare() {   # _qwen_pi_prepare provider model ctx
  local provider="$1" model="$2" ctx="$3"
  [[ "$ctx" =~ ^[1-9][0-9]*$ ]] || { echo "QWENX_CTX debe ser un entero positivo" >&2; return 2; }
  [ -f "$QWEN_PI_DIR/models.json" ] && [ -f "$QWEN_PI_DIR/settings.json" ] || _qwen_pi_init >/dev/null || return 1
  _qwen_pi_context >/dev/null || echo "aviso: no pude actualizar $QWEN_PI_DIR/AGENTS.md" >&2
  python3 - "$QWEN_PI_DIR" "$provider" "$model" "$ctx" <<'PY'
import json, os, sys, tempfile
root, provider, model_id = sys.argv[1:4]
ctx = int(sys.argv[4])
def read(p):
    with open(p, encoding="utf-8") as f: return json.load(f)
def write(p, obj):
    fd, tmp = tempfile.mkstemp(prefix=".qwen-runtime-", dir=root, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2); f.write("\n")
        os.chmod(tmp, 0o600); os.replace(tmp, p)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
mp, sp = os.path.join(root, "models.json"), os.path.join(root, "settings.json")
d = read(mp)
p = d.get("providers", {}).get(provider)
if not p: raise SystemExit(f"No está configurado el proveedor Pi {provider!r} en {mp}")
m = next((x for x in p.get("models", []) if x.get("id") == model_id), None)
if m is None: raise SystemExit(f"No está configurado el modelo Pi {provider}/{model_id}")
m["contextWindow"] = ctx
m["maxTokens"] = min(8192, max(512, ctx // 4))
write(mp, d)
s = read(sp)
c = s.setdefault("compaction", {})
c["enabled"] = True
c["reserveTokens"] = min(8192, max(1024, ctx // 12))
c["keepRecentTokens"] = min(20000, max(1000, ctx // 4))
write(sp, s)
PY
}

# Divide el texto de argumentos del menú respetando comillas, sin evaluar nada.
# Uso:  _qwen_split_args "$PI_ARGS"   → rellena el array global _QWEN_ARGV
_qwen_split_args() {
  _QWEN_ARGV=()
  [ -n "${1:-}" ] || return 0
  mapfile -d '' -t _QWEN_ARGV < <(python3 -c \
    'import shlex,sys; sys.stdout.write("\0".join(shlex.split(sys.argv[1]))+"\0")' "$1") \
    || { echo "Argumentos inválidos (comillas sin cerrar): $1" >&2; return 1; }
}

# ── Ejecuta Pi con un perfil ──
_qwen_pi() {   # _qwen_pi profile provider model [args...]
  local profile="$1" provider="$2" model="$3"; shift 3
  local tools
  local -a session_args=()
  if ! command -v pi >/dev/null 2>&1; then
    echo "No encuentro el comando 'pi' en PATH. Instala/verifica Pi e inténtalo de nuevo." >&2
    return 127
  fi
  if [ "$profile" = edit ]; then tools="$QWEN_PI_TOOLS_EDIT"; else tools="$QWEN_PI_TOOLS_RO"; fi
  [ "${QWEN_PI_NO_SESSION:-0}" = 1 ] && session_args+=(--no-session)
  PI_CODING_AGENT_DIR="$QWEN_PI_DIR" \
    pi --provider "$provider" --model "$model" --tools "$tools" "${session_args[@]}" "$@"
}

# ── Sesión local completa: llama-server (+laya) → Pi → apagado ──
_qwen_run_local() {   # _qwen_run_local profile [args de pi...]
  local profile="$1"; shift
  local rc=0
  _qwen_pi_prepare "$QWEN_PI_PROVIDER" "$QWEN_ALIAS" "$QWENX_CTX" || return $?
  unset QWENX_INT
  trap 'QWENX_INT=1; _qwenx_down' INT
  if _qwenx_up; then rc=0; else rc=$?; fi
  trap - INT
  unset QWENX_INT
  [ "$rc" -eq 0 ] || { _qwenx_down; return "$rc"; }
  if _qwen_pi "$profile" "$QWEN_PI_PROVIDER" "$QWEN_ALIAS" "$@"; then rc=0; else rc=$?; fi
  _qwenx_down
  return "$rc"
}

# ── Sesión contra Ollama (respaldo) ──
_qwen_run_ollama() {   # _qwen_run_ollama profile [args de pi...]
  local profile="$1"; shift
  local rc=0
  _qwen_up || return $?
  _qwen_pi_prepare qwen-ollama "$QWEN_MODEL" "$QWEN_OLLAMA_CTX" || { _qwen_down; return 1; }
  _laya_up || true          # laya también acompaña a Ollama (si QWEN_LAYA=1)
  if _qwen_pi "$profile" qwen-ollama "$QWEN_MODEL" "$@"; then rc=0; else rc=$?; fi
  _laya_down
  _qwen_down
  return "$rc"
}
