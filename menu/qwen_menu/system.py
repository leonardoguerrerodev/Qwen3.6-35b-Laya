"""Utilidades de sistema: puertos, modelos, estado en disco, carpetas, servidores."""
import glob
import json
import os
import signal
import socket
import subprocess
import time

from .config import (CTX_AUTO, HOME, KV_AUTO, KEV_PORT, LAYA_PORT, LLAMA_PORT, MMPROJ, MMPROJ_DEFAULT,
                     MODELS_DIR, PARAMS, STATE_FILE, VOZ_PERFILES, VOZ_PORT)


def voz_perfil(avanzar=False):
    """(nombre, motor) del perfil de voz activo; con avanzar, activa el siguiente y lo guarda.
    Sin perfiles.json todavía → ("", "piper")."""
    try:
        with open(VOZ_PERFILES, encoding="utf-8") as f:
            doc = json.load(f)
        nombres = list(doc["perfiles"])
        activo = doc["activo"] if doc["activo"] in nombres else nombres[0]
    except (OSError, ValueError, KeyError, IndexError):
        return "", "piper"
    if avanzar and len(nombres) > 1:
        activo = nombres[(nombres.index(activo) + 1) % len(nombres)]
        doc["activo"] = activo
        tmp = VOZ_PERFILES + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, VOZ_PERFILES)
    p = doc["perfiles"][activo]
    motor = p.get("motor", "piper")
    if motor == "s2gguf":   # variante elegida en /voz.html, p. ej. «s2gguf q4·cpu»
        motor += f" {p.get('cuant', 'q4_k_m').split('_')[0]}·{p.get('dispositivo', 'cpu')}"
    return activo, motor


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.15):
            return True
    except OSError:
        return False


QWEN_LOCAL = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          "qwen-local.sh")
WEB_LOG = os.path.join(HOME, ".cache", "qwenx", "web.log")


def _web_pids():
    pids = []
    for d in os.listdir("/proc"):
        try:
            if d.isdigit() and b"web_server.py" in open(f"/proc/{d}/cmdline", "rb").read():
                pids.append(int(d))
        except OSError:
            pass
    return pids


def web_toggle(port, espera=20):
    """Tecla w: prende qwen-web en segundo plano (sigue vivo al cerrar el menú) o lo apaga si ya corre.
    Devuelve (prendido, aviso). Log en ~/.cache/qwenx/web.log."""
    if port_open(port):
        pids = [p for p in _web_pids() if p != os.getpid()]
        if not pids:
            return True, "el puerto lo ocupa otro programa"
        for sig in (signal.SIGINT, signal.SIGTERM):   # SIGINT = el Ctrl+C de siempre; TERM si no cede
            for p in pids:
                try:
                    os.kill(p, sig)
                except OSError:
                    pass
            for _ in range(15):
                if not port_open(port):
                    return False, ""
                time.sleep(0.2)
        return port_open(port), "no se apagó"
    os.makedirs(os.path.dirname(WEB_LOG), exist_ok=True)
    with open(WEB_LOG, "ab") as log:
        subprocess.Popen(["bash", "-c", 'source "$1" >/dev/null 2>&1 && qwen-web', "_", QWEN_LOCAL],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(espera * 5):
        if port_open(port):
            return True, ""
        time.sleep(0.2)
    return False, f"no arrancó (mira {WEB_LOG})"


def find_model(patterns, override=None):
    if override and os.path.isfile(override):
        return override
    for pat in patterns:
        hits = sorted(glob.glob(os.path.join(MODELS_DIR, pat)))
        if hits:
            return hits[0]
    return ""


def find_mmproj(mid="base"):
    """mmproj (visión) del modelo `mid`: cada familia usa el suyo (ver config.MMPROJ)."""
    env = os.environ.get("QWENX_MMPROJ", "")
    if env and os.path.isfile(env) and mid not in MMPROJ:
        return env
    hits = sorted(glob.glob(os.path.join(MODELS_DIR, MMPROJ.get(mid, MMPROJ_DEFAULT))))
    return hits[0] if hits else ""


def lan_ip():
    """IP de la interfaz de salida (misma lógica que web/web_server.py:_lan_ip)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # no envía nada: solo resuelve la interfaz de salida
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def find_voz_model():
    env = os.environ.get("VOZ_MODEL", "")
    if env and os.path.isfile(env):
        return env
    pat = os.environ.get("VOZ_MODEL_GLOB", "*.onnx")
    hits = sorted(glob.glob(os.path.join(MODELS_DIR, pat)))
    return hits[0] if hits else ""


def gb(path):
    try:
        return f"{os.path.getsize(path) / 1024 ** 3:.1f} GB"
    except OSError:
        return ""


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def load_params(st):
    """Parámetros guardados en el estado, validados contra PARAMS (valor raro → por defecto)."""
    p = st.get("params") if isinstance(st.get("params"), dict) else {}
    return {k: (p.get(k) if p.get(k) in vals else d) for k, _h, _l, vals, d, _desc in PARAMS}


def ctx_for(mid, valor):
    """Contexto efectivo para llama-server ('' = el QWENX_CTX del shell, 120k por defecto)."""
    return CTX_AUTO.get(mid, "") if valor == "auto" else valor


def kv_for(mid, valor):
    """Tipo de KV para llama-server (vacío = el QWENX_KV del shell, q8_0 por defecto)."""
    return KV_AUTO.get(mid, "") if valor == "auto" else valor


def save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except OSError:
        pass


def short_path(p, maxlen=None):
    """/home/xaski/x → ~/x, y recorta por la izquierda con … si no cabe."""
    if p == HOME or p.startswith(HOME + os.sep):
        p = "~" + p[len(HOME):]
    if maxlen and len(p) > maxlen:
        p = "…" + p[-(maxlen - 1):]
    return p


def complete_dir(buf):
    """Autocompletado con TAB de rutas de carpeta. Devuelve (nuevo_buf, n_candidatos)."""
    raw = os.path.expanduser(buf) if buf else HOME + os.sep
    hits = sorted(h for h in glob.glob(glob.escape(raw) + "*") if os.path.isdir(h))
    if not hits:
        return buf, 0
    new = os.path.commonprefix(hits)
    if len(hits) == 1:
        new += os.sep
    if buf.startswith("~") and (new == HOME or new.startswith(HOME + os.sep)):
        new = "~" + new[len(HOME):]
    return new, len(hits)


def pick_dir_gui(start):
    """Selector gráfico de carpetas (KDE: kdialog; si no, zenity). None si cancela o no hay."""
    for cmd in (["kdialog", "--getexistingdirectory", start],
                ["zenity", "--file-selection", "--directory", f"--filename={start}/"]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired):
            continue
        out = r.stdout.strip()
        return out if r.returncode == 0 and out and os.path.isdir(out) else None
    return None


def stop_servers():
    """Apaga llama-server (y laya). Devuelve (ok, mensaje)."""
    def pkill(sig, pat):
        subprocess.run(["pkill", f"-{sig}", "-f", pat],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def wait_closed(port, secs):
        end = time.time() + secs
        while time.time() < end:
            if not port_open(port):
                return True
            time.sleep(0.2)
        return not port_open(port)

    was_up = port_open(LLAMA_PORT) or port_open(LAYA_PORT) or port_open(KEV_PORT) or port_open(VOZ_PORT)
    pkill("TERM", "voz_server.py")   # al salir se lleva su s2.cpp; el de abajo es respaldo
    pkill("TERM", f"s2 --server -H 127.0.0.1 -P {os.environ.get('VOZ_S2CPP_PORT', '8779')}")
    pkill("TERM", "laya_server.py")
    pkill("TERM", f"kev.serve.*--port {KEV_PORT}")
    pkill("TERM", f"llama-server.*--port {LLAMA_PORT}")
    if not wait_closed(LLAMA_PORT, 6):
        pkill("KILL", f"llama-server.*--port {LLAMA_PORT}")
        if not wait_closed(LLAMA_PORT, 3):
            return False, f"El puerto {LLAMA_PORT} sigue ocupado (¿otro proceso que no es llama-server?)"
    wait_closed(LAYA_PORT, 3)
    wait_closed(KEV_PORT, 3)
    wait_closed(VOZ_PORT, 3)
    return True, "servidores apagados · memoria liberada" if was_up else "Nada que apagar: todo estaba apagado"
