/**
 * Oficio: carga sola la skill que corresponde al pedido y suma dos guardas
 * para fallos que Qwen tuvo en sesiones reales (nota del vault "Qwen local — Perfil y método de trabajo").
 *
 *   input        "el juego crashea" → "/skill:diagnosticar el juego crashea" (Pi la expande como si se escribiera a mano);
 *                "/sigue N" sin etapas en contexto → "/skill:etapas /sigue N"
 *   tool_call    bloquea pkill/pgrep -f sin corchetes: el patrón también encuentra a la propia shell y la mata (exit 143)
 *   tool_result  explica en el resultado de bash los códigos de salida por señal (124, 139, 143…)
 *   /oficio      estado; /oficio on|off prende o apaga la autocarga; QWEN_AUTOSKILL=0 la apaga al arrancar (evals sin kit)
 *
 * Fuente: Nobara, ~/.pi-qwen/agent/extensions/oficio.ts. Test: Qwen3.6-35b+Laya/evals/oficio.test.ts.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

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

// ── Extensión ─────────────────────────────────────────────────────────────────

export default function oficio(pi: ExtensionAPI): void {
	let autocarga = process.env.QWEN_AUTOSKILL !== "0";
	const cargadas = new Set<string>(); // skills ya inyectadas en esta sesión

	pi.on("session_start", async () => cargadas.clear());
	pi.on("session_compact", async () => cargadas.clear()); // el bloque de la skill pudo quedar resumido

	pi.on("input", async (event, ctx) => {
		if (event.source === "extension") return { action: "continue" };
		const cmd = event.text.match(RE_COMANDO);
		if (cmd?.[1].startsWith("skill:")) cargadas.add(cmd[1].slice("skill:".length));
		// La plantilla /sigue solo nombra etapas. Si etapas no está en contexto (sesión nueva o tras compactar), se
		// antepone y "/sigue N" llega literal (Pi expande /skill: antes que las plantillas); etapas lo lee en su paso 1.
		const skill = cmd ? (cmd[1] === "sigue" ? "etapas" : undefined) : elegirSkill(event.text);
		if (!autocarga || !skill || cargadas.has(skill)) return { action: "continue" };
		if (!pi.getCommands().some((c) => c.name === `skill:${skill}`)) return { action: "continue" };
		cargadas.add(skill);
		if (ctx.hasUI) ctx.ui.notify(`oficio: skill ${skill} cargada`, "info");
		return { action: "transform", text: `/skill:${skill} ${event.text}`, images: event.images };
	});

	pi.on("tool_call", async (event) => {
		if (event.toolName !== "bash") return;
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

	pi.registerCommand("oficio", {
		description: "Kit de oficio: autocarga de skills y guardas (/oficio on|off)",
		handler: async (args, ctx) => {
			const a = args.trim().toLowerCase();
			if (a === "on" || a === "off") autocarga = a === "on";
			const lista = [...cargadas].join(", ") || "ninguna";
			ctx.ui.notify(
				`oficio: autocarga ${autocarga ? "on" : "off"} · skills cargadas: ${lista} · guardas: pkill/pgrep -f, códigos de salida`,
				"info",
			);
		},
	});
}
