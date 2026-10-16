#!/usr/bin/env python3
"""Cliente manual de prueba: voz/voz_cliente.py "texto a decir"  (o por stdin).

Solo habla por HTTP con voz_server.py en 127.0.0.1. No depende de TTSiro ni de Pi.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

PORT = os.environ.get("VOZ_PORT", "8778")
URL = f"http://127.0.0.1:{PORT}/hablar"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("texto", nargs="?", help="texto a sintetizar (si falta, se lee stdin)")
    ap.add_argument("--guardar", help="guarda el PCM crudo en este archivo en vez de reproducirlo")
    a = ap.parse_args()
    texto = a.texto if a.texto is not None else sys.stdin.read()
    if not texto.strip():
        sys.exit("nada que decir")

    req = urllib.request.Request(
        URL,
        data=json.dumps({"texto": texto}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            tasa = r.headers.get("X-Sample-Rate", "22050")
            audio = r.read()
    except urllib.error.URLError as e:
        sys.exit(f"no pude hablar con voz_server.py en {URL}: {e}")

    if a.guardar:
        with open(a.guardar, "wb") as f:
            f.write(audio)
        print(f"guardado: {a.guardar} ({tasa} Hz, s16le mono)")
        return

    for cmd in (
        ["aplay", "-q", "-r", tasa, "-f", "S16_LE", "-c", "1"],
        ["paplay", "--raw", f"--rate={tasa}", "--format=s16le", "--channels=1"],
    ):
        try:
            subprocess.run(cmd, input=audio, check=True)
            return
        except (OSError, subprocess.CalledProcessError):
            continue
    sys.exit("no encontré 'aplay' ni 'paplay' para reproducir el audio")


if __name__ == "__main__":
    main()
