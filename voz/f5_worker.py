"""Worker de F5-TTS (F5-Spanish de jpgallegoar, licencia CC-BY-NC) para voz_server.py.
Corre con el python de su propio venv (VOZ_F5_PY: f5-tts + torch), carga el modelo una
vez y queda escuchando. Clona la voz del audio de referencia de cada petición.
Dispositivo: VOZ_WORKER_DEVICE=gpu → CUDA; cualquier otra cosa → CPU.

Protocolo por stdin/stdout, una petición a la vez (el mismo de kokoro_worker.py):
  entrada: una línea JSON {"texto": str, "ref_wav": ruta, "ref_txt": str, "velocidad": 1.0, "pasos": 32,
           "cfg": 2.0, "sway": -1.0, "fundido": 0.15, "semilla": 0}  (los 4 últimos son opcionales; semilla 0 = aleatoria)
  salida:  "OK <tasa> <n_bytes>\n" + n_bytes de PCM s16le mono   |   "ERR <mensaje>\n"
Termina al cerrarse stdin (voz_server.py murió o lo apagó).
"""
import json
import os
import sys

# f5-tts imprime avances por stdout: el protocolo va por una copia del fd 1 y el resto a stderr
out = os.fdopen(os.dup(1), "wb")
os.dup2(2, 1)
sys.stdout = sys.stderr

DISP = "cuda" if os.environ.get("VOZ_WORKER_DEVICE") == "gpu" else "cpu"
if DISP == "cpu":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""   # CPU: la VRAM es de llama-server
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np  # noqa: E402
from huggingface_hub import hf_hub_download  # noqa: E402
from f5_tts.api import F5TTS  # noqa: E402

REPO = "jpgallegoar/F5-Spanish"
CKPT = "model_1250000.safetensors"
# Carpeta local con el modelo (VOZ_F5_DIR la sobreescribe). Si existe se usa; si no, caché de HF.
DIR_LOCAL = os.environ.get("VOZ_F5_DIR",
                           "/run/media/xaski/7c0ba586-7758-4419-b3de-f524b9c9a1fb/!models/Voz/F5-Spanish")
try:
    if os.path.isfile(os.path.join(DIR_LOCAL, CKPT)) and os.path.isfile(os.path.join(DIR_LOCAL, "vocab.txt")):
        ckpt, vocab = os.path.join(DIR_LOCAL, CKPT), os.path.join(DIR_LOCAL, "vocab.txt")
        print(f"[f5_worker] modelo local: {ckpt}", file=sys.stderr)
    else:
        ckpt, vocab = hf_hub_download(REPO, CKPT), hf_hub_download(REPO, "vocab.txt")
        print(f"[f5_worker] modelo desde caché HF: {ckpt}", file=sys.stderr)
    tts, fallo = F5TTS(model="F5TTS_Base", ckpt_file=ckpt, vocab_file=vocab, device=DISP), None
except Exception as e:  # noqa: BLE001 — p. ej. GPU pedida sin CUDA o pesos sin bajar: se avisa en cada ERR
    tts, fallo = None, f"no cargó en {DISP} ({e}); corre qwen-voz-motores"

for linea in sys.stdin:
    try:
        if fallo:
            raise RuntimeError(fallo)
        p = json.loads(linea)
        extra = {}
        if int(p.get("semilla", 0)) > 0:   # sin semilla F5 elige una al azar en cada llamada (-1 NO es "aleatoria")
            extra["seed"] = int(p["semilla"])
        audio, tasa, _ = tts.infer(p["ref_wav"], p["ref_txt"], p["texto"], speed=float(p.get("velocidad", 1.0)),
                                   nfe_step=int(p.get("pasos", 32)),
                                   cfg_strength=float(p.get("cfg", 2.0)),
                                   sway_sampling_coef=float(p.get("sway", -1.0)),
                                   cross_fade_duration=float(p.get("fundido", 0.15)),
                                   show_info=lambda *a: None, progress=None, **extra)
        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
        out.write(f"OK {tasa} {len(pcm)}\n".encode() + pcm)
    except Exception as e:  # noqa: BLE001 — cualquier fallo vuelve como ERR, el worker sigue vivo
        out.write(f"ERR {str(e).replace(chr(10), ' ')[:300]}\n".encode())
    out.flush()
