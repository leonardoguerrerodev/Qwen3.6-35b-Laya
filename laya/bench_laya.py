import os, sys, json, time, statistics, resource
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

if KEV:
    def predict(text):
        return laya_config.kev_predict(text, Q)
else:
    from laya import Router
    router = Router(device="cpu", max_loaded=1)
    def predict(text):
        return router.predict(text, Q, model=MODEL)["answers"]
predict(rows[0]["text"])   # calentamiento (descarga y carga el checkpoint)

lat, ok, fails = [], {k: 0 for k in Q}, []
for r in rows:
    t = time.perf_counter()
    a = predict(r["text"])
    lat.append((time.perf_counter() - t) * 1000)
    pred = {"complejidad": a["complejidad"]["choice"],
            "destructivo": a["destructivo"]["noul"] >= TH["destructivo"],
            "injection": a["injection"]["noul"] >= TH["injection"]}
    for k in Q:
        if pred[k] == r[k]:
            ok[k] += 1
        else:
            fails.append(f'  [{k}] esperado={r[k]} obtenido={pred[k]} :: {r["text"][:70]}')

n = len(rows)
acc = sum(ok.values()) / (n * len(Q))
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

ram_mb = kev_ram_mb() if KEV else resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
med, p95 = statistics.median(lat), sorted(lat)[int(0.95 * (n - 1))]

def v(c): return "OK" if c else "FALLA"
print(f"\n===== laya | checkpoint: {LABEL} | {n} prompts [{PF}] | CPU =====")
for k in Q:
    print(f"  acierto {k:<12}: {ok[k]}/{n}")
print(f"  acuerdo total      : {acc:.0%}      (umbral >= 80%)  {v(acc >= 0.80)}")
print(f"  latencia mediana   : {med:.0f} ms   (umbral <= 500)   {v(med <= 500)}   [p95 {p95:.0f} ms]")
print(f"  RAM pico {'kev.serve' if KEV else 'del proc.'} : {ram_mb:.0f} MB   (umbral <= 2048)  {v(ram_mb <= 2048)}")
if KEV:
    _an, _fi = kev_rss_mb()
    print(f"  RAM actual kev.serve: {_an:.0f} MB anonima (pesos reales) + {_fi:.0f} MB de archivos mapeados (reclamable)")
if fails:
    print("  Fallos:")
    print("\n".join(fails))
print("RESUMEN\t%s\t%.0f%%\t%.0f\t%.0f\t%.0f\t%s" % (LABEL, acc * 100, med, p95, ram_mb, "/".join(str(ok[k]) for k in Q)))
