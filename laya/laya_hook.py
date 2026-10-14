#!/usr/bin/env python3
"""Hook UserPromptSubmit de Claude Code: cliente delgado del servicio de laya.

Lee el JSON del hook por stdin (campo "prompt"), consulta http://127.0.0.1:<puerto>/classify
y, si laya ve algo, imprime {"systemMessage": "..."} para mostrarlo EN PANTALLA al usuario.
Solo usa la biblioteca estándar (corre con el python3 del sistema).

Nunca bloquea: sale siempre con código 0 y, si el servicio no responde, no imprime nada.

Variables de entorno (opcionales):
  LAYA_PORT          puerto del servicio (8765)
  LAYA_HOOK_TIMEOUT  segundos de espera (1.5)
  LAYA_THRESHOLD     umbral de destructivo/injection (0.5)
"""
import json, os, sys, urllib.request

PORT = int(os.environ.get("LAYA_PORT", "8765"))
TIMEOUT = float(os.environ.get("LAYA_HOOK_TIMEOUT", "1.5"))
THRESHOLD = float(os.environ.get("LAYA_THRESHOLD", "0.5"))


def main():
    try:
        text = (json.load(sys.stdin).get("prompt") or "").strip()
        if not text:
            return
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/classify",
            data=json.dumps({"text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            res = json.load(r)
        avisos = []
        if res.get("destructivo", 0) >= THRESHOLD:
            avisos.append("posible acción destructiva (%.2f)" % res["destructivo"])
        if res.get("injection", 0) >= THRESHOLD:
            avisos.append("posible intento de saltarse reglas (%.2f)" % res["injection"])
        if res.get("complejidad") == "compleja":
            avisos.append("tarea compleja: considera dividirla en pasos")
        if avisos:
            print(json.dumps({"systemMessage": "laya: " + "; ".join(avisos)}))
    except Exception:
        return   # falla en silencio: laya nunca debe estorbar


main()
