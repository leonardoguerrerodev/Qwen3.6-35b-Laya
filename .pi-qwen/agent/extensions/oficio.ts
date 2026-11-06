/**
 * Oficio: carga sola la skill que corresponde al pedido y suma dos guardas
 * para fallos que Qwen tuvo en sesiones reales (nota del vault "Qwen local — Perfil y método de trabajo").
 *
 *   input        "el juego crashea" → "/skill:diagnosticar el juego crashea" (Pi la expande como si se escribiera a mano);
 *                "/sigue N" sin etapas en contexto → "/skill:etapas /sigue N"
 *   tool_call    (bash y ShellStart de little-coder) bloquea pkill/pgrep -f sin corchetes: el patrón también encuentra a la propia shell y la mata (exit 143)
 *   tool_result  explica en el resultado de bash los códigos de salida por señal (124, 139, 143…)
 *   /oficio      estado; /oficio on|off prende o apaga la autocarga; QWEN_AUTOSKILL=0 la apaga al arrancar (evals sin kit)
 *   skills       alt+k (o /oficio sin argumentos): panel para prender y apagar skills, como en Claude. Una apagada sale
 *                de la lista del prompt, no se autocarga, `/skill:x` avisa en vez de cargarla y `read` de su SKILL.md
 *                se bloquea. Se guarda en <carpeta de agente>/skills-off.json (QWEN_SKILLS_OFF lo pisa: little-coder
 *                usa el de Pi, así que el interruptor vale para los dos).
 *
 * Fuente: Nobara, ~/.pi-qwen/agent/extensions/oficio.ts. Test: Qwen3.6-35b+Laya/evals/oficio.test.ts.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

// ── Autocarga ─────────────────────────────────────────────────────────────────

// Se compara en minúsculas y sin tildes ("añade" → "anade", "excepción" → "excepcion").
const normalizar = (t: string) => t.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

const RE_ETAPAS = /tareas\/\d{3}|\betapa\s+\d+/;
const RE_NO_FALLO =
	/\b(manejo|mensajes?|captura|control|gestion|tratamiento|validacion|registro) de (los )?error(es)?\b|\berror(es)? (de )?(ortografia|tipeo|redaccion|ortograficos)\b/g;
const RE_FALLO =
	/\b(error(es)?|traceback|excepcion(es)?|exception|crash\w*|segfault|core dumped|cuelga\w*|colgad[oa]s?|falla\w*|fallo|roto|rota|bugs?|regresion|broken|fails?|failing)\b|violacion de segmento|\bno (funciona|arranca|abre|compila|anda|carga|inicia|corre)\b|\bantes (funcionaba|andaba)\b|not working|does ?n[o']t work/;
const RE_REVISAR = /\b(revis\w*|audit\w*|review\w*)\b/;
const RE_TAREA =
	/\b(implement\w*|agreg\w*|anad\w*|crea|crear|creame|crealo|construy\w*|construir|desarroll\w*|refactor\w*|migr\w*|integr\w*|build|add|haz(me)? una?)\b/;
// Pedido chico ("crea hola.py") no necesita plan: el núcleo de AGENTS.md alcanza.
const MIN_PALABRAS_PLAN = 12;

export type Skill = "etapas" | "diagnosticar" | "revisar" | "planificar";

/** Skill que corresponde al pedido, o undefined. Prioridad: etapas > diagnosticar > revisar > planificar. */
export function elegirSkill(texto: string): Skill | undefined {
	const t = normalizar(texto);
	if (RE_ETAPAS.test(t)) return "etapas";
	if (RE_FALLO.test(t.replace(RE_NO_FALLO, " "))) return "diagnosticar";
	if (RE_REVISAR.test(t)) return "revisar";
	if (RE_TAREA.test(t) && t.split(/\s+/).filter(Boolean).length >= MIN_PALABRAS_PLAN) return "planificar";
	return undefined;
}

// "/sigue 2", "/skill:etapas x", "/rea ruta"; una ruta como "/home/x/…" no es comando.
const RE_COMANDO = /^\/([\w:.-]+)(\s|$)/;

// ── Guarda: pkill/pgrep -f ────────────────────────────────────────────────────

/** Motivo para bloquear el comando, o undefined si es seguro. */
export function bloqueoPkill(comando: string): string | undefined {
	for (const parte of comando.split(/[;&|\n`]|\$\(/)) {
		const m = parte.match(/^\s*(?:(?:sudo|until|while|if|then|do|exec|!)\s+)*(pkill|pgrep)\s+(.*)$/);
		if (!m) continue;
		const [, prog, args] = m;
		if (!/(^|\s)(-[a-zA-Z]*f[a-zA-Z]*|--full)(\s|$)/.test(args)) continue;
		if (/\[[^\]]+\]/.test(args)) continue; // '[p]ython x' no se encuentra a sí mismo
		return (
			`Bloqueado: \`${prog} -f\` busca en la línea de comandos completa y también encuentra tu propia shell ` +
			`(la mata: exit 143), así que no sabrías si el programa funcionó. ` +
			`Usa \`timeout 10 <cmd>; echo "exit=$?"\`, o el PID: \`<cmd> & pid=$!; …; kill $pid\`. ` +
			`Si de verdad necesitas buscar por línea completa, pon corchetes: \`${prog} -f '[p]ython juego.py'\`.`
		);
	}
	return undefined;
}

// ── Pista: códigos de salida ──────────────────────────────────────────────────

const NO_EXITO = " Esto NO es éxito.";
const SIGNIFICADO: Record<string, string> = {
	"124":
		"124 = lo cortó `timeout` al llegar al límite. Si era un juego o un servidor y arriba no hay traza, solo prueba que no se cayó en ese tiempo; si era un comando normal, se colgó.",
	"126": "126 = no se pudo ejecutar: falta permiso (`chmod +x`) o no es un ejecutable." + NO_EXITO,
	"127": "127 = comando no encontrado: revisa el nombre, la ruta o si está instalado (¿venv? usa `./venv/bin/python`)." + NO_EXITO,
	"130": "130 = interrumpido con Ctrl-C (SIGINT)." + NO_EXITO,
	"134": "134 = abortó (SIGABRT): falló un assert o una librería en C." + NO_EXITO,
	"137": "137 = matado con SIGKILL (kill -9, falta de memoria o un timeout que mata)." + NO_EXITO,
	"139":
		"139 = segfault (SIGSEGV): casi siempre una librería en C o el entorno (paquetes duplicados, versión incompatible), no tu sintaxis. Antes de tocar código, sigue la skill `diagnosticar` (paso 3, entorno)." +
		NO_EXITO,
	"143":
		"143 = terminado con SIGTERM. Si el comando usó `pkill` o `killall`, puede que hayas terminado tu propia shell: no sabes si el programa funcionó." +
		NO_EXITO,
};

/** Pista para el final del resultado de bash, o undefined si el error es uno normal (código 1, 2…). */
export function pistaSalida(texto: string): string | undefined {
	const codigo = texto.match(/Command exited with code (\d+)\s*$/);
	if (codigo) return SIGNIFICADO[codigo[1]];
	const corte = texto.match(/Command timed out after (\d+) seconds\s*$/);
	if (corte)
		return `Pi cortó el comando a los ${corte[1]} s. Si era un programa que no termina, córrelo tú con \`timeout N <cmd>\` y busca una señal; no lo relances igual.${NO_EXITO}`;
	return undefined;
}

// ── Skills apagadas ───────────────────────────────────────────────────────────

const ARCHIVO_APAGADAS =
	process.env.QWEN_SKILLS_OFF || join(process.env.PI_CODING_AGENT_DIR || join(homedir(), ".pi", "agent"), "skills-off.json");

/** Skills apagadas, guardadas entre sesiones. Archivo ausente o roto = ninguna. */
export function leerApagadas(archivo = ARCHIVO_APAGADAS): Set<string> {
	try {
		const v = JSON.parse(readFileSync(archivo, "utf-8"))?.apagadas;
		return new Set(Array.isArray(v) ? v.filter((x: unknown): x is string => typeof x === "string") : []);
	} catch {
		return new Set();
	}
}

const escapar = (t: string) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** El system prompt sin las entradas de las skills apagadas; si no queda ninguna, sin el bloque entero. */
export function quitarSkills(prompt: string, apagadas: Set<string>): string {
	let p = prompt;
	for (const n of apagadas) p = p.replace(new RegExp(`\\n[ \\t]*<skill>\\s*<name>${escapar(n)}</name>[\\s\\S]*?</skill>`, "g"), "");
	return p.replace(/\n*The following skills provide[^<]*<available_skills>\s*<\/available_skills>\n?/, "\n");
}

// ── Extensión ─────────────────────────────────────────────────────────────────

export default function oficio(pi: ExtensionAPI): void {
	let autocarga = process.env.QWEN_AUTOSKILL !== "0";
	const cargadas = new Set<string>(); // skills ya inyectadas en esta sesión
	let apagadas = leerApagadas(); // se relee en cada mensaje: otra sesión (Pi o little-coder) pudo cambiarla

	pi.on("session_start", async () => cargadas.clear());
	pi.on("session_compact", async () => cargadas.clear()); // el bloque de la skill pudo quedar resumido

	// Pi 1.4 arma la lista de skills desde systemPromptOptions.skills; Pi 0.83 (little-coder) no la rearma, así que
	// también se recorta el texto. Mientras no cambie el interruptor, el prompt queda igual turno a turno (caché).
	pi.on("before_agent_start", async (event) => {
		apagadas = leerApagadas();
		if (!apagadas.size) return;
		const o = (event as { systemPromptOptions?: { skills?: { name?: string }[] } }).systemPromptOptions;
		if (Array.isArray(o?.skills)) o.skills = o.skills.filter((s) => !apagadas.has(String(s.name)));
		const prompt = quitarSkills(event.systemPrompt, apagadas);
		if (prompt !== event.systemPrompt) return { systemPrompt: prompt };
	});

	pi.on("input", async (event, ctx) => {
		if (event.source === "extension") return { action: "continue" };
		apagadas = leerApagadas();
		const cmd = event.text.match(RE_COMANDO);
		const pedida = cmd?.[1].startsWith("skill:") ? cmd[1].slice("skill:".length) : undefined;
		if (pedida && apagadas.has(pedida)) {
			if (ctx.hasUI) ctx.ui.notify(`oficio: la skill ${pedida} está apagada (alt+k para prenderla)`, "warning");
			return { action: "handled" };
		}
		if (pedida) cargadas.add(pedida);
		// La plantilla /sigue solo nombra etapas. Si etapas no está en contexto (sesión nueva o tras compactar), se
		// antepone y "/sigue N" llega literal (Pi expande /skill: antes que las plantillas); etapas lo lee en su paso 1.
		const skill = cmd ? (cmd[1] === "sigue" ? "etapas" : undefined) : elegirSkill(event.text);
		if (!autocarga || !skill || cargadas.has(skill) || apagadas.has(skill)) return { action: "continue" };
		if (!pi.getCommands().some((c) => c.name === `skill:${skill}`)) return { action: "continue" };
		cargadas.add(skill);
		if (ctx.hasUI) ctx.ui.notify(`oficio: skill ${skill} cargada`, "info");
		return { action: "transform", text: `/skill:${skill} ${event.text}`, images: event.images };
	});

	// read de una skill apagada; bash, y en little-coder también ShellStart (su proceso de fondo se encuentra a sí mismo igual)
	pi.on("tool_call", async (event) => {
		if (event.toolName === "read") {
			const ruta = String((event.input as { path?: unknown }).path ?? "");
			const n = [...apagadas].find((s) => new RegExp(`(^|/)skills/${escapar(s)}/`).test(ruta));
			if (n) return { block: true, reason: `La skill ${n} está apagada por el usuario: no la leas y sigue sin ella.` };
			return;
		}
		if (event.toolName !== "bash" && event.toolName !== "ShellStart") return;
		const motivo = bloqueoPkill(String((event.input as { command?: unknown }).command ?? ""));
		if (motivo) return { block: true, reason: motivo };
	});

	pi.on("tool_result", async (event) => {
		if (event.toolName !== "bash" || !event.isError) return;
		const texto = event.content.map((c) => (c.type === "text" ? c.text : "")).join("\n");
		const pista = pistaSalida(texto);
		if (!pista) return;
		return {
			content: [...event.content, { type: "text" as const, text: `⚠ ${pista}` }],
			structuredContent: event.structuredContent,
		};
	});

	const estado = () =>
		`oficio: autocarga ${autocarga ? "on" : "off"} · apagadas: ${[...apagadas].sort().join(", ") || "ninguna"} · ` +
		`cargadas en esta sesión: ${[...cargadas].join(", ") || "ninguna"}`;

	// Panel: una fila por skill (● prendida · ○ apagada) y la autocarga. Enter cambia la fila; Esc cierra.
	async function panel(ctx: { ui: { select(t: string, o: string[]): Promise<string | undefined>; notify(m: string, k?: string): void } }) {
		for (;;) {
			apagadas = leerApagadas();
			const nombres = pi.getCommands().filter((c) => c.name.startsWith("skill:")).map((c) => c.name.slice("skill:".length)).sort();
			const filas = nombres.map((n) => (apagadas.has(n) ? `○ ${n}  (apagada)` : `● ${n}`));
			const filaAuto = `${autocarga ? "●" : "○"} autocarga según el pedido (solo esta sesión)`;
			const r = await ctx.ui.select("Skills · Enter prende o apaga · Esc cierra · rige desde tu próximo mensaje", [...filas, filaAuto]);
			if (r === undefined) break;
			if (r === filaAuto) { autocarga = !autocarga; continue; }
			const n = nombres[filas.indexOf(r)];
			if (!n) break;
			if (apagadas.has(n)) apagadas.delete(n); else apagadas.add(n);
			try {
				writeFileSync(ARCHIVO_APAGADAS, JSON.stringify({ apagadas: [...apagadas].sort() }, null, 2) + "\n");
			} catch (e) {
				ctx.ui.notify(`oficio: no pude guardar ${ARCHIVO_APAGADAS}: ${(e as Error).message}`, "error");
				return;
			}
		}
		ctx.ui.notify(estado(), "info");
	}

	pi.registerShortcut("alt+k", { description: "Prender o apagar skills (oficio)", handler: async (ctx) => panel(ctx) });

	pi.registerCommand("oficio", {
		description: "Kit de oficio: panel de skills (igual que alt+k); /oficio on|off prende o apaga la autocarga",
		handler: async (args, ctx) => {
			const a = args.trim().toLowerCase();
			if (a === "on" || a === "off") autocarga = a === "on";
			else if (!a && ctx.hasUI) return panel(ctx);
			apagadas = leerApagadas();
			ctx.ui.notify(`${estado()} · guardas: pkill/pgrep -f, códigos de salida`, "info");
		},
	});
}
