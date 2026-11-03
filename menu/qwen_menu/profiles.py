"""Perfiles de lanzamiento por modelo: muestreo y parámetros de llama-server, guardados en JSON.

$QWEN_DATA/profiles.json  →  {"<id de modelo>": {"activo": "nombre", "perfiles": {"nombre": {campo: valor}}}}
Todos los valores son texto. Vacío = «el valor por defecto del lanzador» (no se pasa el flag).
ctx, temp y kvq son además los «Parámetros» t / T / C del menú: el perfil los refleja.
"""
import fnmatch
import json
import os
import re
import struct

from .config import PARAMS, QWEN_DATA

PROFILES_FILE = os.path.join(QWEN_DATA, "profiles.json")

_PV = {p[0]: p[3] for p in PARAMS}   # valores de ciclo de ctx/temp/kvq: los mismos que t/T/C

# clave, etiqueta, descripción, valores de ciclo (espacio)
FIELDS = [
    ("temp", "Temp.", "0-2 · 0.6 código, 1.0 general", _PV["temp"]),
    ("top_p", "Top-p", "0-1 · rec. 0.95", ("0.8", "0.9", "0.95", "1.0")),
    ("top_k", "Top-k", "0 = sin límite · rec. 20", ("0", "20", "40", "64")),
    ("min_p", "Min-p", "0-1 · rec. 0.0", ("0.0", "0.02", "0.05")),
    ("ctx", "Contexto", "tokens · 32k vale · auto = lanzador", _PV["ctx"]),
    ("kvq", "KV cache", "q8_0 / q4_0 ahorran memoria", _PV["kvq"]),
    ("ncmoe", "MoE en CPU", "--n-cpu-moe · vacío = lanzador", ("", "20", "28", "36", "40")),
    ("ngl", "Capas GPU", "-ngl · vacío = según modelo", ("", "auto", "20", "30", "45", "99")),
    ("loadmode", "Carga", "--load-mode · vacío = lanzador", ("", "none", "mmap", "mlock")),
    ("batch", "Batch", "-b · vacío = lanzador", ("", "512", "1024", "2048", "4096")),
    ("ub", "Ubatch", "-ub · vacío = lanzador", ("", "256", "512", "1024")),
    ("extra", "Flags extra", "flags crudos, sin comillas", ()),
]
KEYS = tuple(f[0] for f in FIELDS)
SHARED = ("ctx", "temp", "kvq")                     # también viven en los Parámetros del menú
EXTRA_KEYS = tuple(k for k in KEYS if k not in SHARED)
ROW_PARAMS = tuple(p for p in PARAMS if p[0] not in SHARED)   # filas de la pantalla principal (no están en el perfil)

DEFAULTS = {"temp": "0.6", "top_p": "0.95", "top_k": "20", "min_p": "0.0", "ctx": "auto", "kvq": "auto",
            "ncmoe": "", "ngl": "", "loadmode": "", "batch": "", "ub": "", "extra": ""}


_GGUF_SIZE = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}


def gguf_layers(path):
    """(capas, es_moe) leídos de la cabecera del GGUF, o (0, False) si no se pueden leer.
    «capas» cuenta como llama.cpp en «offloaded N/N layers»: bloques + la capa de salida."""
    try:
        with open(path, "rb") as f:
            rd = lambda n: f.read(n)
            if rd(4) != b"GGUF":
                return 0, False
            _ver, _nt, nkv = struct.unpack("<IQQ", rd(20))
            blocks, moe = 0, False
            for _ in range(nkv):
                key = rd(struct.unpack("<Q", rd(8))[0]).decode("utf-8", "replace")
                if key.startswith("tokenizer."):   # las claves de la arquitectura van antes
                    break
                t = struct.unpack("<I", rd(4))[0]
                if t == 8:
                    rd(struct.unpack("<Q", rd(8))[0])
                elif t == 9:
                    et, n = struct.unpack("<IQ", rd(12))
                    for _ in range(n):
                        if et == 8:
                            rd(struct.unpack("<Q", rd(8))[0])
                        else:
                            rd(_GGUF_SIZE[et])
                else:
                    v = rd(_GGUF_SIZE[t])
                    if key.endswith(".block_count"):
                        blocks = int.from_bytes(v, "little")
                    elif key.endswith(".expert_count"):
                        moe = True
            return (blocks + 1 if blocks else 0), moe
    except (OSError, struct.error, KeyError):
        return 0, False


def ngl_info(path):
    """(capas, texto de «por defecto», valores de ciclo) del campo Capas GPU para el modelo en `path`."""
    capas, moe = gguf_layers(path) if path else (0, False)
    base = "todas (99) + MoE en CPU" if moe else "auto (--fit reparte)"
    forced = ""
    try:   # flags.conf pisa al perfil: el primer patrón que calce con el .gguf gana
        with open(os.path.join(QWEN_DATA, "flags.conf"), encoding="utf-8") as f:
            for ln in f:
                pat, sep, flags = ln.strip().partition(" = ")
                if sep and not pat.startswith("#") and fnmatch.fnmatchcase(os.path.basename(path), pat):
                    m = re.search(r"-ngl\s+(\S+)", flags)
                    forced = m.group(1) if m else ""
                    break
    except OSError:
        pass
    vals = ("", "auto") + ((tuple(str(n) for n in range(capas, -1, -5)) if capas else ("20", "30", "45", "99")))
    txt = (f"{capas} capas · " if capas else "") + f"defecto: {base}"
    if forced:
        txt += f" · flags.conf fija {forced} y pisa el perfil"
    return capas, txt, vals


def _float(t, lo, hi):
    try:
        v = float(t)
    except ValueError:
        return None
    return str(v) if lo <= v <= hi else None


def _int(t, lo, hi):
    return str(int(t)) if re.fullmatch(r"\d+", t) and lo <= int(t) <= hi else None


def validate(key, text):
    """(ok, valor_normalizado, mensaje). Vacío → por defecto del campo."""
    t = (text or "").strip()
    if key == "extra":
        if re.search(r"""['"`$;&|<>\\]""", t):
            return False, t, "sin comillas ni caracteres de shell (solo flags separados por espacios)"
        return True, " ".join(t.split()), ""
    if t == "":
        return True, DEFAULTS[key], ""
    if key == "ctx":
        if t.lower() == "auto":
            return True, "auto", ""
        m = re.fullmatch(r"(\d+)([kK]?)", t)
        if m:
            n = int(m.group(1)) * (1024 if m.group(2) else 1)
            if 256 <= n <= 2_000_000:
                return True, str(n), ""
        return False, t, "contexto: auto, un entero (≥256) o con k (32k)"
    choices = {"kvq": ("auto", "f16", "q8_0", "q4_0"), "loadmode": ("none", "mmap", "mlock")}
    if key in choices:
        return ((True, t, "") if t in choices[key] else (False, t, "valores: " + ", ".join(choices[key])))
    if key == "ngl":
        v = "auto" if t == "auto" else _int(t, 0, 999)
        return (True, v, "") if v else (False, t, "-ngl: auto o un entero 0-999")
    rules = {"temp": (_float, 0, 2, "0 a 2"), "top_p": (_float, 0, 1, "0 a 1"), "min_p": (_float, 0, 1, "0 a 1"),
             "top_k": (_int, 0, 1000, "entero 0 a 1000"), "ncmoe": (_int, 0, 999, "entero 0 a 999"),
             "batch": (_int, 1, 65536, "entero 1 a 65536"), "ub": (_int, 1, 65536, "entero 1 a 65536")}
    fn, lo, hi, hint = rules[key]
    v = fn(t, lo, hi)
    return (True, v, "") if v is not None else (False, t, f"{key}: {hint}")


def sanitize(p):
    """Perfil completo y válido: lo que falte o esté roto vuelve al valor por defecto."""
    p = p if isinstance(p, dict) else {}
    out = {}
    for k in KEYS:
        ok, v, _ = validate(k, str(p.get(k, DEFAULTS[k])))
        out[k] = v if ok else DEFAULTS[k]
    return out


def load_all():
    try:
        with open(PROFILES_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_all(doc):
    try:
        os.makedirs(os.path.dirname(PROFILES_FILE), exist_ok=True)
        tmp = PROFILES_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, PROFILES_FILE)
        return True
    except OSError:
        return False


def entry(doc, mid, seed=None):
    """Entrada del modelo `mid` (la crea, o repara, con un perfil «default» a partir de `seed`)."""
    ent = doc.get(mid)
    perfiles = ent.get("perfiles") if isinstance(ent, dict) else None
    if not isinstance(perfiles, dict) or not perfiles:
        ent = doc[mid] = {"activo": "default", "perfiles": {"default": sanitize(seed or DEFAULTS)}}
    else:
        ent["perfiles"] = {str(n): sanitize(p) for n, p in perfiles.items()}
        if ent.get("activo") not in ent["perfiles"]:
            ent["activo"] = next(iter(ent["perfiles"]))
    return ent


def check_name(ent, name, current=None):
    """(ok, nombre, mensaje): sin vacíos, ≤24 caracteres, sin repetir (salvo el mismo al renombrar)."""
    n = " ".join((name or "").split())
    if not n:
        return False, n, "el nombre no puede estar vacío"
    if len(n) > 24 or not n.isprintable():
        return False, n, "máximo 24 caracteres"
    if n in ent["perfiles"] and n != current:
        return False, n, "ya existe un perfil con ese nombre"
    return True, n, ""


def unique_name(ent, base):
    n, i = f"{base}-2", 2
    while n in ent["perfiles"]:
        i += 1
        n = f"{base}-{i}"
    return n


def rename(ent, old, new):
    ent["perfiles"] = {(new if n == old else n): p for n, p in ent["perfiles"].items()}
    if ent["activo"] == old:
        ent["activo"] = new
