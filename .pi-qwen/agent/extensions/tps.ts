/**
 * tps: velocidad del modelo en la barra de estado de Pi, sin terminales aparte.
 *
 *   mientras escribe   ~N tok/s, contando deltas (llama-server manda ~1 token por delta: estimado)
 *   al terminar        N tok/s con el conteo real (usage.output) + prefill: tokens nuevos del prompt
 *                      (usage.input, sin la caché) / espera hasta el primer token
 *
 * Fuente: Nobara, ~/.pi-qwen/agent/extensions/tps.ts (el Mac la recibe con qwen-remoto.sh sync).
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const DELTAS = new Set(["text_delta", "thinking_delta", "toolcall_delta"]);

export default function (pi: ExtensionAPI) {
	let inicio = 0, primero = 0, deltas = 0, pintado = 0;

	pi.on("message_start", async (event, ctx) => {
		if (event.message.role !== "assistant" || !ctx.hasUI) return;
		inicio = Date.now(); primero = 0; deltas = 0; pintado = 0;
		ctx.ui.setStatus("tps", "⏱ leyendo el prompt…");
	});

	pi.on("message_update", async (event, ctx) => {
		if (!ctx.hasUI || !DELTAS.has(event.assistantMessageEvent.type)) return;
		const ahora = Date.now();
		if (!primero) primero = pintado = ahora;
		deltas++;
		if (ahora - pintado < 500) return;   // repinta 2 veces por segundo; la 1.ª a los 500 ms (antes es ruido)
		pintado = ahora;
		ctx.ui.setStatus("tps", `⚡ ~${(deltas / ((ahora - primero) / 1000)).toFixed(1)} tok/s · ${deltas} tok`);
	});

	pi.on("message_end", async (event, ctx) => {
		const m = event.message;
		if (m.role !== "assistant" || !ctx.hasUI) return;
		if (!primero) return ctx.ui.setStatus("tps", undefined);   // error o cancelado antes del primer token
		const gen = (Date.now() - primero) / 1000, pre = (primero - inicio) / 1000;
		const salida = m.usage?.output || deltas, prompt = m.usage?.input ?? 0;
		const prefill = prompt && pre > 0 ? ` · prefill ${Math.round(prompt / pre)} tok/s (${prompt} en ${pre.toFixed(1)} s)` : "";
		ctx.ui.setStatus("tps", `⚡ ${(salida / gen).toFixed(1)} tok/s (${salida} tok)${prefill}`);
	});
}
