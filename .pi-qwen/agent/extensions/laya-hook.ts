/**
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

const LAYA_PORT = 8765;
const CONFIG_PATH = "/run/media/xaski/7c0ba586-7758-4419-b3de-f524b9c9a1fb/!GitHub/!Obsedium/Qwen3.6-35b+Laya/laya/config.json";

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
  // Sin pantalla (pi -p, evals) el aviso no lo ve nadie: no se consulta. Con pantalla, la consulta
  // corre aparte y el turno no la espera (antes la esperaba: hasta 1,5 s por mensaje).
  pi.on("before_agent_start", async (event, ctx) => {
    if (!ctx.hasUI || event.messageType !== "user" || !event.prompt?.trim()) return;
    void (async () => { try {
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
      if (avisos.length) ctx.ui.notify("laya: " + avisos.join("; "), "warning");
    } catch {
      // laya nunca debe estorbar.
    } })();
  });
}
