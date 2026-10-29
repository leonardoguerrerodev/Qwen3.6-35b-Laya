#!/usr/bin/env python3
"""Extrae métricas de una corrida de `pi -p --mode json` (un JSONL por corrida).

Uso: metricas.py <corrida.jsonl> <cwd>   → imprime JSON con las métricas.
"""
import json
import os
import sys
from collections import Counter


def metricas(ruta, cwd):
    asist, herr, resultados = [], [], []
    for linea in open(ruta, encoding="utf-8"):
        try:
            e = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if e.get("type") != "message_end":
            continue
        m = e["message"]
        if m.get("role") == "assistant":
            asist.append(m)
            herr += [c for c in m.get("content", []) if c.get("type") == "toolCall"]
        elif m.get("role") == "toolResult":
            resultados.append(m)

    leidos, editar_sin_leer, fuera = set(), 0, []
    for c in herr:
        a = c.get("arguments") or {}
        p = a.get("path") or a.get("file_path") or ""
        absoluta = os.path.normpath(os.path.join(cwd, p)) if p else ""
        if p and not absoluta.startswith(os.path.normpath(cwd)):
            fuera.append(p)
        if c["name"] == "read":
            leidos.add(absoluta)
        elif c["name"] == "edit" and absoluta not in leidos:
            editar_sin_leer += 1
        elif c["name"] == "write":
            leidos.add(absoluta)  # lo que escribió ya lo "conoce"

    firmas = Counter(json.dumps([c["name"], c.get("arguments")], sort_keys=True) for c in herr)
    u = [m.get("usage", {}) for m in asist]
    return {
        "turnos": len(asist),
        "llamadas": len(herr),
        "por_herramienta": dict(Counter(c["name"] for c in herr)),
        "errores_herramienta": sum(1 for r in resultados if r.get("isError")),
        "editar_sin_leer": editar_sin_leer,
        "rutas_fuera_cwd": fuera,
        "repeticiones_max": max(firmas.values(), default=0),
        "truncado": sum(1 for m in asist if m.get("stopReason") == "length"),
        "error_api": [m.get("errorMessage") for m in asist if m.get("stopReason") == "error"],
        "tok_entrada": sum(x.get("input", 0) for x in u),
        "tok_cache": sum(x.get("cacheRead", 0) for x in u),
        "tok_salida": sum(x.get("output", 0) for x in u),
        "seg_modelo": round(sum(m.get("durationMs", 0) for m in asist) / 1000, 1),
        "final": next((c.get("text", "") for c in reversed(asist[-1]["content"]) if c.get("type") == "text"), "")[:400] if asist else "",
    }


if __name__ == "__main__":
    print(json.dumps(metricas(sys.argv[1], sys.argv[2]), ensure_ascii=False))
