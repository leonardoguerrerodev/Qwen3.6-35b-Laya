#!/usr/bin/env node
// Lanzador de little-coder sobre el Pi fijo de esta carpeta (node_modules, versión en package.json).
// Reemplaza al original (533 líneas): arma el mismo comando de Pi, pero sin buscar actualizaciones, sin parchear
// el código de Pi (la reparación de `edit` es la extensión edit-repair) y sin escribir en ~/.pi/agent.
// Lo usan lib/lc.sh y los sub-agentes (subagent/spawn.ts busca <raíz>/bin/little-coder.mjs).
import { spawn } from "node:child_process";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const piPkg = join(root, "node_modules", "@earendil-works", "pi-coding-agent");
let piEntry;
try {
	const { bin } = JSON.parse(readFileSync(join(piPkg, "package.json"), "utf8"));
	piEntry = join(piPkg, typeof bin === "string" ? bin : bin.pi);
} catch {
	console.error(`little-coder: falta Pi en ${piPkg}. Instálalo: (cd "${root}" && npm ci --ignore-scripts)`);
	process.exit(1);
}

// Una extensión = un .ts/.js/.mjs o una carpeta con index.ts/index.js (como el original)
const extensiones = (dir) => {
	if (!dir || !existsSync(dir)) return [];
	return readdirSync(dir).sort().flatMap((n) => {
		const p = join(dir, n);
		if (n.startsWith(".") || n === "node_modules") return [];
		if (statSync(p).isDirectory()) return ["index.ts", "index.js"].map((i) => join(p, i)).filter(existsSync).slice(0, 1);
		return /\.(ts|js|mjs)$/.test(n) && !/\.test\./.test(n) ? [p] : [];
	});
};
const bundled = extensiones(join(root, ".pi", "extensions"));
const user = extensiones(process.env.LITTLE_CODER_EXTENSIONS_DIR); // cargan después: pueden pisar a las de arriba

const propios = new Set(["--no-update-check", "--update", "--with-pi-extensions", "--plan-mode"]);
const argv = process.argv.slice(2);
if (argv.includes("--plan-mode")) process.env.LITTLE_CODER_PLAN_MODE = "1";
const userArgs = argv.filter((a) => !propios.has(a));
const headless = process.env.LITTLE_CODER_SUBAGENT === "1" || userArgs.includes("--mode") || userArgs.includes("-p");
const eligioNivel = userArgs.includes("--thinking") || userArgs.some((a, i) => a === "--model" && /:/.test(userArgs[i + 1] ?? ""));

process.env.PI_SKIP_VERSION_CHECK ??= "1";
process.env.LITTLE_CODER_EXTENSION_MANIFEST = JSON.stringify({
	bundled, env: [], user, userDir: process.env.LITTLE_CODER_EXTENSIONS_DIR ?? null,
	userDirExists: user.length > 0, warnings: [], piDiscovery: false,
});

const piArgs = [
	"--no-context-files", "--no-extensions", "--system-prompt", join(root, "AGENTS.md"),
	...(!eligioNivel && !headless ? ["--thinking", "medium"] : []),
	...[...bundled, ...user].flatMap((e) => ["--extension", e]),
	...userArgs,
];
const child = spawn(process.execPath, [piEntry, ...piArgs], { stdio: "inherit" });
for (const s of ["SIGINT", "SIGTERM", "SIGHUP"]) process.on(s, () => { try { child.kill(s); } catch {} });
child.on("error", (e) => { console.error("little-coder: no pude arrancar Pi:", e.message); process.exit(1); });
child.on("exit", (code, signal) => (signal ? process.kill(process.pid, signal) : process.exit(code ?? 0)));
