// Test de la extensión oficio (autocarga de skills y guardas).
// Correr: node --test evals/oficio.test.ts   (otra ruta: OFICIO_TS=/ruta/oficio.ts node --test …)
import { test } from "node:test";
import assert from "node:assert/strict";

const ruta = process.env.OFICIO_TS ?? new URL("../.pi-qwen/agent/extensions/oficio.ts", import.meta.url).href;
const { elegirSkill, bloqueoPkill, pistaSalida } = await import(ruta.startsWith("file:") ? ruta : `file://${ruta}`);

test("elegirSkill con pedidos reales de las sesiones", () => {
	const casos: [string, string | undefined][] = [
		[
			"/home/xaski/Documentos/!GitHub/!Obsedium/QwenLocal/Snake/ aqui etsamos desarrollando un juego clon de \"snake 2\" de los nokia antiguos. /tmp/pi-clipboard-7ef2.png esta es una imagen. Revisa el codigo en el snake.py para mejorarlo",
			"revisar",
		],
		[
			"(venv) xaski@xaski-macpro:~/Snake$ python Snake.py\npygame 2.6.1 (SDL 2.32.10, Python 3.14.4)\nViolación de segmento     (`core' generado) python Snake.py\n el juegono arranca, abre la vetana y se cierra",
			"diagnosticar",
		],
		["no hagas nada tu, solo responde. por que me tira error? (venv) $ pip install pygame\n  error: subprocess-exited-with-error", "diagnosticar"],
		["el juego crashea al abrir", "diagnosticar"],
		["hay un bug en el parser cuando la línea está vacía", "diagnosticar"],
		["antes andaba y ahora no", "diagnosticar"],
		["arreglamelo", undefined],
		["requiere venv? de ser asi dame el comando para instalarlo", undefined],
		["continúa: etapa 3", "etapas"],
		["trabaja la tarjeta tareas/003-mochila.md por etapas", "etapas"],
		["agrega un menú de inicio con Jugar y Salir y que guarde la configuración en un json", "planificar"],
		["crea hola.py", undefined],
		["agrega manejo de errores al parser", undefined],
		["corrige los errores de ortografía del README", undefined],
		["revisa los cambios de Snake.py", "revisar"],
		[
			"en el archivo junto, run.sh pon el codigo para arrancar el venv y arrancar el juego en un script, que al cerrar la ventana se cierra el venv junto aljuego",
			undefined,
		],
	];
	for (const [pedido, esperado] of casos) assert.equal(elegirSkill(pedido), esperado, pedido);
});

test("bloqueoPkill: bloquea lo que mata a la propia shell", () => {
	for (const cmd of [
		'pkill -f "python Snake.py"',
		'cd ~/Snake && source venv/bin/activate && python Snake.py 2>&1 &\nsleep 2\npkill -f "python Snake.py" 2>/dev/null',
		"pgrep -af llama",
		"until ! pgrep -f servidor; do sleep 1; done",
		"sudo pkill --full uvicorn",
	])
		assert.ok(bloqueoPkill(cmd), cmd);
});

test("bloqueoPkill: deja pasar lo seguro", () => {
	for (const cmd of [
		"pkill -f '[p]ython Snake.py'",
		"pkill python",
		"python juego.py & pid=$!; sleep 2; kill $pid",
		'grep -n "pkill -f" notas.md',
		'echo "no uses pkill -f"',
		"timeout 10 python juego.py; echo \"exit=$?\"",
	])
		assert.equal(bloqueoPkill(cmd), undefined, cmd);
});

test("pistaSalida: códigos por señal sí, errores normales no", () => {
	assert.match(pistaSalida("(no output)\n\nCommand exited with code 143") ?? "", /143.*NO es éxito/s);
	assert.match(pistaSalida("Violación de segmento\n\nCommand exited with code 139") ?? "", /diagnosticar/);
	assert.match(pistaSalida("\n\nCommand exited with code 124") ?? "", /timeout/);
	assert.match(pistaSalida("Command timed out after 10 seconds") ?? "", /NO es éxito/);
	assert.equal(pistaSalida("Traceback…\nNameError: x\n\nCommand exited with code 1"), undefined);
	assert.equal(pistaSalida("todo bien"), undefined);
});
