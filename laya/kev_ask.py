#!/usr/bin/env python3
"""Pregunta cerrada a kev (System One) desde la línea de comandos; pensado para que Claude lo llame por Bash.

  kev_ask.py "texto o contexto" -q "¿pregunta de sí/no?"                → imprime una probabilidad 0..1
  kev_ask.py "texto o contexto" -q "¿cuál encaja?" -o simple -o media   → imprime la opción elegida

Es orientativo, nunca la autoridad final: kev acierta ~0.8–0.95. Sale con 1 y mensaje en stderr si kev no responde.
Solo biblioteca estándar. Variables: KEV_PORT / KEV_URL (ver laya_config.py).
"""
import argparse, sys

import laya_config


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("texto", help="el texto/contexto sobre el que se pregunta")
    ap.add_argument("-q", "--pregunta", required=True, help="la pregunta (en inglés rinde mejor)")
    ap.add_argument("-o", "--opcion", action="append", help="repetible: opciones cerradas; sin ellas, sí/no")
    a = ap.parse_args()
    if a.opcion:
        q = {"type": "choice", "instructions": a.pregunta, "criteria": {o: o for o in a.opcion}}
    else:
        q = {"type": "noul", "instructions": a.pregunta, "criteria": {"false": "no", "true": "yes"}}
    try:
        r = laya_config.kev_predict(laya_config.clip(a.texto), {"q": q}, timeout=60)["q"]
    except Exception as e:
        sys.exit("kev no responde (¿está levantado?): %s" % e)
    print(r["choice"] if a.opcion else "%.2f" % float(r["noul"]))


main()
