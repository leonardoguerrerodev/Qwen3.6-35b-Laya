#!/usr/bin/env python3
"""Hook PreToolUse(Bash) de Claude Code: filtro «System One» de comandos.

Un prefiltro con regex descarta de inmediato los comandos corrientes (sin red ni espera). Solo los
que huelen a destructivos se le preguntan a laya (/classify → «destructivo», con kev detrás); si
supera el umbral devuelve permissionDecision "ask": Claude Code te pide confirmar. Nunca "deny":
kev/laya son orientativos (~0.8–0.95 de acierto), la última palabra es tuya.

Falla en silencio (sale 0 sin imprimir): si laya no responde, manda el sistema de permisos normal.
Variables: LAYA_PORT (8765), LAYA_GUARD_TIMEOUT (segundos, 3), LAYA_THRESHOLD (como en el hook).
"""
import json, os, re, sys, urllib.request

PORT = int(os.environ.get("LAYA_PORT", "8765"))
TIMEOUT = float(os.environ.get("LAYA_GUARD_TIMEOUT", "3"))
# ponytail: prefiltro por regex; un comando destructivo que no calce aquí no llega a kev (mejorar si se ve un caso)
SOSPECHOSO = re.compile(
    r"\brm\s+(-\w*[rf]|--recursive|--force)|\bgit\s+(push\s.*(--force|-f\b)|reset\s+--hard|clean\s+-\w*f|checkout\s+--\s|branch\s+-D)"
    r"|\b(dd|mkfs\w*|shred|wipefs|truncate)\b|\bfind\b.*(-delete|-exec\s+rm)|\bchmod\s+-R|\bchown\s+-R"
    r"|\b(drop|truncate)\s+(table|database)|\bdelete\s+from\b|(^|[;&|]\s*)>\s*[^&\s]|\bmv\s+\S+\s+/dev/null"
    r"|\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z)?sh\b",
    re.I,
)


def main():
    try:
        cmd = (json.load(sys.stdin).get("tool_input") or {}).get("command") or ""
        if not SOSPECHOSO.search(cmd):
            return
        from laya_config import thresholds   # dentro del try: si falla la config, el guard calla
        umbral = thresholds()["destructivo"]
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/classify",
            data=json.dumps({"text": "Run this shell command: " + cmd}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            p = float(json.load(r).get("destructivo", 0))
        if p >= umbral:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": "laya/kev: el comando parece destructivo (%.2f); confirma tú." % p,
            }}))
    except Exception:
        return


main()
