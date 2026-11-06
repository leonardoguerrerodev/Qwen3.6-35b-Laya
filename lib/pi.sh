# lib/pi.sh — Pi como harness: configuración, perfiles de herramientas y ejecución.
# Requiere lib/config.sh, lib/laya.sh y lib/llama.sh.
# No toca ~/.pi/agent ni ~/.claude-local: Pi usa un directorio separado (QWEN_PI_DIR).
#
# Sin subagentes: el perfil se pasa a Pi con --tools (lista cerrada). Solo existen las
# herramientas listadas en QWEN_PI_TOOLS_RO / QWEN_PI_TOOLS_EDIT; ninguna delega en
# subagentes, así que todo ocurre en la sesión principal.
# Perfiles:  readonly → lectura (read,grep,find,ls)
#            edit     → + write,edit,bash   (¡solo en proyectos de confianza!)

# ── Genera/actualiza models.json, settings.json, el hook de laya y AGENTS.md
#     (idempotente, conserva lo demás) ──
_qwen_pi_init() {
  mkdir -p "$QWEN_PI_DIR" || return 1
  python3 - "$QWEN_PI_DIR" "$QWEN_PI_PROVIDER" "$QWEN_ALIAS" "$QWEN_PORT" \
            "$QWEN_OLLAMA_URL" "$QWEN_OLLAMA_MODEL" "$QWENX_CTX" "$QWEN_PI_TOOLS_RO" \
            "$LAYA_DIR" "$LAYA_PORT" "$VOZ_PORT" "$WEB_PORT" <<'PY' || return $?
import json, os, sys, tempfile
root, provider, alias, port, oll_url, oll_model, ctx, tools_ro, laya_dir, laya_port, voz_port, web_port = sys.argv[1:13]
ctx = int(ctx)

def read_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError(f"{path}: el documento raíz debe ser un objeto JSON")
    return obj

def atomic_write(path, text, mode="w"):
    fd, tmp = tempfile.mkstemp(prefix=".qwen-pi-", dir=root, text=True)
    try:
        with os.fdopen(fd, mode, encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, 0o600); os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def atomic_json(path, obj):
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")

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
                "maxTokens": 16384, "cost": zero,
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
c["reserveTokens"] = 16384
c["keepRecentTokens"] = 20000
atomic_json(settings_path, s)

# Gemelo de laya/laya_hook.py pero para Pi (que no tiene "hooks" de Claude Code:
# usa extensiones TS en <agent-dir>/extensions/, autodescubiertas, antes de cada
# turno — ver before_agent_start en docs/extensions.md). Sin esto, marcar
# Laya/Kev en el launcher solo deja el servidor corriendo: nada lo consulta.
LAYA_HOOK_TS = r"""/**
 * laya-hook.ts — generado por qwen-local (lib/pi.sh:_qwen_pi_init), no
 * editar a mano: `_qwen_pi_init` solo corre si falta models.json o
 * settings.json (ver _qwen_pi_prepare); forzar con `_qwen_pi_init` a mano
 * si laya/config.json cambia y querés que este archivo lo refleje. Avisa en pantalla
 * (ctx.ui.notify, nunca al modelo) si laya ve algo destructivo, un intento
 * de saltarse reglas, o una tarea compleja. Gemelo de laya/laya_hook.py
 * (mismo /classify; ese otro es el hook UserPromptSubmit de Claude Code).
 * Nunca bloquea: cualquier error (sin servidor, timeout, config rota) se
 * ignora en silencio, igual que laya_hook.py.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import * as fs from "node:fs";

const LAYA_PORT = __LAYA_PORT__;
const CONFIG_PATH = __CONFIG_PATH__;

function thresholds(): { destructivo: number; injection: number } {
  const cfg = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
  let th = {
    destructivo: Number(cfg.thresholds.destructivo),
    injection: Number(cfg.thresholds.injection),
  };
  const env = process.env.LAYA_THRESHOLD;
  if (env) {
    const v = Number(env);
    th = { destructivo: v, injection: v };
  }
  return th;
}

export default function (pi: ExtensionAPI) {
  pi.on("before_agent_start", async (event, ctx) => {
    if (event.messageType !== "user" || !event.prompt?.trim()) return;
    try {
      const th = thresholds();
      const res = await fetch(`http://127.0.0.1:${LAYA_PORT}/classify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: event.prompt }),
        signal: AbortSignal.timeout(1500),
      });
      if (!res.ok) return;
      const data = await res.json();
      const avisos: string[] = [];
      if ((data.destructivo ?? 0) >= th.destructivo) {
        avisos.push(`posible acción destructiva (${data.destructivo.toFixed(2)})`);
      }
      if ((data.injection ?? 0) >= th.injection) {
        avisos.push(`posible intento de saltarse reglas (${data.injection.toFixed(2)})`);
      }
      if (data.complejidad === "compleja") {
        avisos.push("tarea compleja: considera dividirla en pasos");
      }
      if (avisos.length && ctx.hasUI) {
        ctx.ui.notify("laya: " + avisos.join("; "), "warning");
      }
    } catch {
      // laya nunca debe estorbar.
    }
  });
}
"""
ext_dir = os.path.join(root, "extensions")
os.makedirs(ext_dir, exist_ok=True)
ext_content = (LAYA_HOOK_TS
    .replace("__LAYA_PORT__", str(int(laya_port)))
    .replace("__CONFIG_PATH__", json.dumps(os.path.join(laya_dir, "config.json"))))
atomic_write(os.path.join(ext_dir, "laya-hook.ts"), ext_content)

# Gemelo de laya-hook.ts: lee la respuesta final de Pi (no las de razonamiento ni
# tool calls) y la manda a voz_server.py cuando Pi ya terminó de verdad
# (agent_settled, no message_end: un mensaje puede terminar y seguir encadenando
# tool calls). Si voz no está corriendo (toggle apagado, o todavía no arrancó),
# el fetch falla y se ignora en silencio — nunca debe estorbar, igual que laya.
VOZ_HOOK_TS = r"""/**
 * voz-hook.ts — generado por qwen-local (lib/pi.sh:_qwen_pi_init), no editar a
 * mano. Al terminar el turno, manda la última respuesta de texto de Pi a
 * web_server.py (POST /api/speak-relay): si hay un navegador adjuntado por la
 * fase 2 de la web, el audio suena ahí (en el teléfono que está chateando).
 * Si no hay nadie adjuntado (uso normal en terminal local, o qwen-web ni está
 * corriendo), cae a reproducir con aplay/paplay en Nobora, como antes.
 * Nunca bloquea: cualquier error (voz apagada, sin aplay/paplay, timeout) se
 * ignora en silencio. Gemelo de laya-hook.ts (ese usa before_agent_start, este
 * message_end + agent_settled); ver voz/voz_server.py para el contrato de /hablar.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Key } from "@earendil-works/pi-tui";
import { spawn } from "node:child_process";
import { request } from "node:http";

const VOZ_PORT = __VOZ_PORT__;
const WEB_PORT = __WEB_PORT__;

// El motor s2 (Fish Audio S2 Pro) tarda minutos en CPU. fetch() de Node corta a los
// 5 min sin cabeceras (headersTimeout de undici), por eso aquí va node:http, sin ese
// límite; el tope propio es de 30 min.
const TOPE_MS = 30 * 60 * 1000;

function post(port: number, path: string, cuerpo: object): Promise<{ status: number; tasa: string; datos: Buffer }> {
  return new Promise((resolve, reject) => {
    const req = request({ host: "127.0.0.1", port, path, method: "POST",
                          headers: { "Content-Type": "application/json" }, timeout: TOPE_MS }, (res) => {
      const partes: Buffer[] = [];
      res.on("data", (c: Buffer) => partes.push(c));
      res.on("end", () => resolve({ status: res.statusCode || 0,
                                    tasa: String(res.headers["x-sample-rate"] || "22050"),
                                    datos: Buffer.concat(partes) }));
      res.on("error", reject);
    });
    req.on("timeout", () => req.destroy(new Error("timeout")));
    req.on("error", reject);
    req.end(JSON.stringify(cuerpo));
  });
}

// Si hay un navegador adjuntado por web_server.py (fase 2), le pide que le
// reenvíe el audio por el mismo WebSocket — así suena en el teléfono que está
// chateando, no en los parlantes de Nobara. Si no hay nadie adjuntado (uso
// normal en terminal local, o qwen-web ni está corriendo) "delivered" da
// false enseguida y el caller sigue con reproducir() local, como antes.
async function intentarRelay(texto: string): Promise<boolean> {
  try {
    const r = await post(WEB_PORT, "/api/speak-relay", { texto });
    return r.status === 200 && !!(JSON.parse(r.datos.toString()) as { delivered?: boolean }).delivered;
  } catch {
    return false;
  }
}

function reproducir(pcm: Uint8Array, tasa: string): Promise<void> {
  const intentos: [string, string[]][] = [
    ["aplay", ["-q", "-r", tasa, "-f", "S16_LE", "-c", "1"]],
    ["paplay", ["--raw", `--rate=${tasa}`, "--format=s16le", "--channels=1"]],
  ];
  return new Promise((resolve) => {
    const intentar = (i: number) => {
      if (i >= intentos.length) return resolve();
      const [cmd, args] = intentos[i];
      let proc;
      try {
        proc = spawn(cmd, args, { stdio: ["pipe", "ignore", "ignore"] });
      } catch {
        return intentar(i + 1);
      }
      proc.on("error", () => intentar(i + 1));
      proc.on("exit", () => resolve());
      proc.stdin.end(Buffer.from(pcm));
    };
    intentar(0);
  });
}

// Las etiquetas de la skill voz-etiquetas ([sigh]...) viajan tal cual: voz_server.py
// las quita si el motor del perfil no es s2.
async function hablar(texto: string): Promise<void> {
  try {
    if (await intentarRelay(texto)) return;   // ya sonó en el navegador adjuntado
    const r = await post(VOZ_PORT, "/hablar", { texto });
    if (r.status === 200 && r.datos.length) await reproducir(new Uint8Array(r.datos), r.tasa);
  } catch {
    // voz nunca debe estorbar.
  }
}

// Corta la voz en curso: la síntesis (voz_server) y lo que esté sonando (aplay/paplay acá,
// o el navegador adjuntado — web_server.py le avisa por WS). Sin qwen-web, va directo a voz.
async function saltar(): Promise<void> {
  try {
    await post(WEB_PORT, "/api/voz/saltar", {});
  } catch {
    await post(VOZ_PORT, "/api/saltar", {}).catch(() => {});
  }
}

export default function (pi: ExtensionAPI) {
  let ultimoTexto = "";

  pi.registerShortcut(Key.alt("s"), {
    description: "Saltar el audio de voz en curso",
    handler: async (ctx) => { await saltar(); ctx.ui.notify("voz: saltado", "info"); },
  });
  pi.registerCommand("saltar", {
    description: "Saltar el audio de voz en curso (igual que Alt+S)",
    handler: async (_args, ctx) => { await saltar(); ctx.ui.notify("voz: saltado", "info"); },
  });

  pi.on("message_end", async (event) => {
    const msg = event.message as { role?: string; content?: Array<{ type: string; text?: string }> };
    if (msg.role !== "assistant" || !Array.isArray(msg.content)) return;
    const texto = msg.content
      .filter((c) => c.type === "text" && c.text)
      .map((c) => c.text)
      .join("\n")
      .trim();
    if (texto) ultimoTexto = texto;
  });

  pi.on("agent_settled", async (event) => {
    const texto = ultimoTexto;
    ultimoTexto = "";
    if (event.aborted || !texto) return;
    void hablar(texto);   // sin await: Pi no espera a la voz (s2 tarda minutos)
  });
}
"""
ext_content_voz = (VOZ_HOOK_TS
    .replace("__VOZ_PORT__", str(int(voz_port)))
    .replace("__WEB_PORT__", str(int(web_port))))
atomic_write(os.path.join(ext_dir, "voz-hook.ts"), ext_content_voz)

print("models.json, settings.json y extensions/{laya,voz}-hook.ts de Pi actualizados")
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
  # también regenera si faltan los hooks (cuenta nueva, o instalación anterior a ellos)
  [ -f "$QWEN_PI_DIR/models.json" ] && [ -f "$QWEN_PI_DIR/settings.json" ] \
    && [ -f "$QWEN_PI_DIR/extensions/laya-hook.ts" ] && [ -f "$QWEN_PI_DIR/extensions/voz-hook.ts" ] \
    || _qwen_pi_init >/dev/null || return 1
  _qwen_pi_context >/dev/null || echo "aviso: no pude actualizar $QWEN_PI_DIR/AGENTS.md" >&2
  # Pi solo adjunta imágenes si el modelo las declara en "input"; mismo criterio de calce
  # que _qwenx_up (un mmproj ajeno se descarta allá, así que acá tampoco cuenta).
  local vision=0
  if [ -n "${QWENX_MMPROJ:-}" ]; then
    case "$(basename "${QWENX_MODEL:-}")|$(basename "$QWENX_MMPROJ")" in
      *35B*\|*35B*|*Qwen3.8-4B*\|*Qwen3.8-4B*) vision=1 ;;
    esac
  fi
  python3 - "$QWEN_PI_DIR" "$provider" "$model" "$ctx" "$vision" \
    "${QWENX_TEMP:-0.6}" "${QWENX_TOPP:-0.95}" "${QWENX_TOPK:-20}" "${QWENX_MINP:-0.0}" <<'PY'
import json, os, sys, tempfile
root, provider, model_id = sys.argv[1:4]
ctx = int(sys.argv[4])
vision = sys.argv[5] == "1"
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
m["input"] = ["text", "image"] if vision else ["text"]
m["contextWindow"] = ctx
m["maxTokens"] = min(16384, max(512, ctx // 4))   # con 8192 el thinking se cortaba sin responder
sp_ = m.get("samplingParams")   # solo el proveedor local lo trae: Pi manda el mismo muestreo que llama-server
if isinstance(sp_, dict):
    try:
        sp_.update(temperature=float(sys.argv[6]), top_p=float(sys.argv[7]), top_k=int(sys.argv[8]), min_p=float(sys.argv[9]))
    except ValueError:
        pass
write(mp, d)
s = read(sp)
c = s.setdefault("compaction", {})
c["enabled"] = True
c["reserveTokens"] = min(16384, max(1024, ctx // 6))   # deja sitio para una respuesta de maxTokens
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

# Idioma de respuesta (Parámetro «Idioma» del menú/web → QWEN_IDIOMA). Vacío = auto: el
# modelo contesta en el idioma del mensaje. Va al system prompt de Pi y de Claude; la voz
# (idioma de lectura de kokoro) es otro ajuste, en /voz.html.
_qwen_idioma_prompt() {
  case "${QWEN_IDIOMA:-auto}" in
    español) printf '%s' 'Responde siempre en español, aunque el usuario escriba en otro idioma.' ;;
    inglés)  printf '%s' 'Always reply in English, even if the user writes in another language.' ;;
  esac
}
# Lo mismo como argumentos ya citados, para las líneas de comando que se arman como texto
_qwen_idioma_args_q() {
  local t; t="$(_qwen_idioma_prompt)"
  [ -n "$t" ] && printf -- '--append-system-prompt %q ' "$t"
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
  local -a modo_args=(--tools "$tools")
  # Chat (menú, o modelos con "modo": "chat"): Pi sin herramientas, skills, AGENTS.md, extensiones ni
  # thinking, y con un system prompt neutro en vez del de «coding assistant».
  [ "${QWEN_CHAT:-0}" = 1 ] && modo_args=(--no-tools --no-skills --no-context-files --no-extensions \
    --no-prompt-templates --no-mcp --thinking off \
    --system-prompt 'Eres un compañero de conversación y de juego de rol. Sigue el personaje, el tono y las reglas que te indique el usuario, y escribe en su idioma.')
  # --no-extensions también apaga la voz: con Voz activa se carga solo su extensión
  [ "${QWEN_CHAT:-0}" = 1 ] && [ "${QWEN_VOZ:-0}" = 1 ] && modo_args+=(-e "$QWEN_PI_DIR/extensions/voz-hook.ts")
  [ "${QWEN_PI_NO_SESSION:-0}" = 1 ] && session_args+=(--no-session)
  # Voz activa → la skill de etiquetas va directo al system prompt: con modelos chicos
  # el catálogo de skills no basta (no siempre la leen solos).
  local voz_skill="$QWEN_PI_DIR/skills/voz-etiquetas/SKILL.md"
  [ "${QWEN_VOZ:-0}" = 1 ] && [ -f "$voz_skill" ] && session_args+=(--append-system-prompt "$voz_skill")
  local idioma; idioma="$(_qwen_idioma_prompt)"
  [ -n "$idioma" ] && session_args+=(--append-system-prompt "$idioma")
  PI_CODING_AGENT_DIR="$QWEN_PI_DIR" \
    pi --provider "$provider" --model "$model" "${modo_args[@]}" "${session_args[@]}" "$@"
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

# ── Solo backends, sin pi (para la UI web: lib/../web/web_server.py) ──
# Arranca llama-server(+laya/kev/voz) u Ollama(+laya), sin invocar a pi y sin
# apagar nada al volver: queda vivo hasta `qwen-stop`/botón «Apagar» de la web.
# _qwen_web_launch  model(base|heretic|<id>|ollama|none)  edit  vision  incognito  laya  kev  voz  [carpeta]  [claude]  [kevgpu]  [ctx]  [temp]  [idioma]  [kev: auto|0.8b|4b]
# ctx vacío = QWENX_CTX (120k); temp vacía = 0.6. Los resuelve web_server.py desde los Parámetros.
# «carpeta»: dónde operará Pi cuando se adjunte (fase 2), o la carpeta de Claude si model=none; vacía = QWEN_ROOT.
# Claude (ventana propia) y Kev GPU valen con cualquier modelo, Ollama o none (mismo criterio que _qwen_menu);
# con none solo se levanta kev/laya. Si kev no cabe en la GPU junto al modelo, laya cae a su checkpoint.
_qwen_web_launch() {
  local model="$1" edit="$2" vision="$3" incog="$4" laya="$5" kev="$6" voz="$7" cdir="${8:-}" claude="${9:-0}" kevgpu="${10:-0}"
  local path="" mmproj=""
  [ -n "${11:-}" ] && QWENX_CTX="${11}"
  QWENX_TEMP="${12:-0.6}"
  QWEN_IDIOMA="${13:-auto}"; export QWEN_IDIOMA   # lo usa la ventana de Claude; Pi lo relee en _qwen_web_attach
  if [ -n "$cdir" ]; then
    cd "$cdir" || { echo "No existe la carpeta: $cdir" >&2; return 1; }
  fi
  [ "$incog" = 1 ] && export QWEN_PI_NO_SESSION=1 || export QWEN_PI_NO_SESSION=0
  QWEN_LAYA="$laya"; export QWEN_LAYA
  QWEN_VOZ="$voz"; export QWEN_VOZ
  [ "$kev" = 1 ] && LAYA_BACKEND=kev || LAYA_BACKEND=laya

  _kev_pick "${14:-auto}" "$([ "$model" = none ] && echo 0 || echo 1)"
  if [ "$kevgpu" = 1 ]; then KEV_DEVICE=cuda; else KEV_DEVICE=cpu; fi
  export KEV_DEVICE
  [ "$claude" = 1 ] && { _qwen_claude_window "${cdir:-$QWEN_ROOT}" || return $?; }
  if [ "$model" = none ]; then _laya_up; return $?; fi
  if [ "$model" = ollama ]; then
    _qwen_pi_prepare qwen-ollama "$QWEN_MODEL" "$QWEN_OLLAMA_CTX" || true
    _qwen_up || return $?
    _laya_up || true
    return 0
  fi
  path="$(_qwen_model_path "$model")" || { echo "No encuentro el modelo '$model' en $QWEN_MODELS_DIR" >&2; return 1; }
  if [ "$vision" = 1 ]; then
    mmproj="$(_qwen_mmproj_path "$model")" || { echo "No encuentro el mmproj de '$model' en $QWEN_MODELS_DIR" >&2; return 1; }
  fi
  QWENX_MODEL="$path" QWENX_MMPROJ="$mmproj" _qwen_pi_prepare "$QWEN_PI_PROVIDER" "$QWEN_ALIAS" "$QWENX_CTX" || true
  QWENX_MODEL="$path" QWENX_MMPROJ="$mmproj" _qwenx_up
}

# ── Adjuntar pi al backend YA levantado (fase 2 de la UI web) ──
# A diferencia de _qwen_run_local/_qwen_run_ollama, esta función NO arranca ni
# apaga nada: asume que _qwen_web_launch (u otra sesión) ya dejó los backends
# arriba, y solo corre `pi` contra ellos. Pensada para que la invoque el puente
# PTY↔WebSocket de web/web_server.py.
# Decide Ollama vs llama.cpp local leyendo el mismo archivo de estado que usa
# el menú TUI (menu/qwen_menu/system.py): única fuente de verdad compartida.
# _qwen_web_attach  profile(readonly|edit)
_qwen_web_attach() {
  local profile="${1:-readonly}"
  local state_file="${XDG_STATE_HOME:-$HOME/.local/state}/qwen/menu.json"
  local ollama=0 incognito=0 voz=0 idioma=auto cdir="" flags
  if [ -f "$state_file" ]; then
    flags="$(python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    o = d.get("opts", {})
    ollama = 1 if o.get("ollama") else 0
    incognito = 1 if o.get("incognito") else 0
    voz = 1 if o.get("voz") else 0
    cdir = d.get("cdir") or ""
    idioma = (d.get("params") or {}).get("idioma") or "auto"
    print(f"{ollama}\t{incognito}\t{voz}\t{idioma}\t{cdir}")
except Exception:
    print("0\t0\t0\tauto\t")
' "$state_file" 2>/dev/null)"
    IFS=$'\t' read -r ollama incognito voz idioma cdir <<<"$flags"
  fi
  [ -n "$cdir" ] && [ -d "$cdir" ] && cd "$cdir"
  [ "$incognito" = 1 ] && export QWEN_PI_NO_SESSION=1 || export QWEN_PI_NO_SESSION=0
  QWEN_VOZ="$voz"; export QWEN_VOZ   # _qwen_pi carga la skill de etiquetas si es 1
  QWEN_IDIOMA="$idioma"; export QWEN_IDIOMA
  if [ "$ollama" = 1 ]; then
    _qwen_pi "$profile" qwen-ollama "$QWEN_MODEL"
  else
    _qwen_pi "$profile" "$QWEN_PI_PROVIDER" "$QWEN_ALIAS"
  fi
}
