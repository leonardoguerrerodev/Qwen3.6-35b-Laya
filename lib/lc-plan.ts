/**
 * lc-plan.ts — el modo plan de little-coder (ctrl+q) a la manera del kit (lib/lc.sh):
 *   plan aprobado → además de su .pi/approved-plan.md, se copia a tareas/NNN-<tema>.md del proyecto, visible y
 *                   versionable, y se ejecuta por etapas con la skill etapas («etapa 1 de tareas/NNN-…md», luego /sigue N).
 *                   El formato por etapas lo pide oficio.md (lib/lc.sh). /implement sigue sirviendo para hacerlo de una.
 *   sub-agentes  → razonamiento low: solo leen y resumen; la síntesis del plan (agente principal) queda en su nivel.
 * Corre después de plan-mode (carpeta de usuario): Pi espera cada handler en orden, así que en agent_end la
 * aprobación ya se respondió y el archivo ya se escribió.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { copyFileSync, mkdirSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const tema = (plan: string) =>
	(plan.match(/^#+\s*(.+)$/m)?.[1] ?? plan.split("\n").find((l) => l.trim()) ?? "plan")
		.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
		.replace(/^(plan( de implementacion)?|implementation plan)\b[\s:—-]*/, "")
		.replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40).replace(/-$/, "") || "plan";

export default function (pi: ExtensionAPI) {
	if (process.env.LITTLE_CODER_SUBAGENT === "1") {
		pi.on("session_start", async () => pi.setThinkingLevel("low"));
		return;
	}
	const mtime = (p: string) => { try { return statSync(p).mtimeMs; } catch { return 0; } };
	let antes = 0;
	pi.on("before_agent_start", async (_e, ctx) => { antes = mtime(join(ctx.cwd, ".pi", "approved-plan.md")); });
	pi.on("agent_end", async (_e, ctx) => {
		const origen = join(ctx.cwd, ".pi", "approved-plan.md");
		if (mtime(origen) <= antes) return; // este turno no aprobó un plan
		const dir = join(ctx.cwd, "tareas");
		mkdirSync(dir, { recursive: true });
		const n = Math.max(0, ...readdirSync(dir).map((f) => Number(f.match(/^(\d{3})-/)?.[1] ?? 0))) + 1;
		const destino = join("tareas", `${String(n).padStart(3, "0")}-${tema(readFileSync(origen, "utf-8"))}.md`);
		copyFileSync(origen, join(ctx.cwd, destino));
		antes = mtime(origen);
		if (ctx.hasUI) ctx.ui.notify(`Plan guardado en ${destino} · por etapas: «etapa 1 de ${destino}», después /sigue 2… · todo de una: /implement`, "info");
	});
}
