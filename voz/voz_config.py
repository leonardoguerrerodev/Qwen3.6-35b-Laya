"""Configuración de voz: perfiles (voz + parámetros) y catálogo de descarga.

Solo biblioteca estándar. Las voces .onnx viven en QWEN_MODELS_DIR (junto a los
GGUF de Qwen, mismo criterio que antes). Los perfiles (nombre → voz + parámetros)
se guardan en perfiles.json, en esta misma carpeta — independiente de !TTSiro,
que tiene el suyo propio en otra ruta.

Variables de entorno (solo para el arranque sin perfiles.json todavía, o para
`qwen-voz`/`voz_cliente.py` fuera de la web): VOZ_MODEL, VOZ_VELOCIDAD, VOZ_RUIDO,
VOZ_RUIDO_W, VOZ_PAUSA — ver lib/config.sh. Una vez que existe perfiles.json, el
perfil activo manda (lo gestiona web/voz.html vía voz_server.py).
"""
import json
import os
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PERFILES_PATH = HERE / "perfiles.json"
CONFIG_PATH = HERE / "config.json"

# campo → (mínimo, máximo, por defecto). Los defaults son los de piper (config.json
# original), no los de TTSiro (esos están afinados para sus propias voces/uso).
RANGOS = {
    "velocidad": (50, 150, 100),      # % de la velocidad normal (100 → length_scale 1.0)
    "tono": (-6, 6, 0),               # semitonos (rubberband; 0 = sin post-proceso)
    "volumen": (10, 200, 100),        # % (SynthesisConfig.volume)
    "expresividad": (0, 1.5, 0.667),  # piper noise_scale
    "ritmo": (0, 1.5, 0.8),           # piper noise_w_scale
    "pausa": (0, 2, 0.2),             # segundos de silencio entre líneas
    "temperatura": (0.1, 1.5, 0.8),   # s2gguf: temperature de s2.cpp (expresividad)
    "top_p": (0.1, 1, 0.8),           # s2gguf: top_p de s2.cpp (variación de entonación)
    "pasos": (8, 32, 32),             # f5: nfe_step (16 ≈ el doble de rápido, algo menos de calidad)
    "guia": (0.5, 5, 2),              # f5: cfg_strength (más alto = más fiel a la referencia y al texto)
    "sway": (-1, 1, -1),              # f5: sway_sampling_coef (-1 = recomendado, 0 = apagado)
    "fundido": (0, 0.5, 0.15),        # f5: cross_fade_duration, s entre los trozos de un texto largo
    "semilla": (0, 9999, 0),          # f5: seed (0 = aleatoria; fija = misma salida, útil para comparar)
}

HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
IDIOMA = "es"

# Motores de síntesis. piper: en este proceso. kokoro y s2 (Fish Audio S2 Pro): cada uno
# en su propio venv (torch distinto), ver voz_server.py; se instalan con `qwen-voz-motores`.
MOTORES = ("piper", "kokoro", "f5", "s2", "s2gguf")
REFS_DIR = HERE / "refs"   # f5/s2/s2gguf: <nombre>.wav (voz a clonar, ~8-12 s) + <nombre>.txt (lo que dice)
# s2gguf = S2 Pro cuantizado, servido por s2.cpp (VOZ_S2CPP_DIR). Se elige por perfil:
CUANTS = {"q2_k": "s2-pro-q2_k.gguf", "q3_k": "s2-pro-q3_k.gguf",
          "q4_k_m": "s2-pro-q4_k_m.gguf", "q8_0": "s2-pro-q8_0.gguf"}
DISPOSITIVOS = ("cpu", "gpu")
CON_DISPOSITIVO = ("piper", "kokoro", "f5", "s2gguf")   # motores con CPU/GPU elegible por perfil
IDIOMAS_KOKORO = ("auto", "es", "en-us", "en-gb")       # cómo lee kokoro el texto; auto = según la voz


def _modelos_dir():
    d = os.environ.get("QWEN_MODELS_DIR") or os.path.expanduser("~/models")
    return Path(d)


def _hf_snapshot(repo):
    """Carpeta del snapshot de un repo en el caché de HF (HF_HOME), o None."""
    hub = Path(os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")) / "hub"
    snaps = sorted((hub / f"models--{repo.replace('/', '--')}" / "snapshots").glob("*"))
    return snaps[-1] if snaps else None


def voces():
    """Nombres (sin extensión) de las voces .onnx de piper instaladas en QWEN_MODELS_DIR."""
    try:
        return sorted(p.stem for p in _modelos_dir().glob("*.onnx"))
    except OSError:
        return []


def _voces_kokoro():
    snap = _hf_snapshot("hexgrad/Kokoro-82M")
    # las bajadas: español (e?_) + femeninas en inglés (af_/bf_), que leen el español con acento
    return sorted(p.stem for p in snap.glob("voices/*.pt")) if snap else []


def _refs_s2():
    try:
        return sorted(p.stem for p in REFS_DIR.glob("*.wav") if p.with_suffix(".txt").is_file())
    except OSError:
        return []


def voces_por_motor():
    refs = _refs_s2()
    return {"piper": voces(), "kokoro": _voces_kokoro(), "f5": refs, "s2": refs, "s2gguf": refs}


def s2cpp_bin():
    """Binario `s2` compilado de s2.cpp, o None."""
    d = Path(os.environ.get("VOZ_S2CPP_DIR", "") or "/nonexistent")
    return next((p for p in (d / "build/s2", d / "build/bin/s2") if os.access(p, os.X_OK)), None)


def ruta_gguf(cuant):
    """(gguf, tokenizer.json) de S2 Pro cuantizado: caché de HF o ~/models (bajados a mano)."""
    snap = _hf_snapshot("rodrigomt/s2-pro-gguf")
    if snap is None or not (snap / "tokenizer.json").is_file():
        raise ValueError("falta tokenizer.json de s2-pro-gguf (corre qwen-voz-motores)")
    for d in (snap, _modelos_dir()):
        if (d / CUANTS[cuant]).is_file():
            return d / CUANTS[cuant], snap / "tokenizer.json"
    raise ValueError(f"falta {CUANTS[cuant]} (corre qwen-voz-motores)")


def motores_instalados():
    """Qué motores pueden sintetizar ya (venv/binario + pesos presentes)."""
    kokoro_py = os.environ.get("VOZ_KOKORO_PY", "")
    f5_py = os.environ.get("VOZ_F5_PY", "")
    fish = Path(os.environ.get("VOZ_FISH_DIR", "") or "/nonexistent")
    snap_gguf = _hf_snapshot("rodrigomt/s2-pro-gguf")
    return {
        "piper": bool(voces()),
        "kokoro": bool(kokoro_py and os.access(kokoro_py, os.X_OK) and _voces_kokoro()),
        "f5": bool(f5_py and os.access(f5_py, os.X_OK) and _hf_snapshot("jpgallegoar/F5-Spanish")
                   and _refs_s2()),
        "s2": (fish / ".venv/bin/python").is_file() and _hf_snapshot("fishaudio/s2-pro") is not None
              and bool(_refs_s2()),
        "s2gguf": s2cpp_bin() is not None and snap_gguf is not None and bool(_refs_s2())
                  and any((d / f).is_file() for d in (snap_gguf, _modelos_dir()) for f in CUANTS.values()),
    }


def ruta_ref(nombre):
    wav = REFS_DIR / f"{nombre}.wav"
    if nombre not in _refs_s2():
        raise ValueError(f"referencia de s2 desconocida: {nombre}")
    return wav, wav.with_suffix(".txt").read_text(encoding="utf-8").strip()


def ruta_voz(nombre):
    p = _modelos_dir() / f"{nombre}.onnx"
    if not p.is_file():
        raise ValueError(f"voz desconocida: {nombre}")
    return p


def _voz_por_defecto():
    env = os.environ.get("VOZ_MODEL", "")
    if env:
        return Path(env).stem
    todas = voces()
    return todas[0] if todas else None


def _escribir_atomico(ruta, texto):
    fd, tmp = tempfile.mkstemp(prefix=".voz-", dir=str(ruta.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
        os.replace(tmp, ruta)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def limpiar(perfil):
    """Valida un perfil que viene del navegador (o de un default): motor conocido, voz
    instalada para ese motor y números acotados a RANGOS. Falta un campo → su default
    (motor → piper: los perfiles de antes de los motores siguen siendo válidos)."""
    motor = perfil.get("motor") or "piper"
    if motor not in MOTORES:
        raise ValueError(f"motor desconocido: {motor}")
    disponibles = voces_por_motor()[motor]
    voz = perfil.get("voz") or (_voz_por_defecto() if motor == "piper" else
                                (disponibles[0] if disponibles else None))
    if voz not in disponibles:
        raise ValueError(f"voz desconocida o no instalada para {motor}: {voz}")
    limpio = {"motor": motor, "voz": voz}
    if motor in CON_DISPOSITIVO:
        disp = perfil.get("dispositivo") or "cpu"
        if disp not in DISPOSITIVOS:
            raise ValueError(f"{motor}: dispositivo inválido: {disp}")
        limpio["dispositivo"] = disp
    if motor == "kokoro":
        idioma = perfil.get("idioma") or "auto"
        if idioma not in IDIOMAS_KOKORO:
            raise ValueError(f"kokoro: idioma inválido: {idioma}")
        limpio["idioma"] = idioma
    if motor == "s2gguf":
        cuant = perfil.get("cuant") or "q4_k_m"
        if cuant not in CUANTS:
            raise ValueError(f"s2gguf: cuantización inválida: {cuant}")
        limpio["cuant"] = cuant
    for campo, (lo, hi, defecto) in RANGOS.items():
        valor = perfil.get(campo, defecto)
        try:
            valor = float(valor)
        except (TypeError, ValueError):
            raise ValueError(f"{campo} inválido")
        limpio[campo] = min(hi, max(lo, valor))
    return limpio


def _perfil_arranque():
    """Perfil inicial cuando todavía no existe perfiles.json: lee config.json +
    env vars (comportamiento histórico de esta carpeta, antes de tener perfiles)."""
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cfg = {}
    velocidad_env = os.environ.get("VOZ_VELOCIDAD")
    base = {
        "voz": _voz_por_defecto(),
        "velocidad": (100 / float(velocidad_env)) if velocidad_env else
                     (100 / float(cfg.get("length_scale", 1.0))),
        "tono": 0,
        "volumen": 100,
        "expresividad": float(os.environ.get("VOZ_RUIDO") or cfg.get("noise_scale", 0.667)),
        "ritmo": float(os.environ.get("VOZ_RUIDO_W") or cfg.get("noise_w_scale", 0.8)),
        "pausa": float(os.environ.get("VOZ_PAUSA") or cfg.get("sentence_silence", 0.2)),
    }
    return limpiar(base)


def leer_perfiles():
    if PERFILES_PATH.exists():
        doc = json.loads(PERFILES_PATH.read_text(encoding="utf-8"))
        if doc.get("activo") in doc.get("perfiles", {}):
            return doc
    return {"activo": "Predeterminado", "perfiles": {"Predeterminado": _perfil_arranque()}}


def guardar_perfiles(activo, perfiles):
    limpios = {str(n)[:40]: limpiar(p) for n, p in perfiles.items() if str(n).strip()}
    if activo not in limpios:
        raise ValueError("el perfil activo no existe")
    _escribir_atomico(PERFILES_PATH, json.dumps({"activo": activo, "perfiles": limpios},
                                                 indent=2, ensure_ascii=False) + "\n")
    return {"activo": activo, "perfiles": limpios}


def perfil_activo():
    doc = leer_perfiles()
    return doc["perfiles"][doc["activo"]]


# ── Catálogo de voces es_* descargables desde HF (igual criterio que !TTSiro) ──
_catalogo_cache = None


def catalogo():
    global _catalogo_cache
    if _catalogo_cache is None:
        with urllib.request.urlopen(HF + "voices.json", timeout=20) as r:
            todo = json.load(r)
        _catalogo_cache = {
            k: {"calidad": v["quality"],
                "archivos": sorted((f for f in v["files"] if f.endswith((".onnx", ".onnx.json"))), reverse=True),
                "mb": round(sum(x["size_bytes"] for x in v["files"].values()) / 1e6)}
            for k, v in todo.items() if v["language"]["family"] == IDIOMA
        }
    return _catalogo_cache


def descargar(clave):
    voz = catalogo().get(clave)
    if not voz:
        raise ValueError(f"voz fuera del catálogo: {clave}")
    destino_dir = _modelos_dir()
    destino_dir.mkdir(parents=True, exist_ok=True)
    for ruta in voz["archivos"]:
        destino = destino_dir / Path(ruta).name
        tmp = destino.with_name(destino.name + ".part")
        with urllib.request.urlopen(HF + ruta, timeout=30) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(tmp, destino)  # el .json va primero (orden inverso): la voz aparece completa o no aparece
