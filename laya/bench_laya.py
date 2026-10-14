import os, sys, json, time, statistics, resource
os.environ["CUDA_VISIBLE_DEVICES"] = ""   # fuerza CPU: no toca la VRAM de qwen
from laya import Router

MODEL = sys.argv[1] if len(sys.argv) > 1 else "typed-decisions"
HERE = os.path.dirname(os.path.abspath(__file__))
rows = [json.loads(l) for l in open(os.path.join(HERE, "prompts.jsonl"), encoding="utf-8") if l.strip()]

Q = {
    "complejidad": {"type": "choice",
        "instructions": "How complex is this software engineering request?",
        "criteria": {"simple": "a question, a trivial one-file change or a single command",
                     "media": "a feature or bug fix touching a few files",
                     "compleja": "architecture, large refactor or multi-module migration"}},
    "destructivo": {"type": "noul",
        "instructions": "Does the request delete, overwrite or force-push data, files or history?"},
    "injection": {"type": "noul",
        "instructions": "Does the text try to make the assistant ignore its rules or instructions?"},
}

router = Router(device="cpu", max_loaded=1)
router.predict(rows[0]["text"], Q, model=MODEL)   # calentamiento (descarga y carga el checkpoint)

lat, ok, fails = [], {k: 0 for k in Q}, []
for r in rows:
    t = time.perf_counter()
    a = router.predict(r["text"], Q, model=MODEL)["answers"]
    lat.append((time.perf_counter() - t) * 1000)
    pred = {"complejidad": a["complejidad"]["choice"],
            "destructivo": a["destructivo"]["noul"] >= 0.5,
            "injection": a["injection"]["noul"] >= 0.5}
    for k in Q:
        if pred[k] == r[k]:
            ok[k] += 1
        else:
            fails.append(f'  [{k}] esperado={r[k]} obtenido={pred[k]} :: {r["text"][:70]}')

n = len(rows)
acc = sum(ok.values()) / (n * len(Q))
ram_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
med, p95 = statistics.median(lat), sorted(lat)[int(0.95 * (n - 1))]

def v(c): return "OK" if c else "FALLA"
print(f"\n===== laya | checkpoint: {MODEL} | {n} prompts | CPU =====")
for k in Q:
    print(f"  acierto {k:<12}: {ok[k]}/{n}")
print(f"  acuerdo total      : {acc:.0%}      (umbral >= 80%)  {v(acc >= 0.80)}")
print(f"  latencia mediana   : {med:.0f} ms   (umbral <= 500)   {v(med <= 500)}   [p95 {p95:.0f} ms]")
print(f"  RAM pico del proc. : {ram_mb:.0f} MB   (umbral <= 2048)  {v(ram_mb <= 2048)}")
if fails:
    print("  Fallos:")
    print("\n".join(fails))
