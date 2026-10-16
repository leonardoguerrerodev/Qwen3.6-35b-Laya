#!/usr/bin/env python3
"""UI web local (LAN) para elegir la combinación del launcher de Qwen.

Fase 1: solo prende los backends (llama-server/laya/kev/voz), headless.
No invoca a pi/claude ni los apaga automáticamente: eso sigue en la terminal
local de Nobara. Arranque manual (`qwen-web`), sin autenticación (red de casa
de confianza) — ver web/README.md.

Fase 2: adjuntar `pi` remotamente — una terminal real (xterm.js, vendorizado en
web/vendor/) sobre un WebSocket que puentea un pty local (`_qwen_web_attach` en
lib/pi.sh). A diferencia de la fase 1, esto SÍ exige un token (WEB_PI_TOKEN,
generado al azar por `qwen-web` e impreso en la terminal de Nobara): da acceso
a una shell real vía las tools de pi, así que no puede quedar abierto a
cualquier dispositivo de la LAN sin más. Si falta el paquete `websockets` o el
token, esta parte queda deshabilitada y el resto de la web (fase 1) sigue
funcionando igual.

Único endpoint "nuevo" de lógica propia en la fase 1: todo lo demás (tablas de
modelos/opciones, estado en disco, apagado) se reusa tal cual de menu/qwen_menu/.
"""
import base64
import fcntl
import http.client
import json
import os
import pty
import select
import signal
import socket
import struct
import subprocess
import sys
import termios
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

try:
    from websockets.sync.server import serve as ws_serve
    HAS_WS = True
except ImportError:
    HAS_WS = False

QWEN_ROOT = os.environ["QWEN_ROOT"]
WEB_PORT = int(os.environ.get("WEB_PORT", "8780"))
WEB_WS_PORT = int(os.environ.get("WEB_WS_PORT", "8781"))
WEB_PI_TOKEN = os.environ.get("WEB_PI_TOKEN", "")
WEB_PI_PASSWORD = os.environ.get("WEB_PI_PASSWORD", "")
WEB_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = os.path.join(WEB_DIR, "index.html")
PI_HTML = os.path.join(WEB_DIR, "pi.html")
VOZ_HTML = os.path.join(WEB_DIR, "voz.html")
STYLE_CSS = os.path.join(WEB_DIR, "style.css")
NO_ZOOM_JS = os.path.join(WEB_DIR, "no-zoom.js")
MANIFEST = os.path.join(WEB_DIR, "manifest.webmanifest")
SW_JS = os.path.join(WEB_DIR, "sw.js")
ICONS_DIR = os.path.join(WEB_DIR, "icons")
VENDOR_DIR = os.path.join(WEB_DIR, "vendor")
PI_ATTACH_ENABLED = HAS_WS and bool(WEB_PI_TOKEN)

sys.path.insert(0, os.path.join(QWEN_ROOT, "menu"))
from qwen_menu.config import KEV_PORT, LAYA_PORT, LLAMA_PORT, MODELS, OPTIONS, PARAMS, VOZ_PORT  # noqa: E402
from qwen_menu.system import (ctx_for, find_model, load_params, load_state, port_open,  # noqa: E402
                              save_state, stop_servers)
# voz_config es solo stdlib: la UI de voz lee/guarda perfiles aunque voz_server.py esté apagado
sys.path.insert(0, os.path.join(QWEN_ROOT, "voz"))
import voz_config  # noqa: E402

MODEL_IDS = [m[0] for m in MODELS]  # base, heretic, iq3
# Fase 5: claude/kevgpu abren una terminal gráfica/kev en la pantalla física de
# Nobora (qwen-web hereda $DISPLAY de la sesión que lo arrancó) — no en el navegador.
WEB_OPT_KEYS = ("edit", "vision", "incognito", "laya", "kev", "voz", "claude", "kevgpu")
WEB_OPTIONS = [o for o in OPTIONS if o[0] in WEB_OPT_KEYS]

VENDOR_MIME = {".js": "application/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}

# ── Estado de la sesión de pi adjuntada (una sola a la vez) ──
_attach_lock = threading.Lock()
_attach_pid = None
_attach_connection = None   # conexión WS viva, para que voz-hook.ts le reenvíe el audio (ver _speak_relay)


def _models_info():
    out = []
    for mid, label, desc, patterns in MODELS:
        path = find_model(patterns)
        out.append({"id": mid, "label": label, "desc": desc, "found": bool(path), "path": path})
    return out


def _ports():
    return {
        "llama": port_open(LLAMA_PORT),
        "laya": port_open(LAYA_PORT),
        "kev": port_open(KEV_PORT),
        "voz": port_open(VOZ_PORT),
    }


# ── ¿el modelo grande está REALMENTE cargado? ──
# port_open() no alcanza para esto: llama-server abre el puerto primero y recién
# después carga el GGUF a VRAM (con 35B son minutos). En esa ventana el puerto
# contesta pero el modelo todavía no puede responder un prompt — y la web usaba
# justamente port_open() para pintar "online", así que parecía listo cuando no.
# El /health de llama-server distingue las dos cosas: 503 mientras carga, 200
# cuando ya puede atender. Con eso la web bloquea la entrada a la terminal de Pi
# hasta que de verdad esté.
#
# Falta un caso que /health no cubre: entre que se aprieta "Lanzar" y que
# llama-server llega a abrir el puerto no hay nada a quién preguntarle, y se
# vería "offline" (indistinguible de no haber lanzado nada). Para eso se anota
# el momento del lanzamiento; si venció el tope se deja de insistir con
# "cargando" para no mentir cuando el arranque falló de verdad.
_launch_pending_since = 0.0      # monotonic; 0 = no hay modelo grande arrancando
LAUNCH_PENDING_MAX_S = 20 * 60   # tope: más que esto y asumimos que falló


def _llama_estado():
    """'off' (no hay nada) · 'loading' (arrancando o cargando pesos) · 'ready'."""
    global _launch_pending_since
    pendiente = bool(_launch_pending_since) and \
        (time.monotonic() - _launch_pending_since) < LAUNCH_PENDING_MAX_S
    if not port_open(LLAMA_PORT):
        return "loading" if pendiente else "off"
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{LLAMA_PORT}/health", timeout=2) as r:
            if r.status == 200:
                _launch_pending_since = 0.0
                return "ready"
            return "loading"
    except urllib.error.HTTPError:
        return "loading"   # 503 "Loading model" es el caso esperado mientras carga
    except (urllib.error.URLError, OSError):
        # El puerto está abierto pero no habla HTTP todavía: sigue arrancando.
        return "loading"


def _version_web():
    """Marca de versión de los archivos de la web, para detectar código viejo.

    Es la fecha del archivo modificado más recientemente (HTML/JS/CSS). La web
    la muestra en una esquina: si el teléfono enseña una marca más vieja que la
    que imprime el server, está corriendo una copia cacheada — que fue
    exactamente el problema difícil de diagnosticar con la PWA instalada, donde
    no hay botón de recargar. Se calcula por pedido, así que refleja ediciones
    sin tener que reiniciar.
    """
    ultimo = 0.0
    for nombre in os.listdir(WEB_DIR):
        if nombre.endswith((".html", ".js", ".css", ".webmanifest")):
            try:
                ultimo = max(ultimo, os.stat(os.path.join(WEB_DIR, nombre)).st_mtime)
            except OSError:
                pass
    return time.strftime("%d/%m %H:%M", time.localtime(ultimo)) if ultimo else "?"


def _browse_dir(path):
    """Lista subcarpetas de `path` (servidor = Nobara, nunca el teléfono/navegador
    remoto). Selector básico: sin salto a rutas arbitrarias por texto, solo navegación
    por subcarpetas reales — pero sin enjaular a $HOME, mismo criterio de confianza-LAN
    que el resto de esta fase (ver web/README.md)."""
    home = os.path.expanduser("~")
    base = os.path.realpath(path) if path else home
    if not os.path.isdir(base):
        base = home
    try:
        entries = os.listdir(base)
    except OSError:
        entries = []
    dirs = []
    for name in sorted(entries, key=str.lower):
        full = os.path.join(base, name)
        try:
            if os.path.isdir(full):
                dirs.append({"name": name, "path": full})
        except OSError:
            continue
    parent = os.path.dirname(base) if base != os.path.sep else None
    return {"path": base, "parent": parent, "dirs": dirs}


def _launch(model, opts, cdir, params=None):
    if model not in MODEL_IDS and model not in ("ollama", "none"):
        raise ValueError(f"modelo desconocido: {model!r}")
    edit = bool(opts.get("edit"))
    vision = bool(opts.get("vision"))
    incognito = bool(opts.get("incognito"))
    laya = bool(opts.get("laya"))
    kev = bool(opts.get("kev"))
    voz = bool(opts.get("voz"))
    claude = bool(opts.get("claude"))
    kevgpu = bool(opts.get("kevgpu"))
    if claude or kevgpu:
        # misma regla que menu.py normalize(): Claude/Kev GPU exigen «Ninguno» y kev.
        model = "none"
        kev = True
    if kev:
        laya = True  # misma regla que menu.py normalize(): kev ⇒ laya
    ollama = model == "ollama"
    nomodel = model == "none"
    if nomodel:
        edit = vision = False  # igual que result() del menú: sin modelo grande, no aplican

    cdir = cdir or ""
    if cdir and not os.path.isdir(cdir):
        raise ValueError(f"la carpeta no existe: {cdir!r}")

    st = load_state()
    st["model"] = -1 if nomodel else (
        MODEL_IDS.index(model) if not ollama else
        (st.get("model", 0) if isinstance(st.get("model"), int) and st.get("model", -1) >= 0 else 0)
    )
    st["opts"] = dict(st.get("opts", {}))
    st["opts"].update({
        "edit": edit, "vision": vision, "incognito": incognito, "ollama": ollama,
        "laya": laya, "kev": kev, "voz": voz, "kevgpu": kevgpu, "claude": claude,
    })
    st["cdir"] = cdir
    st["params"] = pv = load_params({"params": params if isinstance(params, dict) else {}})
    save_state(st)

    # Arranca la cuenta de "cargando" solo si hay GGUF de verdad en juego:
    # «Ninguno» y Ollama no levantan llama-server, así que ahí no hay nada que
    # esperar y la terminal de Pi puede abrirse enseguida (ver _llama_estado).
    global _launch_pending_since
    _launch_pending_since = 0.0 if (nomodel or ollama) else time.monotonic()

    cmd = 'source "$QWEN_ROOT/qwen-local.sh" >/dev/null 2>&1 && _qwen_web_launch "$@"'
    subprocess.Popen(
        ["bash", "-lc", cmd, "_",
         model,
         "1" if edit else "0", "1" if vision else "0", "1" if incognito else "0",
         "1" if laya else "0", "1" if kev else "0", "1" if voz else "0", cdir,
         "1" if claude else "0", "1" if kevgpu else "0",
         ctx_for(model, pv["ctx"]), pv["temp"], pv["idioma"]],
        cwd=QWEN_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True,
    )


VOZ_TOPE_S = 30 * 60   # el motor s2 (S2 Pro en CPU) tarda minutos por frase


def _hablar(texto):
    """Reenvía a voz_server.py (127.0.0.1, invisible fuera de esta máquina) y
    devuelve el PCM crudo + sample rate tal cual. voz_server.py no cambia nada
    de su superficie para esto (ver Fase 3 del plan)."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{VOZ_PORT}/hablar",
        data=json.dumps({"texto": texto}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=VOZ_TOPE_S) as r:
        tasa = r.headers.get("X-Sample-Rate", "22050")
        audio = r.read()
    return audio, tasa


# ── Proxy a la API de settings de voz (fase: configurar voz desde la web) ──
# voz_server.py sigue en 127.0.0.1 (nunca en la LAN); esto es lo único que la
# expone, igual criterio que _hablar() de arriba.
def _voz_proxy(method, path, body=None, timeout=30):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{VOZ_PORT}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ctype = r.headers.get("Content-Type", "application/json")
        return r.status, ctype, r.read()


def _voz_estado_local():
    """Mismo formato que GET /api/estado de voz_server.py, leído de disco (voz apagada)."""
    return {"voces": voz_config.voces_por_motor(), "rangos": voz_config.RANGOS,
            "motores": voz_config.motores_instalados(), "corriendo": False, "cargado": None,
            **voz_config.leer_perfiles()}


def _voz_iniciar_sola():
    """Arranca voz_server.py sin el modelo grande (para ajustar settings sin
    prender todo Qwen) — mismo camino que `qwen-voz`, headless/detached."""
    cmd = 'source "$QWEN_ROOT/qwen-local.sh" >/dev/null 2>&1 && QWEN_VOZ=1 _voz_up'
    subprocess.Popen(
        ["bash", "-lc", cmd], cwd=QWEN_ROOT,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True,
    )


def _lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # no envía nada: solo resuelve la interfaz de salida
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


# ── Puente pty↔WebSocket para adjuntar pi (fase 2) ──

def _spawn_attach_pty(profile):
    """Abre un pty y corre _qwen_web_attach dentro. Devuelve (pid, master_fd)."""
    cmd = 'source "$QWEN_ROOT/qwen-local.sh" && _qwen_web_attach "$@"'
    argv = ["bash", "-lc", cmd, "_", profile]
    pid, master_fd = pty.fork()
    if pid == 0:
        try:
            os.chdir(QWEN_ROOT)
            os.execvp(argv[0], argv)
        finally:
            os._exit(1)
    return pid, master_fd


def _reap(pid):
    try:
        os.waitpid(pid, 0)
    except OSError:
        pass


def _pi_ws_handler(connection):
    global _attach_pid, _attach_connection

    # Primer mensaje: token. Sin esto no se abre ningún proceso.
    try:
        first = connection.recv(timeout=10)
    except Exception:
        return
    try:
        auth = json.loads(first) if isinstance(first, str) else None
    except ValueError:
        auth = None
    if not auth or auth.get("token") != WEB_PI_TOKEN:
        try:
            connection.send(json.dumps({"type": "error", "message": "token inválido"}))
        except Exception:
            pass
        connection.close()
        return

    with _attach_lock:
        if _attach_pid is not None:
            connection.send(json.dumps({"type": "error", "message": "ya hay una sesión de Pi abierta"}))
            connection.close()
            return
        edit = bool(load_state().get("opts", {}).get("edit"))
        profile = "edit" if edit else "readonly"
        pid, master_fd = _spawn_attach_pty(profile)
        _attach_pid = pid
        _attach_connection = connection

    stop_event = threading.Event()

    def reader():
        try:
            while not stop_event.is_set():
                r, _, _ = select.select([master_fd], [], [], 0.2)
                if master_fd in r:
                    try:
                        data = os.read(master_fd, 4096)
                    except OSError:
                        break
                    if not data:
                        break
                    connection.send(data)
        except Exception:
            pass
        finally:
            stop_event.set()

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    try:
        connection.send(json.dumps({"type": "ready"}))
        for message in connection:
            if isinstance(message, bytes):
                try:
                    os.write(master_fd, message)
                except OSError:
                    break
            else:
                # xterm.js manda las teclas como texto plano (no JSON); solo el
                # control de resize es JSON — se distinguen por forma, no por tipo.
                ctrl = None
                try:
                    parsed = json.loads(message)
                    if isinstance(parsed, dict) and "resize" in parsed:
                        ctrl = parsed
                except ValueError:
                    pass
                if ctrl is not None:
                    cols, rows = ctrl["resize"]
                    try:
                        fcntl.ioctl(master_fd, termios.TIOCSWINSZ,
                                    struct.pack("HHHH", int(rows), int(cols), 0, 0))
                    except OSError:
                        pass
                else:
                    try:
                        os.write(master_fd, message.encode("utf-8", "ignore"))
                    except OSError:
                        break
    except Exception:
        pass
    finally:
        stop_event.set()
        t.join(timeout=1)
        with _attach_lock:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            threading.Thread(target=_reap, args=(pid,), daemon=True).start()
            try:
                os.close(master_fd)
            except OSError:
                pass
            _attach_pid = None
            _attach_connection = None


def _speak_relay(texto):
    """Reenvía el audio de la respuesta de Pi al navegador adjuntado por WS, en
    vez de a los parlantes de Nobara (eso hace voz-hook.ts cuando esto falla o
    no hay nadie adjuntado). Devuelve True si se lo entregó a alguien."""
    conn = _attach_connection
    if conn is None:
        return False
    audio, tasa = _hablar(texto)
    if not audio:   # saltado (o texto sin nada que decir): no hay qué mandar
        return True
    conn.send(json.dumps({"type": "speak", "audio": base64.b64encode(audio).decode("ascii"),
                           "sample_rate": int(tasa)}))
    return True


_speak_lock = threading.Lock()   # el motor s2 corre en CPU: una síntesis a la vez


def _speak_bg(texto):
    """Sintetiza y entrega por WS sin tener al hook esperando la respuesta HTTP."""
    with _speak_lock:
        try:
            _speak_relay(texto)
        except urllib.error.HTTPError as e:
            cuerpo = e.read()[:300].decode("utf-8", "replace")
            print(f"speak-relay: HTTP {e.code}: {cuerpo} (texto: {len(texto)} car.)", file=sys.stderr)
        except Exception as e:
            print(f"speak-relay: {e.__class__.__name__}: {e}", file=sys.stderr)


def _start_ws_server():
    with ws_serve(_pi_ws_handler, "0.0.0.0", WEB_WS_PORT) as server:
        server.serve_forever()


class Server(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return   # el cliente cerró antes de leer la respuesta: no es un fallo
        super().handle_error(request, client_address)


class Handler(BaseHTTPRequestHandler):
    server_version = "QwenWeb/1"

    def log_message(self, fmt, *args):
        pass  # silencioso, igual que laya_server.py / voz_server.py

    def _send_json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, mime):
        """Sirve un archivo del disco.

        `Cache-Control: no-store` en el código (HTML/JS/CSS/manifest): sin ningún
        header de caché el navegador aplica caché heurística, y una PWA instalada
        en el dock lo hace de forma mucho más agresiva que una pestaña — sin
        botón de recargar a mano. El síntoma es desconcertante: tocás un archivo,
        reiniciás el server, y el teléfono sigue corriendo la versión vieja.
        Acá no hay nada que ganar cacheando (es una LAN, los archivos son chicos
        y cambian seguido), así que se pide siempre de nuevo.

        Los iconos y lo vendorizado (xterm) sí se cachean: son grandes y no
        cambian nunca.
        """
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        estable = os.sep + "icons" + os.sep in path or os.sep + "vendor" + os.sep in path
        self.send_header("Cache-Control", "max-age=86400" if estable else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/api/browse":
            path = (parse_qs(parsed.query).get("path") or [""])[0]
            self._send_json(200, _browse_dir(path))
            return
        if parsed.path == "/api/pi-info":
            self._send_json(200, {"available": PI_ATTACH_ENABLED, "ws_port": WEB_WS_PORT,
                                   "password_gate": bool(WEB_PI_PASSWORD)})
            return
        if parsed.path == "/api/version":
            self._send_json(200, {"version": _version_web()})
            return
        if parsed.path == "/api/pi-pin":
            # Muestra el PIN, pero SOLO a quien ya presenta el token válido.
            #
            # El punto: desde el teléfono no había forma de recordar el PIN sin
            # ir a mirar la terminal de Nobora. Devolverlo abiertamente lo
            # volvería inútil (el PIN se canjea por el token, y el token da una
            # shell a cualquiera en la red). Exigir el token hace que esto no
            # entregue nada nuevo —quien lo pide ya tiene acceso— y aun así
            # resuelve el caso real: dar de alta un segundo dispositivo desde el
            # teléfono que ya está adentro, en vez de tener que ir a la PC.
            token = (self.headers.get("X-Pi-Token") or
                     parse_qs(parsed.query).get("token", [""])[0])
            if not PI_ATTACH_ENABLED or not WEB_PI_PASSWORD:
                self._send_json(404, {"ok": False, "message": "sin PIN configurado"})
            elif not token or token != WEB_PI_TOKEN:
                self._send_json(403, {"ok": False, "message": "hace falta estar conectado"})
            else:
                self._send_json(200, {"ok": True, "pin": WEB_PI_PASSWORD})
            return
        if parsed.path.startswith("/vendor/"):
            name = os.path.basename(parsed.path)
            ext = os.path.splitext(name)[1]
            if name and ext in VENDOR_MIME:
                self._send_file(os.path.join(VENDOR_DIR, name), VENDOR_MIME[ext])
            else:
                self.send_error(404)
            return
        if parsed.path == "/pi.html" or parsed.path == "/pi":
            self._send_file(PI_HTML, "text/html; charset=utf-8")
            return
        if parsed.path == "/voz.html" or parsed.path == "/voz":
            self._send_file(VOZ_HTML, "text/html; charset=utf-8")
            return
        if parsed.path == "/style.css":
            self._send_file(STYLE_CSS, "text/css; charset=utf-8")
            return
        if parsed.path == "/pwa.js":
            # Se le inyecta la versión con la que se sirvió. Si el navegador
            # devuelve una copia cacheada, esa constante queda vieja y el propio
            # script lo detecta comparándola contra /api/version — que es cómo
            # se distingue "hay un bug" de "estás corriendo código viejo", algo
            # imposible de ver a ojo en una PWA instalada.
            try:
                with open(os.path.join(WEB_DIR, "pwa.js"), "rb") as f:
                    cuerpo = f.read()
            except OSError:
                self.send_error(404)
                return
            cuerpo = (f'window.__QWEN_BUILD__ = "{_version_web()}";\n'
                      ).encode("utf-8") + cuerpo
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cuerpo)
            return
        if parsed.path == "/no-zoom.js":
            self._send_file(NO_ZOOM_JS, "application/javascript; charset=utf-8")
            return
        # ── PWA: guardar la web en el dock del iPhone ──
        if parsed.path == "/manifest.webmanifest":
            self._send_file(MANIFEST, "application/manifest+json; charset=utf-8")
            return
        if parsed.path == "/sw.js":
            # El scope de un service worker no puede ser más amplio que su
            # propia ruta, así que sw.js tiene que servirse desde la raíz para
            # poder controlar /pi.html y /voz.html.
            self._send_file(SW_JS, "application/javascript; charset=utf-8")
            return
        if parsed.path.startswith("/icons/"):
            name = os.path.basename(parsed.path)
            ruta = os.path.join(ICONS_DIR, name)
            if name.endswith(".png") and os.path.isfile(ruta):
                self._send_file(ruta, "image/png")
            else:
                self.send_error(404)
            return
        if parsed.path in ("/", "/index.html"):
            self._send_file(INDEX_HTML, "text/html; charset=utf-8")
            return
        if parsed.path == "/api/state":
            self._send_json(200, {
                "models": _models_info(),
                "options": [{"key": k, "label": lbl, "desc": d} for k, _h, lbl, d in WEB_OPTIONS],
                "params": [{"key": k, "label": lbl, "desc": d, "values": list(vals), "value": v}
                           for (k, _h, lbl, vals, _d, d), v in zip(PARAMS, load_params(load_state()).values())],
                "state": load_state(),
                "ports": _ports(),
                "llama_estado": _llama_estado(),
                "port_nums": {"llama": LLAMA_PORT, "laya": LAYA_PORT, "kev": KEV_PORT, "voz": VOZ_PORT},
            })
            return
        if parsed.path in ("/api/voz/estado", "/api/voz/catalogo"):
            sub = "/api/estado" if parsed.path.endswith("estado") else "/api/catalogo"
            try:
                status, ctype, body = _voz_proxy("GET", sub)
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except urllib.error.URLError:
                if sub == "/api/catalogo":
                    self._send_json(200, [])
                else:   # voz apagada: la interfaz se arma igual, desde los perfiles en disco
                    self._send_json(200, _voz_estado_local())
            return
        self.send_error(404)

    def do_POST(self):
        if self.path == "/api/launch":
            length = int(self.headers.get("Content-Length", "0") or "0")
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
                _launch(data.get("model", ""), data.get("opts") or {}, data.get("cdir", ""),
                        data.get("params"))
            except (ValueError, TypeError) as e:
                self._send_json(400, {"ok": False, "message": str(e)})
                return
            self._send_json(202, {"ok": True, "message": "lanzando… revisá el panel de estado"})
        elif self.path == "/api/stop":
            global _launch_pending_since
            _launch_pending_since = 0.0   # se apagó todo: ya no hay nada "cargando"
            ok, message = stop_servers()
            self._send_json(200, {"ok": ok, "message": message})
        elif self.path == "/api/hablar":
            length = int(self.headers.get("Content-Length", "0") or "0")
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
                texto = (data.get("texto") or "").strip()
                if not texto:
                    raise ValueError("texto vacío")
                audio, tasa = _hablar(texto)
            except (ValueError, TypeError) as e:
                self._send_json(400, {"ok": False, "message": str(e)})
                return
            except urllib.error.URLError as e:
                self._send_json(502, {"ok": False, "message": f"voz no disponible: {e.reason}"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "audio/x-raw")
            self.send_header("X-Sample-Rate", tasa)
            self.send_header("Content-Length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)
        elif self.path == "/api/speak-relay":
            # Solo lo llama voz-hook.ts (localhost); no necesita token: lo peor
            # que puede hacer un tercero de la LAN es hacerte sintetizar un
            # texto cualquiera, no le da acceso a nada que no tuviera ya.
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                self._send_json(403, {"delivered": False})
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
                texto = str(data.get("texto", "")).strip()
            except Exception:
                texto = ""
            # delivered = "aceptado": hay navegador adjuntado y el audio se
            # sintetiza en segundo plano (tarda minutos; el hook no espera).
            delivered = bool(texto) and _attach_connection is not None and port_open(VOZ_PORT)
            if delivered:
                threading.Thread(target=_speak_bg, args=(texto,), daemon=True).start()
            self._send_json(200, {"delivered": delivered})
        elif self.path == "/api/pi-unlock":
            # Capa simple sobre el token real: un PIN corto que el navegador pide
            # una sola vez por dispositivo. Sin límite de intentos ni hashing a
            # propósito (ver comentario en qwen-local.sh:qwen-web) — no es la
            # defensa real, solo evita que cualquiera que abra la página pegue
            # el token largo a mano; el que de verdad autentica el WebSocket
            # sigue siendo WEB_PI_TOKEN.
            length = int(self.headers.get("Content-Length", "0") or "0")
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, TypeError):
                data = {}
            ok = bool(WEB_PI_PASSWORD) and str(data.get("password", "")) == WEB_PI_PASSWORD
            if ok:
                self._send_json(200, {"ok": True, "token": WEB_PI_TOKEN})
            else:
                self._send_json(401, {"ok": False, "message": "PIN incorrecto"})
        elif self.path == "/api/voz/levantar":
            # Deja el perfil elegido como activo y sube su modelo: si la voz está apagada la
            # arranca (al arrancar precarga el activo); si ya corre, le pide precargar.
            length = int(self.headers.get("Content-Length", "0") or "0")
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
                voz_config.guardar_perfiles(data.get("activo"), data.get("perfiles") or {})
            except (ValueError, TypeError) as e:
                self._send_json(400, {"error": str(e)})
                return
            if not port_open(VOZ_PORT):
                _voz_iniciar_sola()
                self._send_json(202, {"ok": True, "message": "arrancando la voz…"})
                return
            try:
                status, ctype, body = _voz_proxy("POST", "/api/precargar", {}, timeout=VOZ_TOPE_S)
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except urllib.error.HTTPError as e:
                self._send_json(e.code, json.loads(e.read() or b"{}"))
            except urllib.error.URLError as e:
                self._send_json(502, {"error": f"voz no responde: {e.reason}"})
        elif self.path == "/api/voz/saltar":
            # Corta la síntesis en curso y lo que suene en Nobara; y avisa al navegador
            # adjuntado (pi.html) para que pare el audio que le llegó por WS.
            conn = _attach_connection
            if conn is not None:
                try:
                    conn.send(json.dumps({"type": "speak-stop"}))
                except Exception:   # noqa: BLE001 — WS cerrándose: nada que parar ahí
                    pass
            try:
                _voz_proxy("POST", "/api/saltar", {})
                self._send_json(200, {"ok": True})
            except (urllib.error.URLError, OSError):
                self._send_json(200, {"ok": True, "message": "la voz está apagada"})
        elif self.path in ("/api/voz/probar", "/api/voz/descargar", "/api/voz/guardar"):
            length = int(self.headers.get("Content-Length", "0") or "0")
            sub = "/api/" + self.path.rsplit("/", 1)[-1]
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
                status, ctype, body = _voz_proxy("POST", sub, data,
                                                 timeout=VOZ_TOPE_S if sub == "/api/probar" else 30)
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except urllib.error.HTTPError as e:
                body = e.read()
                self.send_response(e.code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except urllib.error.URLError:
                if sub == "/api/guardar":   # con voz apagada se guarda directo en perfiles.json
                    try:
                        doc = voz_config.guardar_perfiles(data.get("activo"), data.get("perfiles") or {})
                        self._send_json(200, {"ok": True, **doc})
                    except ValueError as e:
                        self._send_json(400, {"error": str(e)})
                else:
                    self._send_json(503, {"error": "la voz está apagada: toca «Levantar voz» primero"})
            except (ConnectionError, http.client.HTTPException) as e:   # voz cortó sin responder
                self._send_json(502, {"error": f"la voz se cortó sin responder ({e.__class__.__name__}); "
                                               "revisa ~/.local/share/qwen/s2cpp.log"})
            except (ValueError, TypeError) as e:
                self._send_json(400, {"error": str(e)})
        else:
            self.send_error(404)


def main():
    srv = Server(("0.0.0.0", WEB_PORT), Handler)
    print(f"UI web de Qwen: http://{_lan_ip()}:{WEB_PORT}/  (Ctrl+C para apagar)")
    if PI_ATTACH_ENABLED:
        threading.Thread(target=_start_ws_server, daemon=True).start()
        print(f"Adjuntar pi (fase 2): WebSocket en el puerto {WEB_WS_PORT} — pide el token impreso al arrancar")
    else:
        reason = "falta 'websockets' (venv)" if not HAS_WS else "falta WEB_PI_TOKEN"
        print(f"Adjuntar pi (fase 2) deshabilitado: {reason}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
