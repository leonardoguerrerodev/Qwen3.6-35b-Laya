"""Configuración única de laya: lee questions.json y config.json de esta carpeta.

Solo biblioteca estándar (el hook corre con el python3 del sistema).
Precedencia: variable de entorno > config.json.

Variables de entorno (opcionales):
  LAYA_MODEL      pisa "model"
  LAYA_MAXCHARS   pisa "maxchars"
  LAYA_THRESHOLD  pisa TODOS los umbrales de "thresholds"
  LAYA_BACKEND    "laya" (Router de la biblioteca) o "kev" (kev.serve en CPU); pisa "backend"
  KEV_RUN         checkpoint de kev que sirve kev.serve (kev.run; informativo aquí)
  KEV_PORT        puerto de kev.serve (kev.port; 8009)
  KEV_URL         URL completa de kev.serve (pisa KEV_PORT)
"""
import json, os, urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
REQUIRED = ("complejidad", "destructivo", "injection")   # el servidor y el hook dependen de estos nombres


def _load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


def load_questions():
    q = _load("questions.json")
    missing = [k for k in REQUIRED if k not in q]
    if missing:
        raise ValueError("questions.json: faltan las preguntas %s" % missing)
    return q


def model():
    return os.environ.get("LAYA_MODEL") or _load("config.json")["model"]


def maxchars():
    return int(os.environ.get("LAYA_MAXCHARS") or _load("config.json")["maxchars"])


def thresholds():
    th = {k: float(v) for k, v in _load("config.json")["thresholds"].items()}
    env = os.environ.get("LAYA_THRESHOLD")
    if env:
        th = {k: float(env) for k in th}
    return th


def backend():
    """'laya' (Router de la biblioteca laya) o 'kev' (servidor kev.serve en CPU)."""
    b = (os.environ.get("LAYA_BACKEND") or _load("config.json").get("backend") or "laya").strip().lower()
    if b not in ("laya", "kev"):
        raise ValueError("backend inválido %r (usa 'laya' o 'kev')" % b)
    return b


def _kev_cfg():
    return _load("config.json").get("kev", {})


def kev_run():
    return os.environ.get("KEV_RUN") or _kev_cfg().get("run", "jaredpalmer/kev-0.8b")


def kev_url():
    if os.environ.get("KEV_URL"):
        return os.environ["KEV_URL"].rstrip("/")
    return "http://127.0.0.1:%d" % int(os.environ.get("KEV_PORT") or _kev_cfg().get("port", 8009))


def kev_predict(text, questions, timeout=300):
    """Pregunta a kev.serve (API System One). Devuelve el mismo dict 'answers' que Router.predict(...)['answers']."""
    body = json.dumps({"state": text, "model": "kev-latest", "questions": questions}).encode("utf-8")
    req = urllib.request.Request(kev_url() + "/v1/systemone", data=body,
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["answers"]
