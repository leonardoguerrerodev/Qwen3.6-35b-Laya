/**
 * edit-repair — reemplaza el parche 2 del little-coder original (scripts/patch-pi.mjs, issue #127), que en Pi 1.x
 * ya no encuentra su ancla y se salta sin avisar. Un modelo chico manda a veces `edits` como texto JSON con saltos
 * de línea crudos dentro de oldText/newText: JSON.parse falla, Pi se lo traga y la validación rechaza el edit
 * (`edits.0: must be object`). Como la validación corre antes que cualquier hook, se repara donde Pi prepara los
 * argumentos: la herramienta `edit` se registra de nuevo (Pi deja pisar las suyas) con su misma definición.
 */
import { createEditToolDefinition, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Escapa CR, LF y TAB que estén DENTRO de strings JSON; deja el resto igual. Copiada de patch-pi.mjs. */
export function repararControles(texto: string): string {
	let out = "", enStr = false, esc = false;
	for (const ch of texto) {
		if (esc) { out += ch; esc = false; continue; }
		if (ch === "\\") { out += ch; esc = true; continue; }
		if (ch === '"') { enStr = !enStr; out += ch; continue; }
		if (enStr && ch === "\n") { out += "\\n"; continue; }
		if (enStr && ch === "\r") { out += "\\r"; continue; }
		if (enStr && ch === "\t") { out += "\\t"; continue; }
		out += ch;
	}
	return out;
}

export default function (pi: ExtensionAPI) {
	const original = createEditToolDefinition(process.cwd());
	pi.registerTool({
		...original,
		prepareArguments(args: unknown) {
			const a = args as { edits?: unknown } | null;
			if (a && typeof a.edits === "string") {
				try { JSON.parse(a.edits); } catch { args = { ...a, edits: repararControles(a.edits) }; }
			}
			return original.prepareArguments ? original.prepareArguments(args) : (args as never);
		},
	});
}
