/**
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

const VOZ_PORT = 8778;
const WEB_PORT = 8780;

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
