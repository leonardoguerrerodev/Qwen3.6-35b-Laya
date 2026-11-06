#!/usr/bin/env python3
"""Prueba del comando de llama-server (vista previa = lanzamiento): python3 menu/test_comando.py
Usa los .gguf reales de ~/models; si falta uno, ese caso se salta."""
import os
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qwen_menu import flags, profiles  # noqa: E402

M = os.path.expanduser("~/models")
Q38 = os.path.join(M, "Qwen3.8-27B-GSQ-RCO-IQ2_XS-mtp.gguf")   # denso, MTP tras el vocabulario
BASE = os.path.join(M, "Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf")       # MoE, sin MTP


def cmd(path, **p):
    words, err = flags.build_cmd({"MODEL_PATH": path, "P_CTX": "16384", **p})
    assert words, err
    return words


def after(words, flag):
    return words[words.index(flag) + 1]


# Flags extra: comillas permitidas, cada palabra viaja entera hasta llama-server (JSON con espacios)
ok, val, _ = profiles.validate("extra", """--chat-template-kwargs '{"enable_thinking": false}' -t 8""")
assert ok
assert not profiles.validate("extra", "--x 'sin cerrar")[0]
extra = profiles.extra_words(val)
assert shlex.split(extra) == ["--chat-template-kwargs", '{"enable_thinking": false}', "-t", "8"]
# nada se ejecuta: $(...) llega como texto
assert "$(touch /tmp/no)" in cmd(BASE, P_EXTRA=profiles.extra_words("--alias '$(touch /tmp/no)'"))

if os.path.exists(Q38):
    w = cmd(Q38, P_EFFORT="low", P_EXTRA=extra)
    assert after(w, "--spec-type") == "draft-mtp" and after(w, "--spec-draft-n-max") == "2", w   # MTP auto
    assert after(w, "-np") == "1" and after(w, "-ngl") == "auto" and "--n-cpu-moe" not in w
    assert after(w, "--reasoning-effort") == "low"
    assert after(w, "--chat-template-kwargs") == '{"enable_thinking": false}'
    assert "--spec-type" not in cmd(Q38, P_MTP="off")
    assert after(cmd(Q38, P_DRAFT="3"), "--spec-draft-n-max") == "3"
    assert profiles.gguf_scan(Q38) == {"mtp": True, "efforts": ("xhigh", "medium", "low")}
if os.path.exists(BASE):
    w = cmd(BASE)
    assert "--spec-type" not in w and after(w, "--n-cpu-moe") and after(w, "-c") == "16384"
    assert "--spec-type" in cmd(BASE, P_MTP="on")
    assert profiles.gguf_scan(BASE)["mtp"] is False

# Lanzar a mano: el texto reemplaza todo el armado, palabra por palabra
man = " ".join(shlex.quote(x) for x in ["/bin/llama-server", "-m", "/a b.gguf", "--port", "8001"])
assert cmd(BASE, P_MANUAL=man) == ["/bin/llama-server", "-m", "/a b.gguf", "--port", "8001"]

# Agrupado para mostrar/editar: cada flag con sus valores (los negativos son valores, no flags)
assert flags.groups(["bin", "-m", "x", "--reasoning-budget", "-1", "--jinja"]) == \
    [["bin"], ["-m", "x"], ["--reasoning-budget", "-1"], ["--jinja"]]

# Catálogo del --help: secciones, alias y descripción
cat = flags.catalog()
if cat:
    spec = next(it for it in cat if "--spec-type" in it[1])
    assert spec[0] == "speculative params" and spec[3], spec
    assert next(it for it in cat if "-ngl" in it[1])[1][:2] == ["-ngl", "--gpu-layers"]
    print(f"catálogo: {len(cat)} flags, {sum(1 for it in cat if flags.es(it[1]))} con explicación en español")
print("ok")
