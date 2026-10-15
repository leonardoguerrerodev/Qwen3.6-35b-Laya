#!/usr/bin/env python3
"""Calibración sobre los volcados de bench_laya.py (results/laya-probs/*.jsonl). Solo biblioteca estándar.

Uso: python3 calib.py archivo1.jsonl [archivo2.jsonl ...]
  noul (destructivo, injection): AUC (calidad del ranking, independiente del umbral) y mejor umbral por F1.
  complejidad: ajusta un sesgo aditivo por opción sobre el log-prob y lo valida dejando un archivo fuera.
"""
import sys, json, math

LABELS = ["simple", "media", "compleja"]
GRID = sorted([i / 4 for i in range(-16, 17)], key=abs)   # -4 .. 4; los sesgos pequeños ganan los empates
THS = [i / 20 for i in range(1, 20)]


def load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def find_probs(node):
    """Busca las probabilidades por opción dentro del resultado crudo de la pregunta 'choice'."""
    n = len(LABELS)
    if isinstance(node, dict):
        if all(isinstance(node.get(l), (int, float)) for l in LABELS):
            return [float(node[l]) for l in LABELS]
        if all(isinstance(node.get(str(i)), (int, float)) for i in range(n)):
            return [float(node[str(i)]) for i in range(n)]
        for v in node.values():
            r = find_probs(v)
            if r:
                return r
    elif isinstance(node, list) and len(node) == n and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in node):
        return [float(x) for x in node]
    return None


def to_logp(p):
    if all(0 <= x <= 1 for x in p) and 0.9 <= sum(p) <= 1.1:
        return [math.log(max(x, 1e-9)) for x in p]
    return p   # ya son logits


def auc(scores, ys):
    pos = [s for s, y in zip(scores, ys) if y]
    neg = [s for s, y in zip(scores, ys) if not y]
    if not pos or not neg:
        return None
    return sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))


def prf(scores, ys, t):
    tp = sum(1 for s, y in zip(scores, ys) if y and s >= t)
    fp = sum(1 for s, y in zip(scores, ys) if (not y) and s >= t)
    fn = sum(1 for s, y in zip(scores, ys) if y and s < t)
    P = tp / (tp + fp) if tp + fp else 0.0
    R = tp / (tp + fn) if tp + fn else 0.0
    return P, R, (2 * P * R / (P + R) if P + R else 0.0)


def best_t(scores, ys):
    return max(THS, key=lambda t: (prf(scores, ys, t)[2], prf(scores, ys, t)[1], -t))


def pick(lp, b):
    s = [lp[i] + b[i] for i in range(len(LABELS))]
    return LABELS[s.index(max(s))]


def score(lps, golds, b):
    pred = [pick(lp, b) for lp in lps]
    acc = sum(p == g for p, g in zip(pred, golds)) / len(golds)
    rec = []
    for c in LABELS:
        idx = [i for i, g in enumerate(golds) if g == c]
        if idx:
            rec.append(sum(pred[i] == c for i in idx) / len(idx))
    return sum(rec) / len(rec), acc


def fit(lps, golds):
    best = None
    for b1 in GRID:
        for b2 in GRID:
            b = [0.0, b1, b2]
            key = score(lps, golds, b)
            if best is None or key > best[0]:
                best = (key, b)
    return best[1]


def main(paths):
    data = {p: load(p) for p in paths}
    print("== noul: AUC y mejor umbral (F1) ==")
    for k in ("destructivo", "injection"):
        allS, allY = [], []
        for p, rows in data.items():
            S = [r["p"][k] for r in rows]
            Y = [bool(r["gold"][k]) for r in rows]
            allS += S; allY += Y
            a = auc(S, Y)
            t = best_t(S, Y)
            P, R, F = prf(S, Y, t)
            print("  %-11s %-52s AUC %s  mejor umbral %.2f -> P %.0f%% R %.0f%%" % (k, p.split("/")[-1][:52], "%.2f" % a if a is not None else "n/d", t, P * 100, R * 100))
        a = auc(allS, allY)
        t = best_t(allS, allY)
        P, R, F = prf(allS, allY, t)
        print("  %-11s COMBINADO %s  AUC %.2f  mejor umbral %.2f -> P %.0f%% R %.0f%%" % (k, " " * 40, a if a is not None else 0, t, P * 100, R * 100))

    print("\n== complejidad: sesgo por opción ==")
    lps, golds, grp = [], [], []
    for p, rows in data.items():
        for r in rows:
            raw = (r.get("raw") or {}).get("complejidad")
            if raw is None:
                print("  el volcado no trae 'raw': usa el bench_laya.py con 'raw' y vuelve a correr")
                return
            pr = find_probs(raw)
            if pr is None:
                print("  no encuentro las probabilidades por opción. Resultado crudo de la primera fila:")
                print("  " + json.dumps(raw, ensure_ascii=False)[:600])
                return
            lps.append(to_logp(pr)); golds.append(r["gold"]["complejidad"]); grp.append(p)
    b0 = [0.0, 0.0, 0.0]
    ba0, a0 = score(lps, golds, b0)
    b = fit(lps, golds)
    ba1, a1 = score(lps, golds, b)
    print("  sin ajuste:   acierto %.0f%%  balanceado %.0f%%" % (a0 * 100, ba0 * 100))
    print("  ajustado:     acierto %.0f%%  balanceado %.0f%%  sesgos [simple 0, media %+.2f, compleja %+.2f]  (ajustado sobre los mismos datos: optimista)" % (a1 * 100, ba1 * 100, b[1], b[2]))
    files = list(data)
    if len(files) >= 2:
        okc = tot = 0
        for held in files:
            tr = [i for i, g in enumerate(grp) if g != held]
            te = [i for i, g in enumerate(grp) if g == held]
            bb = fit([lps[i] for i in tr], [golds[i] for i in tr])
            okc += sum(pick(lps[i], bb) == golds[i] for i in te); tot += len(te)
        print("  validación dejando un archivo fuera: acierto %.0f%%  (n=%d)" % (okc / tot * 100, tot))
    # --- complejidad como detector binario (lo único que usa el hook es "compleja") ---
    def softmax(lp):
        m = max(lp); e = [math.exp(x - m) for x in lp]; z = sum(e)
        return [x / z for x in e]
    PP = [softmax(lp) for lp in lps]
    for name, sc, ys in (("compleja vs resto", [p[2] for p in PP], [g == "compleja" for g in golds]),
                         ("no-simple vs simple", [1 - p[0] for p in PP], [g != "simple" for g in golds])):
        a = auc(sc, ys)
        t = best_t(sc, ys)
        P, R, F = prf(sc, ys, t)
        print("  detector %-20s AUC %.2f  mejor umbral %.2f -> P %.0f%% R %.0f%%  (positivos %d de %d)" % (name, a if a is not None else 0, t, P * 100, R * 100, sum(ys), len(ys)))
    print("  confusión con el ajuste (fila=esperado, col=obtenido) %s" % LABELS)
    for g in LABELS:
        print("    %-9s " % g + " ".join("%3d" % sum(1 for lp, gg in zip(lps, golds) if gg == g and pick(lp, b) == c) for c in LABELS))
    print("  probabilidades medias por esperado (simple/media/compleja):")
    for g in LABELS:
        sel = [lp for lp, gg in zip(lps, golds) if gg == g]
        if sel:
            m = [sum(math.exp(lp[i]) for lp in sel) / len(sel) for i in range(len(LABELS))]
            print("    %-9s %s" % (g, "  ".join("%.2f" % x for x in m)))

    print("\n== abstención por confianza (cobertura = % de respuestas con confianza >= umbral) ==")
    for k in ("complejidad", "destructivo", "injection"):
        pts = []
        for rows in data.values():
            for r in rows:
                raw = (r.get("raw") or {}).get(k)
                c = raw.get("confidence") if isinstance(raw, dict) else None
                if isinstance(c, (int, float)) and not isinstance(c, bool) and k in r.get("pred", {}):
                    pts.append((float(c), r["pred"][k] == r["gold"][k]))
        if not pts:
            print("  %-11s sin campo 'confidence' en el resultado crudo" % k)
            continue
        out = []
        for t in (0.0, 0.3, 0.5, 0.7, 0.8, 0.9):
            sel = [ok for c, ok in pts if c >= t]
            if sel:
                out.append(">=%.1f: %3.0f%% cob, %3.0f%% acierto" % (t, len(sel) / len(pts) * 100, sum(sel) / len(sel) * 100))
        print("  %-11s %s" % (k, " | ".join(out)))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
