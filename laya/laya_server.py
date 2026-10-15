#!/usr/bin/env python3
"""Servicio local de laya para el hook de Claude Code.

Carga el Router UNA vez (CPU, igual que bench_laya.py) y clasifica prompts por HTTP en 127.0.0.1.
Se ejecuta con el python del .venv de laya:  laya/.venv/bin/python laya/laya_server.py

POST /classify  {"text": "..."}  ->  {"complejidad": "simple|media|compleja",
                                      "destructivo": 0..1, "injection": 0..1, "ms": N}
GET  /health    ->  200 "ok" (solo existe cuando el modelo ya está cargado)

Preguntas, checkpoint y recorte de texto salen de questions.json y config.json (ver laya_config.py).

Variables de entorno (opcionales):
  LAYA_PORT      puerto (8765)
  LAYA_MODEL     pisa el checkpoint de config.json
  LAYA_MAXCHARS  pisa el recorte de texto de config.json
"""
import os, sys, json, time

os.environ["CUDA_VISIBLE_DEVICES"] = ""   # fuerza CPU: no toca la VRAM de qwen (antes de importar laya)

from http.server import BaseHTTPRequestHandler, HTTPServer
from laya import Router
import laya_config

PORT = int(os.environ.get("LAYA_PORT", "8765"))
MODEL = laya_config.model()
MAXCHARS = laya_config.maxchars()
Q = laya_config.load_questions()   # las mismas que usa bench_laya.py

router = Router(device="cpu", max_loaded=1)


def classify(text):
    t = time.perf_counter()
    a = router.predict(text[:MAXCHARS], Q, model=MODEL)["answers"]
    return {
        "complejidad": a["complejidad"]["choice"],
        "destructivo": float(a["destructivo"]["noul"]),
        "injection": float(a["injection"]["noul"]),
        "ms": round((time.perf_counter() - t) * 1000),
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, "ok", "text/plain")
        else:
            self._send(404, "{}")

    def do_POST(self):
        if self.path != "/classify":
            return self._send(404, "{}")
        try:
            n = int(self.headers.get("Content-Length", "0"))
            text = json.loads(self.rfile.read(n).decode("utf-8")).get("text", "")
            self._send(200, json.dumps(classify(text)))
        except Exception as e:
            print(f"error en /classify: {e!r}", file=sys.stderr, flush=True)
            self._send(500, json.dumps({"error": str(e)}))

    def log_message(self, *args):   # sin log de cada petición
        pass


if __name__ == "__main__":
    print(f"laya: cargando '{MODEL}' (la primera vez descarga el checkpoint)...", flush=True)
    classify("hola")   # calentamiento: descarga y carga el modelo antes de abrir el puerto
    srv = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"laya: listo en 127.0.0.1:{PORT}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
