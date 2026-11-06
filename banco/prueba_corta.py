#!/usr/bin/env python3
"""Prueba corta de calidad, razonamiento y velocidad: 6 tareas con respuesta verificable, razonamiento activado.

Lanza cada modelo con el MISMO comando que el menú (flags.build_cmd + su perfil activo en profiles.json),
en el puerto 8077 para no pisar al :8001. Uso:
  python3 banco/prueba_corta.py                 # base, heretic y q38
  python3 banco/prueba_corta.py q38 -n 3        # un modelo, 3 rondas (con temperatura > 0 una ronda es ruidosa)
Resultado en pantalla y en banco/resultados/AAAA-MM-DD_HHMM.md
"""
import argparse, datetime, itertools, json, os, re, subprocess, sys, tempfile, time, urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "menu"))
from qwen_menu import flags, profiles  # noqa: E402

PUERTO = "8077"
M = os.path.expanduser("~/models")
MODELOS = {  # id del menú → GGUF (mismos archivos que resuelve lib/config.sh)
    "base": ("Qwen3.6-35B-A3B Q4_K_XL", f"{M}/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"),
    "heretic": ("Qwen3.6-35B-A3B heretic Q4_K_M", f"{M}/Qwen3.6-35B-A3B-uncensored-heretic-Native-MTP-Preserved-Q4_K_M.gguf"),
    "q38": ("Qwen3.8-27B IQ3_XXS", f"{M}/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-mtp.gguf"),
}
FIN = "\n\nPuedes explicar brevemente; la última línea de tu respuesta debe ser exactamente: RESPUESTA: <respuesta>"
# ojo: nada de «responde solo X» junto a FIN; la contradicción hace que el modelo razone en bucle (5-nov-2026)


# ---------- tareas: (nombre, qué mide, prompt, verificador(texto) -> bool) ----------
def respuesta(t):
    m = re.findall(r"RESPUESTA:\s*(.+)", t)
    return m[-1].strip().strip("*`. ") if m else ""


def numero(t):
    return re.sub(r"[^\d]", "", respuesta(t).split(",")[0])


def escalones_ref(n):  # pasos de 1, 2 o 3, sin dos pasos de 3 seguidos
    f = {}

    def g(r, prev3):
        if r == 0:
            return 1
        if (r, prev3) not in f:
            f[r, prev3] = sum(g(r - s, s == 3) for s in (1, 2, 3) if s <= r and not (s == 3 and prev3))
        return f[r, prev3]
    return g(n, False)


def verif_codigo(t):
    bloques = re.findall(r"```(?:python)?\n(.*?)```", t, re.S)
    if not bloques:
        return False
    casos = {n: escalones_ref(n) for n in (0, 1, 2, 3, 4, 5, 6, 7, 10, 15, 25)}
    prueba = bloques[-1] + "\n" + "".join(f"assert formas({n}) == {v}, ({n}, formas({n}))\n" for n, v in casos.items())
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.py")
        open(p, "w").write(prueba)
        try:
            return subprocess.run([sys.executable, "-I", p], cwd=d, capture_output=True, timeout=20).returncode == 0
        except subprocess.TimeoutExpired:
            return False


METALES = ["oro", "plata", "cobre", "titanio"]  # de más caro a más barato
PERSONAS = ["Ana", "Bea", "Cata", "Dani"]


def puzzle_soluciones():
    sols = []
    for perm in itertools.permutations(METALES):
        a = dict(zip(PERSONAS, perm))
        quien = {v: k for k, v in a.items()}
        if (a["Ana"] not in ("oro", "plata") and quien["cobre"] in ("Bea", "Dani") and a["Bea"] != "cobre"
                and METALES.index(a["Bea"]) > METALES.index(a["Cata"]) and a["Dani"] != "titanio"):
            sols.append(a)
    return sols


SOL = puzzle_soluciones()
assert len(SOL) == 1, SOL  # el acertijo tiene solución única
SOL = SOL[0]


def verif_puzzle(t):
    r = respuesta(t).lower()
    return all(re.search(rf"{p.lower()}\W*(?:=|:|-|usa)?\W*{m}", r) for p, m in SOL.items())


def verif_instrucciones(t):
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip()
    oraciones = [o.strip() for o in re.split(r"(?<=[.!?])\s+", t) if o.strip()]
    if len(oraciones) != 3 or "z" in t.lower():
        return False
    if not oraciones[1].startswith("Guarda"):
        return False
    return all(8 <= len(re.findall(r"\b[\wáéíóúñü]+\b", o)) <= 14 for o in oraciones)


TAREAS = [
    ("costo", "aritmética de varios pasos",
     "Un anillo de plata 950 pesa 6,4 g (95 % plata fina, 5 % cobre). La plata fina cuesta $1.120 por gramo y el "
     "cobre $15 por gramo. La mano de obra son 2,5 horas a $9.000 la hora. Precio = costo total × 1,6, y a eso se le "
     "suma IVA del 19 %. ¿Cuál es el precio final en pesos, redondeado al peso más cercano? La respuesta es solo el número."
     + FIN, lambda t: numero(t) == "55815"),
    ("trampa", "no caer en la respuesta intuitiva",
     "Un anillo y su estuche cuestan juntos $26.000. El anillo cuesta $20.000 más que el estuche. "
     "¿Cuánto cuesta el estuche? La respuesta es solo el número." + FIN, lambda t: numero(t) == "3000"),
    ("fecha", "razonamiento con calendario",
     "Si el 5 de noviembre de 2026 es jueves, ¿qué día de la semana es el 1 de marzo de 2027? "
     "La respuesta es el día en español, en minúsculas." + FIN, lambda t: respuesta(t).lower().startswith("lunes")),
    ("acertijo", "lógica con restricciones",
     "Ana, Bea, Cata y Dani usan cada una un metal distinto: oro, plata, cobre o titanio (precio de mayor a menor en "
     "ese orden). Pistas: 1) Ana no usa oro ni plata. 2) Quien usa cobre es Bea o Dani. 3) Bea no usa cobre. "
     "4) Bea usa un metal más barato que el de Cata. 5) Dani no usa titanio. "
     "¿Qué metal usa cada una? La respuesta va en el formato Ana=metal, Bea=metal, Cata=metal, Dani=metal." + FIN,
     verif_puzzle),
    ("codigo", "programación con casos ocultos",
     "Escribe en Python la función `formas(n: int) -> int` que cuente de cuántas maneras se puede subir una escalera "
     "de n escalones dando pasos de 1, 2 o 3 escalones, con la regla de que nunca puede haber dos pasos de 3 "
     "seguidos. formas(0) = 1. Debe ser eficiente para n hasta 1000. Entrega solo un bloque ```python con la "
     "función, sin tests ni prints.", verif_codigo),
    ("instrucciones", "seguir restricciones de forma",
     "Escribe exactamente 3 oraciones en español sobre cómo cuidar una joya de plata. Cada oración debe tener entre "
     "8 y 14 palabras. No uses la letra z en ninguna parte. La segunda oración debe empezar con la palabra Guarda. "
     "No escribas nada más: ni título, ni listas, ni comentarios.", verif_instrucciones),
]


# ---------- servidor ----------
def comando(mid, gguf):
    perf = profiles.load_all().get(mid, {})
    p = perf.get("perfiles", {}).get(perf.get("activo", "default"), {})
    g = lambda k, d="": str(p.get(k, d) or d)  # noqa: E731
    env = {"MODEL_PATH": gguf, "P_CTX": g("ctx"), "P_TEMP": g("temp", "0.6"), "P_KVQ": g("kvq"),
           "P_TOPP": g("top_p"), "P_TOPK": g("top_k"), "P_MINP": g("min_p"), "P_NCMOE": g("ncmoe"),
           "P_NGL": g("ngl"), "P_LOADMODE": g("loadmode"), "P_BATCH": g("batch"), "P_UB": g("ub"),
           "P_RAZON": g("razon"), "P_EFFORT": g("effort"), "P_MTP": g("mtp", "auto"), "P_DRAFT": g("draft"),
           "P_EXTRA": profiles.extra_words(g("extra"))}
    os.environ["QWEN_PORT"] = PUERTO
    palabras, err = flags.build_cmd(env)
    if not palabras:
        sys.exit(f"{mid}: no se pudo armar el comando: {err}")
    return palabras, perf.get("activo", "default")


def pedir(cuerpo, timeout=900):
    req = urllib.request.Request(f"http://127.0.0.1:{PUERTO}/v1/chat/completions", json.dumps(cuerpo).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def vram():
    try:
        return subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True).stdout.strip() + " MiB"
    except OSError:
        return "?"


def probar(mid, rondas, salida):
    nombre, gguf = MODELOS[mid]
    cmd, perfil = comando(mid, gguf)
    log = open(os.path.join(salida, f"srv-{mid}.log"), "w")
    t0 = time.time()
    srv = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
    try:
        while True:
            if srv.poll() is not None:
                sys.exit(f"{mid}: llama-server murió al cargar (ver {log.name})")
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PUERTO}/health", timeout=2)
                break
            except OSError:
                time.sleep(0.5)
        carga = time.time() - t0
        filas = []
        for ronda in range(rondas):
            for nom, mide, prompt, ok in TAREAS:
                t1 = time.time()
                r = pedir({"messages": [{"role": "user", "content": prompt}], "max_tokens": 12000, "seed": 42 + ronda})
                seg = time.time() - t1
                texto = r["choices"][0]["message"].get("content") or ""
                tim = r.get("timings", {})
                filas.append({"tarea": nom, "ok": bool(ok(texto)), "seg": seg, "tokens": tim.get("predicted_n", 0),
                              "gen_s": tim.get("predicted_ms", 0) / 1000, "corte": r["choices"][0].get("finish_reason")})
                with open(os.path.join(salida, f"{mid}-{nom}-r{ronda + 1}.txt"), "w") as f:
                    f.write((r["choices"][0]["message"].get("reasoning_content") or "") + "\n\n=====\n\n" + texto)
                print(f"  {mid:8} {nom:13} {'✔' if filas[-1]['ok'] else '✘'}  {seg:6.1f} s  "
                      f"{filas[-1]['tokens']:5} tok  {filas[-1]['corte']}", flush=True)
        return {"id": mid, "nombre": nombre, "perfil": perfil, "carga": carga, "vram": vram(), "filas": filas,
                "cmd": " ".join(cmd)}
    finally:
        srv.terminate()
        try:
            srv.wait(30)
        except subprocess.TimeoutExpired:
            srv.kill()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("modelos", nargs="*", default=list(MODELOS), choices=list(MODELOS))
    ap.add_argument("-n", "--rondas", type=int, default=1)
    a = ap.parse_args()
    if subprocess.run(["pgrep", "-f", "llama-server"], capture_output=True).returncode == 0:
        sys.exit("Hay un llama-server corriendo (ocupa la GPU): ciérralo con qwen-stop antes de la prueba.")
    marca = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    salida = os.path.join(RAIZ, "banco", "salida", marca)
    os.makedirs(salida, exist_ok=True)
    res = [probar(m, a.rondas, salida) for m in a.modelos]

    n = len(TAREAS) * a.rondas
    lin = [f"# Prueba corta {marca}", "", f"{len(TAREAS)} tareas × {a.rondas} ronda(s), razonamiento activado, "
           "perfil activo de cada modelo.", "",
           "| Modelo | Perfil | Aciertos | Tiempo total | Tokens | tok/s gen | Carga | VRAM |", "|---|---|---|---|---|---|---|---|"]
    for r in res:
        f = r["filas"]
        tok, gen = sum(x["tokens"] for x in f), sum(x["gen_s"] for x in f)
        lin.append(f"| {r['nombre']} | {r['perfil']} | {sum(x['ok'] for x in f)}/{n} | {sum(x['seg'] for x in f):.0f} s "
                   f"| {tok} | {tok / gen if gen else 0:.1f} | {r['carga']:.0f} s | {r['vram']} |")
    lin += ["", "| Tarea | " + " | ".join(r["id"] for r in res) + " |", "|---" * (len(res) + 1) + "|"]
    for nom, mide, *_ in TAREAS:
        celdas = []
        for r in res:
            xs = [x for x in r["filas"] if x["tarea"] == nom]
            celdas.append(f"{sum(x['ok'] for x in xs)}/{len(xs)} · {sum(x['seg'] for x in xs) / len(xs):.0f} s")
        lin.append(f"| {nom} ({mide}) | " + " | ".join(celdas) + " |")
    lin += ["", "Comandos:", ""] + [f"- `{r['id']}`: `{r['cmd']}`" for r in res]
    os.makedirs(os.path.join(RAIZ, "banco", "resultados"), exist_ok=True)
    with open(os.path.join(RAIZ, "banco", "resultados", f"{marca}.md"), "w") as fh:
        fh.write("\n".join(lin) + "\n")
    print("\n" + "\n".join(lin))


if __name__ == "__main__":
    main()
