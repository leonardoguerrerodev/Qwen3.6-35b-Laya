# lib/lc.sh — little-coder con lo elegido del kit de Pi (6-nov-2026). Ver little-coder/README.md.
# little-coder = nuestra copia en little-coder/ (versionada en git) sobre un Pi fijo en su node_modules.
# little-coder ignora el AGENTS.md global y fija sus extensiones; lo nuestro entra por sus puertas oficiales:
#   --no-skills + --skill: solo las skills elegidas del kit (sin esto se colaba ~/.agents/skills, p. ej. hf-cli)
#   carpeta de agente propia (QWEN_LC_DIR): prompts del kit (symlinks a ~/.pi-qwen/agent, una sola fuente)
#   LITTLE_CODER_EXTENSIONS_DIR: oficio, tps, handoff, laya-hook, lc-temperatura y lc-permisos (cargan después de las suyas)
#   lc-plan: plan aprobado (ctrl+q) → tareas/NNN-*.md del proyecto, por etapas; sub-agentes con razonamiento low
#   skills apagadas (alt+k, oficio.ts): las mismas que en Pi (QWEN_SKILLS_OFF = su skills-off.json)
#   permisos: su gate en accept-all y lc-permisos pregunta lo que no está en su lista blanca (no bloquea sin preguntar)
#   --append-system-prompt: el bloque qwen-oficio del AGENTS.md de Pi
#   --exclude-tools: sus herramientas de benchmark (GAIA, Terminal-Bench) y dispatch; ver QWEN_LC_SIN_TOOLS
#   LITTLE_CODER_MODELS_FILE: el modelo cargado, con ctx, tope ctx/2 y nivel de razonamiento por petición

QWEN_LC_DIR="${QWEN_LC_DIR:-$HOME/.pi-qwen/lc-agent}"
# fuera del PATH: sin PI_CODING_AGENT_DIR, Pi usaría ~/.pi/agent (la carpeta de tu Pi principal)
QWEN_LC_BIN="${QWEN_LC_BIN:-$QWEN_ROOT/little-coder/bin/little-coder.mjs}"
QWEN_LC_SKILLS="diagnosticar planificar etapas revisar rea rea-js rea-artefactos"
QWEN_LC_PROMPTS="sigue rea"
QWEN_LC_EXTS="oficio tps handoff laya-hook"
# Fuera (~1.400 tokens de esquemas en cada arranque, 26 → 12 herramientas): Browser*/Evidence* son de GAIA y
# nunca se usaron; ShellSession* sin Terminal-Bench es un bash repetido; dispatch lanza sub-agentes contra el
# mismo llama-server de un solo slot: hacen fila y le borran la caché de prompt al agente principal.
QWEN_LC_SIN_TOOLS="BrowserNavigate,BrowserClick,BrowserType,BrowserScroll,BrowserExtract,BrowserBack,BrowserHistory,EvidenceAdd,EvidenceGet,EvidenceList,dispatch,ShellSession,ShellSessionCwd,ShellSessionReset"

_qwen_lc_prepare() {   # _qwen_lc_prepare alias ctx
  local alias="$1" ctx="$2" d="$QWEN_LC_DIR" s
  mkdir -p "$d/prompts" "$d/extensions" || return 1
  for s in $QWEN_LC_PROMPTS; do ln -sfn "$QWEN_PI_DIR/prompts/$s.md" "$d/prompts/$s.md"; done
  for s in $QWEN_LC_EXTS;    do ln -sfn "$QWEN_PI_DIR/extensions/$s.ts" "$d/extensions/$s.ts"; done
  for s in lc-temperatura lc-permisos lc-plan; do ln -sfn "$QWEN_ROOT/lib/$s.ts" "$d/extensions/$s.ts"; done
  # el bloque sin sus marcas <!-- qwen-oficio:… --> (al modelo no le dicen nada)
  { sed -n '/<!-- qwen-oficio:begin/,/<!-- qwen-oficio:end/{/<!-- qwen-oficio:/!p}' "$QWEN_PI_DIR/AGENTS.md"
    # solo en little-coder: su modo plan escribe el plan que lc-plan.ts copia a tareas/ para la skill etapas
    printf '%s\n' '' '**Modo plan:** si te piden un plan de implementación, escríbelo en el formato de la skill `planificar`: `# Plan: <título>`, Objetivo, Fuera, y etapas `## Etapa N — <título>` con `Archivos:`, `Hacer:` (nombres exactos) y `Verificación: <comando> → <señal>`; si una verificación solo mira la sintaxis, súmale un caso calculado a mano. Al aprobarse queda en `tareas/NNN-*.md` y se ejecuta con la skill `etapas`.'
  } > "$d/oficio.md"
  python3 -I - "$d/models.json" "$alias" "$ctx" "$QWEN_PORT" <<'PY'
import json, sys
path, alias, ctx, port = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
tope = min(32768, max(512, ctx // 2))   # igual que Pi (lib/pi.sh)

# Su thinking-budget (abortaba el turno y apagaba el razonamiento) va en 32768 en little-coder/.pi/settings.json,
# por encima de este tope: el razonamiento lo corta el servidor (--reasoning-budget del perfil), como en Pi.
m = {"id": alias, "name": alias, "reasoning": True, "input": ["text"], "contextWindow": ctx,
     "maxTokens": tope,
     "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
     # a nivel de modelo: el proveedor de little-coder solo pasa baseUrl/apiKey/api/models
     "compat": {"supportsDeveloperRole": False, "supportsReasoningEffort": True},
     "thinkingLevelMap": {"off": "none", "minimal": None, "low": "low", "medium": "medium",
                          "high": None, "xhigh": "xhigh", "max": None}}
json.dump({"default": "llamacpp/" + alias, "providers": {"llamacpp": {
    "api": "openai-completions", "baseUrl": f"http://127.0.0.1:{port}/v1",
    "apiKey": "LLAMACPP_API_KEY", "models": [m]}}}, open(path, "w"), indent=2)
PY
}

_qwen_lc() {   # _qwen_lc profile model [args...] — profile edit = todas sus herramientas; otro = solo lectura
  local profile="$1" model="$2" s; shift 2
  [ -x "$QWEN_LC_BIN" ] || { echo "No encuentro little-coder en $QWEN_LC_BIN. Si falta su Pi: (cd \"$QWEN_ROOT/little-coder\" && npm ci --ignore-scripts)" >&2; return 127; }
  local -a extra=(--append-system-prompt "$QWEN_LC_DIR/oficio.md" --exclude-tools "$QWEN_LC_SIN_TOOLS" --no-skills)
  for s in $QWEN_LC_SKILLS; do extra+=(--skill "$QWEN_PI_DIR/skills/$s"); done
  [ "$profile" = edit ] || extra+=(--tools "$QWEN_PI_TOOLS_RO")
  [ "${QWEN_PI_NO_SESSION:-0}" = 1 ] && extra+=(--no-session)
  local idioma; idioma="$(_qwen_idioma_prompt)"
  [ -n "$idioma" ] && extra+=(--append-system-prompt "$idioma")
  PI_CODING_AGENT_DIR="$QWEN_LC_DIR" LITTLE_CODER_MODELS_FILE="$QWEN_LC_DIR/models.json" \
    LITTLE_CODER_EXTENSIONS_DIR="$QWEN_LC_DIR/extensions" LLAMACPP_API_KEY=local \
    LITTLE_CODER_NO_UPDATE_CHECK=1 QWEN_LC_TEMP="${QWENX_TEMP:-}" \
    LITTLE_CODER_PERMISSION_MODE=accept-all QWEN_LC_PKG="$(dirname "$(readlink -f "$QWEN_LC_BIN")")/.." \
    QWEN_SKILLS_OFF="$QWEN_PI_DIR/skills-off.json" \
    "$QWEN_LC_BIN" --no-update-check --model "llamacpp/$model" "${extra[@]}" "$@"
}

# ── Sesión local completa desde el menú (Agente = little-coder): llama-server (+laya) → little-coder → apagado ──
_qwen_run_local_lc() {   # _qwen_run_local_lc profile [args de little-coder...]  (gemela de _qwen_run_local)
  local profile="$1" rc=0; shift
  _qwen_lc_prepare "$QWEN_ALIAS" "$QWENX_CTX" || return $?
  unset QWENX_INT
  trap 'QWENX_INT=1; _qwenx_down' INT
  if _qwenx_up; then rc=0; else rc=$?; fi
  trap - INT
  unset QWENX_INT
  [ "$rc" -eq 0 ] || { _qwenx_down; return "$rc"; }
  if _qwen_lc "$profile" "$QWEN_ALIAS" "$@"; then rc=0; else rc=$?; fi
  _qwenx_down
  return "$rc"
}
