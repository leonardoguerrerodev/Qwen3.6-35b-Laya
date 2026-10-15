import os, sys, json, time, statistics, resource, collections
os.environ["CUDA_VISIBLE_DEVICES"] = ""   # fuerza CPU: no toca la VRAM de qwen
import laya_config

MODEL = sys.argv[1] if len(sys.argv) > 1 else laya_config.model()
KEV = MODEL == "kev"   # "kev" = kev.serve por HTTP (levantado antes) en vez de un checkpoint de laya
LABEL = "kev (%s)" % laya_config.kev_run() if KEV else MODEL
HERE = os.path.dirname(os.path.abspath(__file__))
PF = os.environ.get("LAYA_PROMPTS", "prompts.jsonl")
rows = [json.loads(l) for l in open(os.path.join(HERE, PF), encoding="utf-8") if l.strip()]

Q = laya_config.load_questions()    # las mismas que usa laya_server.py
TH = laya_config.thresholds()       # umbrales de config.json (LAYA_THRESHOLD los pisa)
BINS = [i / 10 for i in range(1, 10)]
NOUL = [k for k in Q if Q[k]["type"] == "noul"]

if KEV:
    def predict(text):
        return laya_config.kev_predict(laya_config.clip(text), Q)
else:
    from laya import Router
    router = Router(device="cpu", max_loaded=1)
    def predict(text):
        return router.predict(laya_config.clip(text), Q, model=MODEL)["answers"]
predict(rows[0]["text"])   # calentamiento (descarga y carga el checkpoint)
print("laya: calentamiento listo, midiendo...", file=sys.stderr, flush=True)

lat, ok, fails, probs = [], {k: 0 for k in Q}, [], []
for r in rows:
    t = time.perf_counter()
    a = predict(r["text"])
    lat.append((time.perf_counter() - t) * 1000)
    p = {k: float(a[k]["noul"]) for k in NOUL}
    pred = {k: (a[k]["choice"] if Q[k]["type"] == "choice" else p[k] >= TH[k]) for k in Q}
    probs.append({"text": r["text"], "raw": {k: a[k] for k in Q}, "pred": pred, "p": p, "gold": {k: r[k] for k in Q}, "tags": r.get("tags", [])})
    for k in Q:
        if pred[k] == r[k]:
            ok[k] += 1
        else:
            fails.append(f'  [{k}] esperado={r[k]} obtenido={pred[k]} :: {r["text"][:70]}')

n = len(rows)
acc = sum(ok.values()) / (n * len(Q))

# --- baseline constante: siempre la clase mayoritaria de cada pregunta ---
base_ok = 0
for k in Q:
    base_ok += max(collections.Counter(r[k] for r in rows).values())
base = base_ok / (n * len(Q))

def prf(k, th):
    tp = fp = fn = 0
    for x in probs:
        g, pr = x["gold"][k], x["p"][k] >= th
        tp += g and pr; fp += (not g) and pr; fn += g and (not pr)
    P = tp / (tp + fp) if tp + fp else 0.0
    R = tp / (tp + fn) if tp + fn else 0.0
    return P, R, (2 * P * R / (P + R) if P + R else 0.0), tp, fp, fn

def kev_ram_mb():
    """Pico de RAM (VmHWM) del proceso kev.serve: el bench solo hace HTTP, su propia RAM no cuenta."""
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode("utf-8", "ignore")
            if "kev.serve" in cmd:
                for ln in open(f"/proc/{pid}/status"):
                    if ln.startswith("VmHWM"):
                        return int(ln.split()[1]) / 1024
        except OSError:
            pass
    return 0.0

def kev_rss_mb():  # -> (RssAnon, RssFile) en MB
    """RAM residente actual (VmRSS) de kev.serve: lo que sigue ocupando despues de cargar, sin el pico de la carga."""
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode("utf-8", "ignore")
            if "kev.serve" in cmd:
                anon = file = 0.0
                for ln in open(f"/proc/{pid}/status"):
                    if ln.startswith("RssAnon"):
                        anon = int(ln.split()[1]) / 1024
                    elif ln.startswith("RssFile"):
                        file = int(ln.split()[1]) / 1024
                return anon, file
        except OSError:
            pass
    return 0.0, 0.0

def self_rss_mb():
    for ln in open("/proc/self/status"):
        if ln.startswith("VmRSS"):
            return int(ln.split()[1]) / 1024
    return 0.0

ram_mb = kev_ram_mb() if KEV else resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
med, p95 = statistics.median(lat), sorted(lat)[int(0.95 * (n - 1))]

# --- volcado de probabilidades (para calibrar / barrer umbrales sin volver a correr el modelo) ---
outdir = os.path.join(HERE, "..", "results", "laya-probs")
os.makedirs(outdir, exist_ok=True)
safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in LABEL)
outf = os.path.join(outdir, "%s__%s__%s.jsonl" % (safe, os.path.splitext(PF)[0], os.path.splitext(os.environ.get("LAYA_QUESTIONS") or "questions.json")[0]))
with open(outf, "w", encoding="utf-8") as f:
    for x in probs:
        f.write(json.dumps(x, ensure_ascii=False, default=str) + "\n")

def v(c): return "OK" if c else "FALLA"
print(f"\n===== laya | checkpoint: {LABEL} | {n} prompts [{PF}] | CPU =====")
for k in Q:
    print(f"  acierto {k:<12}: {ok[k]}/{n}")
print(f"  acuerdo total      : {acc:.0%}      (umbral >= 80%)  {v(acc >= 0.80)}")
print(f"  baseline constante : {base:.0%}      (siempre la clase mayoritaria; el acuerdo debe superarlo con margen)")
print(f"  latencia mediana   : {med:.0f} ms   (umbral <= 500)   {v(med <= 500)}   [p95 {p95:.0f} ms]")
print(f"  RAM pico {'kev.serve' if KEV else 'del proc.'} : {ram_mb:.0f} MB   (umbral <= 2048)  {v(ram_mb <= 2048)}")
if KEV:
    _an, _fi = kev_rss_mb()
    print(f"  RAM actual kev.serve: {_an:.0f} MB anonima (pesos reales) + {_fi:.0f} MB de archivos mapeados (reclamable)")
else:
    print(f"  RAM actual del proc.: {self_rss_mb():.0f} MB (sin el pico de la carga; umbral <= 2048)  {v(self_rss_mb() <= 2048)}")

for k in NOUL:
    P, R, F, tp, fp, fn = prf(k, TH[k])
    print(f"  {k:<12} @{TH[k]:.2f}: precision {P:.0%}  recall {R:.0%}  F1 {F:.2f}  (tp {tp} fp {fp} fn {fn})")
for k in NOUL:
    print(f"  barrido {k}: umbral -> precision/recall")
    print("    " + "  ".join("%.1f:%.0f/%.0f" % (t, prf(k, t)[0] * 100, prf(k, t)[1] * 100) for t in BINS))

for k in Q:
    if Q[k]["type"] == "choice":
        labs = sorted({r[k] for r in rows})
        print(f"  confusión {k} (fila=esperado, col=obtenido) {labs}")
        for g in labs:
            print("    %-9s " % g + " ".join("%3d" % sum(1 for x in probs if x["gold"][k] == g and x["pred"][k] == c) for c in labs))

tagacc = collections.defaultdict(lambda: [0, 0])
for x in probs:
    for tg in x["tags"]:
        tagacc[tg][1] += len(Q)
        tagacc[tg][0] += sum(1 for k in Q if x["pred"][k] == x["gold"][k])
if tagacc:
    print("  acierto por tipo de caso: " + "  ".join("%s %d/%d" % (tg, a, b) for tg, (a, b) in sorted(tagacc.items())))

print(f"  probabilidades guardadas en {os.path.relpath(outf, HERE)}")
if fails:
    print("  Fallos:")
    print("\n".join(fails))
print("RESUMEN\t%s\t%.0f%%\t%.0f\t%.0f\t%.0f\t%s" % (LABEL, acc * 100, med, p95, ram_mb, "/".join(str(ok[k]) for k in Q)))
