/**
 * lc-permisos.ts — permisos de la terminal para little-coder (lib/lc.sh). Su modo auto bloqueaba sin preguntar
 * todo lo que no está en su lista blanca (en la prueba: `cd` y `rm`, un turno perdido cada uno). Aquí:
 *   en la lista blanca (la suya, importada: una sola fuente)  → pasa
 *   fuera de la lista                                         → te pregunta: Sí · Sí y no preguntar más por ese programa · No
 *   sin pantalla (pi -p, evals)                               → se bloquea como antes: no hay a quién preguntar
 * Su permission-gate queda en accept-all (lo pone lib/lc.sh); los sub-agentes (plan mode) siguen con el suyo en auto.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

type Gate = { isSafeBash(c: string): boolean; splitCommandChain(c: string): string[]; detectWriteTargets(c: string): unknown[] };
const SHELL = new Set(["bash", "Bash", "ShellSession", "ShellStart"]);

// "FOO=1 npm test" → "npm"
const programa = (segmento: string) => segmento.trim().split(/\s+/).find((w) => !/^\w+=/.test(w)) ?? segmento.trim();

export default function (pi: ExtensionAPI) {
	if (process.env.LITTLE_CODER_SUBAGENT === "1") return;
	const ext = `${process.env.QWEN_LC_PKG ?? ""}/.pi/extensions`;
	let gate: Promise<Gate | undefined> | undefined;
	const cargar = () =>
		(gate ??= Promise.all([import(`${ext}/permission-gate/index.ts`), import(`${ext}/_shared/shell-write.ts`)])
			.then(([p, s]) => ({ isSafeBash: p.isSafeBash, splitCommandChain: s.splitCommandChain, detectWriteTargets: s.detectWriteTargets }))
			.catch(() => undefined)); // sin la lista: se pregunta todo
	const permitidos = new Set<string>(); // programas autorizados para el resto de la sesión
	pi.on("session_start", async () => permitidos.clear());

	pi.on("tool_call", async (event, ctx) => {
		if (!SHELL.has(event.toolName)) return;
		const cmd = String((event.input as { command?: unknown }).command ?? "");
		const g = await cargar();
		if (g?.isSafeBash(cmd)) return;
		// programas fuera de la lista; vacío = sin lista o escribe a un archivo (`> x`, tee): se pregunta siempre
		const fuera = g && !g.detectWriteTargets(cmd).length ? [...new Set(g.splitCommandChain(cmd).filter((s) => !g.isSafeBash(s)).map(programa))] : [];
		if (fuera.length && fuera.every((p) => permitidos.has(p))) return;
		if (!ctx.hasUI)
			return {
				block: true,
				reason: `Bloqueado: fuera de la lista blanca (${fuera.map((p) => `«${p}»`).join(", ") || "escribe a un archivo"}) y no hay a quién preguntar (sesión sin pantalla).`,
			};
		const SI = "Sí", NO = "No";
		const SIEMPRE = fuera.length ? `Sí, y no preguntar más por ${fuera.join(", ")} en esta sesión` : "";
		const r = await ctx.ui.select(`¿Ejecutar este comando?\n\n${cmd}`, SIEMPRE ? [SI, SIEMPRE, NO] : [SI, NO]);
		if (r === SIEMPRE) fuera.forEach((p) => permitidos.add(p));
		if (r === SI || r === SIEMPRE) return;
		return {
			block: true,
			reason: "El usuario no autorizó este comando. No busques otra vía para lo mismo: si lo necesitas, explica por qué y pregúntale.",
		};
	});
}
