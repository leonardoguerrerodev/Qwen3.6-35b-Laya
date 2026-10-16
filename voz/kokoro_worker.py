"""Worker de Kokoro-82M para voz_server.py. Corre con el python de su propio venv
(VOZ_KOKORO_PY: kokoro + torch), carga el modelo una vez y queda escuchando.
Dispositivo: VOZ_WORKER_DEVICE=gpu → CUDA; cualquier otra cosa → CPU.

Protocolo por stdin/stdout, una petición a la vez:
  entrada: una línea JSON {"texto": str, "voz": "ef_dora", "velocidad": 1.0, "idioma": "auto"}
  idioma: auto (según el prefijo de la voz: a→inglés EE.UU., b→británico, el resto español)
          | es | en-us | en-gb — decide cómo se lee el texto (G2P); la voz solo pone el timbre.
  salida:  "OK <tasa> <n_bytes>\n" + n_bytes de PCM s16le mono   |   "ERR <mensaje>\n"
Termina al cerrarse stdin (voz_server.py murió o lo apagó).
"""
import json
import os
import sys

DISP = "cuda" if os.environ.get("VOZ_WORKER_DEVICE") == "gpu" else "cpu"
if DISP == "cpu":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""   # CPU: la VRAM es de llama-server
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np  # noqa: E402
import torch  # noqa: E402
from kokoro import KPipeline  # noqa: E402

TASA = 24000
out = sys.stdout.buffer
LANGS = {"es": "e", "en-us": "a", "en-gb": "b"}
try:
    pipes, fallo = {"e": KPipeline(lang_code="e", repo_id="hexgrad/Kokoro-82M", device=DISP)}, None
except Exception as e:  # noqa: BLE001 — p. ej. GPU pedida con torch sin CUDA: se avisa en cada ERR
    pipes, fallo = {}, f"no cargó en {DISP} ({e}); con torch +cpu corre qwen-voz-motores"


def pipe_para(voz, idioma):
    """Pipeline del idioma pedido; los demás idiomas comparten el modelo del de español."""
    code = LANGS.get(idioma) or {"a": "a", "b": "b"}.get(voz[:1], "e")
    if code not in pipes:
        pipes[code] = KPipeline(lang_code=code, repo_id="hexgrad/Kokoro-82M", model=pipes["e"].model)
    return pipes[code]


for linea in sys.stdin:
    try:
        if fallo:
            raise RuntimeError(fallo)
        p = json.loads(linea)
        pipe = pipe_para(p["voz"], p.get("idioma", "auto"))
        trozos = [r.audio for r in pipe(p["texto"], voice=p["voz"], speed=float(p.get("velocidad", 1.0)))
                  if r.audio is not None]
        audio = torch.cat(trozos).numpy() if trozos else np.zeros(0, dtype=np.float32)
        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
        out.write(f"OK {TASA} {len(pcm)}\n".encode() + pcm)
    except Exception as e:  # noqa: BLE001 — cualquier fallo vuelve como ERR, el worker sigue vivo
        out.write(f"ERR {str(e).replace(chr(10), ' ')[:300]}\n".encode())
    out.flush()
