"""Utilidades de sistema: puertos, modelos, estado en disco, carpetas, servidores."""
import glob
import json
import os
import socket
import subprocess
import time

from .config import HOME, KEV_PORT, LAYA_PORT, LLAMA_PORT, MODELS_DIR, STATE_FILE


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.15):
            return True
    except OSError:
        return False


def find_model(patterns, override=None):
    if override and os.path.isfile(override):
        return override
    for pat in patterns:
        hits = sorted(glob.glob(os.path.join(MODELS_DIR, pat)))
        if hits:
            return hits[0]
    return ""


def find_mmproj():
    env = os.environ.get("QWENX_MMPROJ", "")
    if env and os.path.isfile(env):
        return env
    hits = sorted(glob.glob(os.path.join(MODELS_DIR, "mmproj-*F16*.gguf")))
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

    was_up = port_open(LLAMA_PORT) or port_open(LAYA_PORT) or port_open(KEV_PORT)
    pkill("TERM", "laya_server.py")
    pkill("TERM", f"kev.serve.*--port {KEV_PORT}")
    pkill("TERM", f"llama-server.*--port {LLAMA_PORT}")
    if not wait_closed(LLAMA_PORT, 6):
        pkill("KILL", f"llama-server.*--port {LLAMA_PORT}")
        if not wait_closed(LLAMA_PORT, 3):
            return False, f"El puerto {LLAMA_PORT} sigue ocupado (¿otro proceso que no es llama-server?)"
    wait_closed(LAYA_PORT, 3)
    wait_closed(KEV_PORT, 3)
    return True, "servidores apagados · memoria liberada" if was_up else "Nada que apagar: ya estaba offline"
