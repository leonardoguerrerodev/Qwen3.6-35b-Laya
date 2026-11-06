// Test de las tarjetas propias de little-coder (documentos, http_json, svg_png, presentaciones) y del tokenizador parchado
// de knowledge-inject. Correr: node --test evals/tarjetas.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

const raiz = new URL("../", import.meta.url);
const ext = new URL("little-coder/.pi/extensions/", raiz);
const { scoreEntry, MIN_SCORE_THRESHOLD } = await import(new URL("knowledge-inject/index.ts", ext).href);
const { parseSkillFile } = await import(new URL("skill-inject/frontmatter.ts", ext).href);

const NUESTRAS = ["documentos", "http_json", "svg_png", "presentaciones"];
function cargar(n: string) {
	const p = parseSkillFile(readFileSync(new URL(`little-coder/skills/knowledge/${n}.md`, raiz), "utf-8"));
	assert.ok(p, `${n}: frontmatter ilegible`);
	const fm = p.frontmatter;
	return { fm, body: p.body, entry: { topic: String(fm.topic), body: p.body, tokenCost: Number(fm.token_cost),
		keywords: (fm.keywords as string[]).map((k) => k.toLowerCase()), requiresTools: (fm.requires_tools as string[]) ?? [] } };
}
const tarjeta = Object.fromEntries(NUESTRAS.map((n) => [n, cargar(n)]));
const disparadas = (t: string) => NUESTRAS.filter((n) => scoreEntry(t, tarjeta[n].entry) >= MIN_SCORE_THRESHOLD);
const e = (kw: string[]) => ({ topic: "t", body: "b", tokenCost: 0, keywords: kw, requiresTools: [] });

test("tokenizador: corta por signos, no por partes de palabra", () => {
	assert.equal(scoreEntry("lee ~/Clase/TI3V23.pdf", e(["pdf"])), 1);
	assert.equal(scoreEntry("¿y el pdf?", e(["pdf"])), 1);
	assert.equal(scoreEntry("many buckets here", e(["bucket"])), 0);
	assert.equal(scoreEntry("usa rsvg-convert", e(["rsvg-convert"])), 1);
	assert.equal(scoreEntry("minimum moves to solve", e(["minimum moves"])), 2);
});

test("formato de las tarjetas", () => {
	for (const n of NUESTRAS) {
		const { fm, body } = tarjeta[n];
		assert.equal(fm.type, "domain-knowledge", n);
		assert.ok(fm.topic, n);
		assert.ok(Number(fm.token_cost) > 0 && Number(fm.token_cost) <= 150, `${n}: token_cost`);
		assert.deepEqual(fm.requires_tools, ["bash"], n);
		const est = Math.ceil(body.length / 3.5);
		assert.ok(est <= 250, `${n}: cuerpo de ~${est} tokens (tope 250)`);
	}
});

test("pedidos que deben cargar cada tarjeta", () => {
	const casos: [string, string][] = [
		["lee ~/Documentos/Clase/Semestre_II/06_Metodologia_agil/00_Ramo/TI3V23.pdf y resume la unidad 1", "documentos"],
		["hazme un informe en pdf con esta tabla", "documentos"],
		["convierte Resumen_Metodologia_Agil_Scrum.docx a pdf", "documentos"],
		["pasa estas notas a un documento word", "documentos"],
		["consulta la api con curl y filtra la respuesta con jq", "http_json"],
		["revisa qué devuelve https://panel.obsedium.cl/api/pedidos", "http_json"],
		["saca los nombres de data.json con jq", "http_json"],
		["convierte figura.svg a png", "svg_png"],
		["exporta los diagramas svg a png para el informe", "svg_png"],
		["hazme una presentación de scrum para la clase", "presentaciones"],
		["arma 5 diapositivas sobre los roles de scrum", "presentaciones"],
		["convierte notas.md a pptx", "presentaciones"],
		["necesito un powerpoint del informe", "presentaciones"],
	];
	for (const [t, n] of casos)
		assert.ok(disparadas(t).includes(n), `«${t}» debería cargar ${n}; cargó: ${disparadas(t).join(", ") || "ninguna"}`);
});

test("pedidos que no deben cargar ninguna", () => {
	for (const t of [
		"agrega un botón de pausa al juego snake",
		"el servidor crashea al arrancar",
		"revisa el código de snake.py para mejorarlo",
		"crea hola.py que imprima hola",
		"lee el package.json y dime las dependencias",
		"la figura del personaje se ve borrosa",
		"mejora la presentación del menú del juego",
		// las rutas de Leo traen «Documentos»: no debe sumar (por eso la tarjeta solo tiene «documento», en singular)
		"/home/xaski/Documentos/!GitHub/!Obsedium/QwenLocal/Snake/ convierte snake.py a typescript",
	]) assert.deepEqual(disparadas(t), [], `«${t}»`);
});

test("las skills que autocarga el kit no disparan tarjetas con su propio texto", () => {
	for (const s of ["diagnosticar", "planificar", "etapas", "revisar"]) {
		const t = readFileSync(new URL(`.pi-qwen/agent/skills/${s}/SKILL.md`, raiz), "utf-8");
		assert.deepEqual(disparadas(t), [], `${s}/SKILL.md`);
	}
});

test("ninguna palabra clave de las tarjetas originales lleva signos que ahora cortan", () => {
	for (const pack of ["knowledge", "protocols"]) {
		const dir = new URL(`little-coder/skills/${pack}/`, raiz);
		for (const f of readdirSync(dir).filter((f) => f.endsWith(".md"))) {
			const kws = (parseSkillFile(readFileSync(new URL(f, dir), "utf-8"))?.frontmatter.keywords as string[]) ?? [];
			for (const k of kws) if (!k.includes(" ")) assert.ok(!/[\/.,;:!?()"'`¿¡]/.test(k), `${pack}/${f}: «${k}»`);
		}
	}
});
