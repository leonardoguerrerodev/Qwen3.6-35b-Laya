"""Configuración única de laya: lee questions.json y config.json de esta carpeta.

Solo biblioteca estándar (el hook corre con el python3 del sistema).
Precedencia: variable de entorno > config.json.

Variables de entorno (opcionales):
  LAYA_MODEL      pisa "model"
  LAYA_MAXCHARS   pisa "maxchars"
  LAYA_THRESHOLD  pisa TODOS los umbrales de "thresholds"
"""
import json, os

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
