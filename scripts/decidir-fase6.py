#!/usr/bin/env python3
# decidir-fase6.py — aplica los umbrales y la regla de decisión del plan a lo que dejó bench-qwen.sh
# Solo LEE archivos (no toca la GPU ni ~/.qwen-local.sh): se puede ejecutar mientras corre otra cosa.
# Uso: python3 scripts/decidir-fase6.py   (lee <repo>/results/bench-qwen; otra carpeta con BENCH_DIR=ruta)
import csv, glob, os, re, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # este script vive en <repo>/scripts/
BASE = os.path.expanduser(os.environ.get("BENCH_DIR") or os.path.join(REPO, "results", "bench-qwen"))
CSV = os.path.join(BASE, "resultados.csv")

# Orden de prioridad (calidad): se cede primero contexto, luego thinking, luego cuantización
ORDEN = ["q4-base", "q4-ctx32k", "q4-nothink", "iq3xxs"]
EXTRA = ["base-ollama"]

U_FRIO_S, U_CALIENTE_S, U_GEN, U_VRAM, U_RAM = 30.0, 3.0, 20.0, 11500, 4096
CORTO = 1000  # tokens: por debajo se considera "mensaje corto" para el umbral de ≤ 3 s

# --- CSV: última fila por (etiqueta, etapa) ---
if not os.path.exists(CSV):
    sys.exit(f"No existe {CSV}")
filas = {}
with open(CSV, newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        filas[(r["etiqueta"], r["etapa"])] = r

def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

def log_de(etq):
    ds = sorted(glob.glob(os.path.join(BASE, "runs", etq + "-*", "llama-server.log")))
    return ds[-1] if ds else None

RE_PP = re.compile(r"prompt eval time\s*=\s*([\d.]+) ms /\s*(\d+) tokens")
RE_EV = re.compile(r"\beval time\s*=\s*[\d.]+ ms /\s*\d+ tokens .*?([\d.]+) tokens per second")
RE_NT = re.compile(r"n_tokens = (\d+)")

def leer_log(path):
    pps, gens, nt = [], [], 0
    with open(path, errors="replace") as f:
        for l in f:
            m = RE_PP.search(l)
            if m:
                pps.append((float(m.group(1)) / 1000, int(m.group(2))))
                continue
            if "prompt" not in l:
                m = RE_EV.search(l)
                if m:
                    gens.append(float(m.group(1)))
            m = RE_NT.search(l)
            if m:
                nt = max(nt, int(m.group(1)))
    return pps, gens, nt

def mark(ok):
    return "n/d" if ok is None else ("OK" if ok else "FALLA")

res = {}
for etq in ORDEN + EXTRA:
    e1, e2 = filas.get((etq, "1")), filas.get((etq, "2"))
    if not e1 and not e2:
        continue
    d = {"etq": etq}
    est = [e for e in (e1, e2) if e]
    d["tests"] = all(e["tests"].startswith("OK") and e["tests_intactos"] == "si" for e in est) and len(est) == 2
    vr = [num(e["vram_max_mb"]) for e in est if num(e["vram_max_mb"]) is not None]
    rm = [num(e["ram_disp_min_mb"]) for e in est if num(e["ram_disp_min_mb"]) is not None]
    d["vram"] = max(vr) if vr else None
    d["ram"] = min(rm) if rm else None
    d["wall1"] = num(e1["wall_s"]) if e1 else None
    d["wall2"] = num(e2["wall_s"]) if e2 else None
    d["turnos"] = (e1["turnos"] if e1 else "?") + "/" + (e2["turnos"] if e2 else "?")
    d["carga"] = num(est[0]["carga_s"])
    lg = log_de(etq)
    d["frio"] = d["caliente"] = d["gen"] = d["ctx"] = None
    if lg:
        pps, gens, nt = leer_log(lg)
        if pps:
            d["frio"] = pps[0][0]
            cortos = [t for t, n in pps[1:] if n <= CORTO]
            d["caliente"] = max(cortos) if cortos else None
        d["gen"] = min(gens) if gens else None
        d["ctx"] = nt or None
    d["ok_frio"] = None if d["frio"] is None else d["frio"] <= U_FRIO_S
    d["ok_cal"] = None if d["caliente"] is None else d["caliente"] <= U_CALIENTE_S
    d["ok_gen"] = None if d["gen"] is None else d["gen"] >= U_GEN
    d["ok_vram"] = None if d["vram"] is None else d["vram"] <= U_VRAM
    d["ok_ram"] = None if d["ram"] is None else d["ram"] >= U_RAM
    res[etq] = d

def f(x, fmt="{:.1f}"):
    return "-" if x is None else fmt.format(x)

print("Umbrales: frío ≤ %ds (prefill 1.er prompt) | caliente ≤ %ds (prompts ≤ %d tokens) | gen ≥ %d tok/s (mínima) | VRAM ≤ %d MiB | RAM ≥ %d MiB\n"
      % (U_FRIO_S, U_CALIENTE_S, CORTO, U_GEN, U_VRAM, U_RAM))
cab = ["config", "frío s", "cal. s", "gen mín", "VRAM", "RAM mín", "ctx máx", "wall1 s", "wall2 s", "turnos", "tests", "veredicto"]
print("{:<12}".format(cab[0]) + "".join("{:>9}".format(c) for c in cab[1:11]) + "  " + cab[11])

pasa = []
for etq in ORDEN + EXTRA:
    d = res.get(etq)
    if not d:
        print("{:<12}sin datos".format(etq))
        continue
    chk = [d["ok_frio"], d["ok_cal"], d["ok_gen"], d["ok_vram"], d["ok_ram"], d["tests"]]
    if any(c is False for c in chk):
        ver = "NO cumple: " + ",".join(n for n, c in zip(["frío", "caliente", "gen", "VRAM", "RAM", "tests"], chk) if c is False)
    elif any(c is None for c in chk):
        ver = "incompleto (falta: " + ",".join(n for n, c in zip(["frío", "caliente", "gen", "VRAM", "RAM", "tests"], chk) if c is None) + ")"
    else:
        ver = "cumple todo"
        if etq in ORDEN:
            pasa.append(etq)
    print("{:<12}".format(etq) + "".join("{:>9}".format(x) for x in [
        f(d["frio"]), f(d["caliente"]), f(d["gen"]), f(d["vram"], "{:.0f}"), f(d["ram"], "{:.0f}"),
        f(d["ctx"], "{:.0f}"), f(d["wall1"]), f(d["wall2"]), d["turnos"], "OK" if d["tests"] else "FALLA"]) + "  " + ver)

print()
if pasa:
    print("Regla de decisión (contexto > thinking > cuantización): gana  ->  " + pasa[0])
    if len(pasa) > 1:
        print("También cumplen: " + ", ".join(pasa[1:]))
else:
    print("Ninguna configuración cumple todos los umbrales con datos completos.")
if "base-ollama" in res:
    print("base-ollama: sin log de llama-server, no hay frío/caliente/gen; se compara solo por wall, VRAM, RAM y tests.")
print("Nota: una sola corrida por configuración; si dos quedan cerca, repetir antes de decidir.")
