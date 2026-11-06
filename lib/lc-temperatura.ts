/**
 * lc-temperatura.ts — para little-coder (lib/lc.sh). Su extensión benchmark-profiles fija la temperatura
 * (0.3) desde la settings.json de su propio paquete, sin forma de cambiarla por fuera. Esta carga después
 * (carpeta de extensiones del usuario) y pone la del perfil del launcher: QWEN_LC_TEMP. Vacía = no toca nada.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
	const raw = process.env.QWEN_LC_TEMP ?? "";
	const t = Number(raw);
	if (raw === "" || !Number.isFinite(t)) return;
	pi.on("before_provider_request", async (event) => {
		const p: any = (event as any).payload;
		if (p && typeof p === "object") return { ...p, temperature: t };
	});
}
