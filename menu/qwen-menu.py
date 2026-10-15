#!/usr/bin/env python3
"""qwen-menu.py — lanzador TUI para Qwen3.6-35B + Pi + llama.cpp + laya.

Solo librería estándar (sin venv, sin rich). Dibuja en /dev/tty y escribe el
resultado en stdout como asignaciones de shell, listas para `eval`:

    ACTION=launch|mem|status|laya|quit
    MODEL_ID=base|heretic|iq3
    MODEL_PATH=/ruta/al/modelo.gguf
    OPT_EDIT=0|1  OPT_VISION=0|1  OPT_INCOGNITO=0|1  OPT_OLLAMA=0|1
    MMPROJ_PATH=/ruta/mmproj.gguf   (vacío si no hay visión)
    PI_ARGS='...'                   (argumentos extra para pi, ya entrecomillados)

Variables de entorno opcionales:
    QWEN_MODELS_DIR   directorio de modelos (~/models)
    QWENX_MODEL       sobreescribe la ruta del modelo Base
    QWENX_MMPROJ      sobreescribe la ruta del mmproj
    QWEN_PORT         puerto de llama-server (8001; el mismo que usa lib/config.sh)
    LAYA_PORT         puerto de laya (8765)
"""
import glob
import json
import os
import re
import select
import shlex
import socket
import subprocess
import sys
import termios
import time
import tty

# ───────────────────────── configuración ─────────────────────────
HOME = os.path.expanduser("~")
MODELS_DIR = os.environ.get("QWEN_MODELS_DIR", os.path.join(HOME, "models"))
LLAMA_PORT = int(os.environ.get("QWEN_PORT") or os.environ.get("QWEN_LLAMA_PORT") or "8001")
LAYA_PORT = int(os.environ.get("LAYA_PORT", "8765"))
STATE_FILE = os.path.join(
    os.environ.get("XDG_STATE_HOME", os.path.join(HOME, ".local", "state")),
    "qwen", "menu.json",
)
WIDTH = 72  # ancho total de la caja

# id, etiqueta, descripción, patrones glob (el primero que exista gana)
MODELS = [
    ("base", "Base", "Q4_K_XL · MoE 35B-A3B",
     ["Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf", "*Q4_K_XL*.gguf"]),
    ("heretic", "Heretic", "uncensored Q4_K_M",
     ["*heretic*Q4_K_M*.gguf"]),
    ("iq3", "IQ3", "ligero IQ3_XXS",
     ["*IQ3_XXS*.gguf"]),
]

# clave, tecla, etiqueta, descripción
OPTIONS = [
    ("edit", "e", "Edición", "write · edit · bash"),
    ("vision", "v", "Visión", "mmproj F16"),
    ("incognito", "i", "Incógnito", "sin guardar sesión"),
    ("ollama", "o", "Ollama", "respaldo · ignora el modelo"),
    ("laya", "s", "Laya", "system 1 · clasifica prompts en CPU"),
]

# Opciones activadas por defecto la primera vez
DEFAULT_ON = ("edit", "laya")

WARN_EDIT = "! Pi podrá escribir y ejecutar bash: solo en proyectos de confianza"

# ───────────────────────── estilos ─────────────────────────
BG_FOCUS = "48;5;236"
S_BORDER = "38;5;240"
S_DIM = "38;5;245"
S_FAINT = "38;5;241"
S_TEXT = "38;5;253"
S_BOLD = "1;38;5;255"
S_TITLE = "1;38;5;159"
S_ACCENT = "38;5;141"
S_KEY = "38;5;183"
S_GREEN = "38;5;114"
S_TEAL = "38;5;116"
S_PINK = "38;5;211"
S_ORANGE = "38;5;216"
S_YELLOW = "1;38;5;222"

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def seg_len(segs):
    return sum(len(t) for t, _ in segs)


def render_segs(segs, bg=""):
    out = []
    for text, style in segs:
        codes = ";".join(c for c in (bg, style) if c)
        out.append(f"\x1b[{codes}m{text}\x1b[0m" if codes else text)
    return "".join(out)


def fit(segs, width):
    """Recorta una lista de segmentos a `width` columnas (con …) y rellena."""
    total = seg_len(segs)
    if total > width:
        keep, res = width - 1, []
        for text, style in segs:
            if keep <= 0:
                break
            res.append((text[:keep], style))
            keep -= len(text)
        res.append(("…", S_DIM))
        return res
    return segs + [(" " * (width - total), "")]


# ───────────────────────── utilidades ─────────────────────────
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

    was_up = port_open(LLAMA_PORT)
    pkill("TERM", "laya_server.py")
    pkill("TERM", f"llama-server.*--port {LLAMA_PORT}")
    if not wait_closed(LLAMA_PORT, 6):
        pkill("KILL", f"llama-server.*--port {LLAMA_PORT}")
        if not wait_closed(LLAMA_PORT, 3):
            return False, f"El puerto {LLAMA_PORT} sigue ocupado (¿otro proceso que no es llama-server?)"
    wait_closed(LAYA_PORT, 3)
    return True, "llama-server apagado · modelo descargado" if was_up else "Nada que apagar: ya estaba offline"


# ───────────────────────── terminal ─────────────────────────
class Tty:
    def __init__(self):
        self.fd = os.open("/dev/tty", os.O_RDWR)
        self.old = termios.tcgetattr(self.fd)

    def __enter__(self):
        tty.setcbreak(self.fd)
        self.write("\x1b[?1049h\x1b[?25l")
        return self

    def __exit__(self, *exc):
        self.write("\x1b[?25h\x1b[?1049l")
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
        os.close(self.fd)

    def write(self, s):
        os.write(self.fd, s.encode("utf-8"))

    def size(self):
        try:
            c, r = os.get_terminal_size(self.fd)
            return c, r
        except OSError:
            return 80, 24

    def key(self, timeout=1.0):
        if not select.select([self.fd], [], [], timeout)[0]:
            return None
        data = os.read(self.fd, 1)
        if data == b"\x1b":
            if select.select([self.fd], [], [], 0.03)[0]:
                data += os.read(self.fd, 8)
            else:
                return "ESC"
            return {b"\x1b[A": "UP", b"\x1b[B": "DOWN", b"\x1bOA": "UP",
                    b"\x1bOB": "DOWN"}.get(data, "")
        if data in (b"\r", b"\n"):
            return "ENTER"
        if data == b"\x7f" or data == b"\x08":
            return "BACKSPACE"
        if data == b"\x03":
            return "CTRL_C"
        if data == b"\x15":
            return "CTRL_U"
        # carácter UTF-8 multibyte
        try:
            need = {0xC0: 1, 0xE0: 2, 0xF0: 3}
            b0 = data[0]
            extra = 3 if b0 >= 0xF0 else 2 if b0 >= 0xE0 else 1 if b0 >= 0xC0 else 0
            if extra:
                data += os.read(self.fd, extra)
            return data.decode("utf-8", "ignore")
        except Exception:
            return ""


# ───────────────────────── aplicación ─────────────────────────
class Menu:
    def __init__(self, term):
        self.t = term
        st = load_state()
        self.model = st.get("model", 0) if isinstance(st.get("model"), int) else 0
        if not 0 <= self.model < len(MODELS):
            self.model = 0
        self.opts = {k: bool(st.get("opts", {}).get(k, k in DEFAULT_ON))
                     for k, *_ in OPTIONS}
        self.args = st.get("args", "") if isinstance(st.get("args"), str) else ""
        # Presets de qwenh / qwen-edit / qwen-incognito...: sobreescriben lo recordado.
        pm = os.environ.get("QWEN_MENU_MODEL", "")
        ids = [m[0] for m in MODELS]
        if pm in ids:
            self.model = ids.index(pm)
        po = [x for x in os.environ.get("QWEN_MENU_OPTS", "").split(",") if x]
        if po:
            keep_laya = self.opts["laya"]
            self.opts = {k: k in po for k, *_ in OPTIONS}
            self.opts["laya"] = keep_laya and "nolaya" not in po or "laya" in po
        self.focus = 0
        self.editing = False
        self.buf = ""
        self.msg = ""
        self.msg_style = S_PINK
        self.paths = {}
        self.mmproj = ""
        self.llama_up = False
        self.laya_up = False
        self.refresh()

    # rows: modelos | opciones | args | lanzar
    @property
    def n_rows(self):
        return len(MODELS) + len(OPTIONS) + 2

    def row_kind(self, i):
        if i < len(MODELS):
            return "model", i
        i -= len(MODELS)
        if i < len(OPTIONS):
            return "opt", i
        i -= len(OPTIONS)
        return ("args", 0) if i == 0 else ("launch", 0)

    def refresh(self):
        override = os.environ.get("QWENX_MODEL")
        for idx, (mid, _l, _d, pats) in enumerate(MODELS):
            self.paths[mid] = find_model(pats, override if idx == 0 else None)
        self.mmproj = find_mmproj()
        self.llama_up = port_open(LLAMA_PORT)
        self.laya_up = port_open(LAYA_PORT)

    # ── dibujo ──
    def build(self):
        W = WIDTH - 2
        lines = []
        B = lambda s: (s, S_BORDER)

        def box(segs, bg=""):
            return render_segs([B("│ ")], "") + render_segs(fit(segs, W - 2), bg) + \
                render_segs([B(" │")], "")

        def section(title):
            head = f"─ {title} "
            return render_segs([B("├" + head + "─" * (W - len(head)) + "┤")])

        lines.append(render_segs([B("╭" + "─" * W + "╮")]))
        lines.append(box([("◆ ", S_ACCENT), ("QWEN3.6-35B", S_TITLE),
                          ("  pi · llama.cpp · laya", S_DIM)]))

        def status(name, port, up):
            return [("●" if up else "○", S_GREEN if up else S_DIM),
                    (f" {name} ", S_TEXT),
                    ("online" if up else "offline", S_GREEN if up else S_FAINT),
                    (f" :{port}", S_DIM)]

        lines.append(box(status("llama-server", LLAMA_PORT, self.llama_up) + [("   ", "")]
                         + status("laya", LAYA_PORT, self.laya_up)))

        # modelos
        lines.append(section("Modelo"))
        ollama = self.opts["ollama"]
        for i, (mid, label, desc, _p) in enumerate(MODELS):
            path = self.paths.get(mid, "")
            sel = i == self.model
            fg_lbl = S_FAINT if ollama else (S_BOLD if sel else S_TEXT)
            fg_desc = S_FAINT if ollama else S_DIM
            right = ([("no encontrado", S_PINK)] if not path
                     else [(gb(path), S_TEAL if not ollama else S_FAINT)])
            left = [("◉" if sel else "○", S_GREEN if sel and not ollama else S_DIM),
                    (f" {i + 1} ", S_DIM), (f"{label:<8}", fg_lbl),
                    (f" {desc}", fg_desc)]
            gap = W - 2 - seg_len(left) - seg_len(right)
            segs = left + [(" " * max(1, gap), "")] + right
            bg = BG_FOCUS if self.focus == i else ""
            lines.append(box(segs, bg))

        # opciones
        lines.append(section("Opciones"))
        for j, (key, hot, label, desc) in enumerate(OPTIONS):
            on = self.opts[key]
            segs = [("[", S_DIM), ("✓" if on else " ", S_YELLOW), ("] ", S_DIM),
                    (f"{hot} ", S_DIM),
                    (f"{label:<9}", S_BOLD if on else S_TEXT),
                    (f" {desc}", S_DIM)]
            bg = BG_FOCUS if self.focus == len(MODELS) + j else ""
            lines.append(box(segs, bg))
        if self.opts["edit"]:
            lines.append(box([("  " + WARN_EDIT, S_ORANGE)]))

        # argumentos
        lines.append(section("Argumentos para pi"))
        is_args_focus = self.focus == len(MODELS) + len(OPTIONS)
        if self.editing:
            left = [("› ", S_KEY), (self.buf, S_TEXT), ("▏", S_KEY)]
            right = [("enter ok · esc cancela", S_FAINT)]
        elif self.args:
            left = [("› ", S_DIM), (self.args, S_TEXT)]
            right = [("a", S_DIM)]
        else:
            left = [("› ", S_DIM),
                    ('opcional · ej: -p "resume este repo"', S_FAINT)]
            right = [("a", S_DIM)]
        gap = W - 2 - seg_len(left) - seg_len(right)
        if gap < 1:  # recorta la parte izquierda para dejar sitio a la derecha
            left = fit(left, W - 2 - seg_len(right) - 1)[:-1] + [("", "")]
            gap = 1
        lines.append(box(left + [(" " * gap, "")] + right,
                         BG_FOCUS if is_args_focus and not self.editing else ""))

        # lanzar
        lines.append(render_segs([B("├" + "─" * W + "┤")]))
        parts = [MODELS[self.model][1].lower()]
        if ollama:
            parts = ["ollama"]
        parts += [lbl.lower() for k, _h, lbl, _d in OPTIONS
                  if self.opts[k] and k != "ollama"]
        summary = " · ".join(parts)
        left = [("▶ ", S_GREEN), ("Lanzar", "1;38;5;151")]
        right = [(summary, S_DIM)]
        gap = W - 2 - seg_len(left) - seg_len(right)
        lines.append(box(left + [(" " * max(1, gap), "")] + right,
                         BG_FOCUS if self.focus == self.n_rows - 1 else ""))
        lines.append(render_segs([B("╰" + "─" * W + "╯")]))

        # ayuda
        def centered(segs):
            """Centra una línea de segmentos respecto al ancho de la caja."""
            return " " * max(0, (WIDTH - seg_len(segs)) // 2) + render_segs(segs)

        def hint(pairs):
            segs = []
            for k, d in pairs:
                segs += [(k, S_KEY), (f" {d}", S_FAINT), (" · ", S_FAINT)]
            return centered(segs[:-1])

        lines.append("")
        lines.append(hint([("↑↓", "mover"), ("espacio", "marcar"),
                           ("enter", "lanzar"), ("q", "salir")]))
        lines.append(hint([(f"1-{len(MODELS)}", "modelo"), ("a", "argumentos"),
                           ("m", "memoria"), ("c", "estado"), ("l", "laya"),
                           ("x", "apagar")]))
        if self.msg:
            lines.append("")
            lines.append(centered([(self.msg[:WIDTH], self.msg_style)]))
        return lines

    def draw(self):
        cols, _rows = self.t.size()
        pad = " " * max(0, (cols - WIDTH) // 2)
        out = ["\x1b[H\x1b[J"]
        for ln in self.build():
            out.append(pad + ln + "\x1b[0m\r\n")
        self.t.write("".join(out))

    # ── resultado ──
    def result(self, action):
        mid, _l, _d, _p = MODELS[self.model]
        use_vision = self.opts["vision"]
        save_state({"model": self.model, "opts": self.opts, "args": self.args})
        q = shlex.quote
        out = [
            f"ACTION={action}",
            f"MODEL_ID={mid}",
            f"MODEL_PATH={q(self.paths.get(mid, ''))}",
            f"OPT_EDIT={int(self.opts['edit'])}",
            f"OPT_VISION={int(use_vision)}",
            f"OPT_INCOGNITO={int(self.opts['incognito'])}",
            f"OPT_OLLAMA={int(self.opts['ollama'])}",
            f"OPT_LAYA={int(self.opts['laya'])}",
            f"MMPROJ_PATH={q(self.mmproj if use_vision else '')}",
            f"PI_ARGS={q(self.args)}",
        ]
        return "\n".join(out) + "\n"

    def try_launch(self):
        if not self.opts["ollama"]:
            mid = MODELS[self.model][0]
            if not self.paths.get(mid):
                self.msg = f"No hay GGUF para «{MODELS[self.model][1]}» en {MODELS_DIR}"
                return None
        if self.opts["vision"] and not self.opts["ollama"] and not self.mmproj:
            self.msg = f"No encuentro mmproj-*F16*.gguf en {MODELS_DIR}"
            return None
        return self.result("launch")

    # ── bucle ──
    def run(self):
        last = self.t.size()
        self.draw()
        while True:
            k = self.t.key(timeout=1.0)
            if k is None:
                before = (self.llama_up, self.laya_up)
                self.llama_up = port_open(LLAMA_PORT)
                self.laya_up = port_open(LAYA_PORT)
                if self.t.size() != last or before != (self.llama_up, self.laya_up):
                    last = self.t.size()
                    self.draw()
                continue
            if self.editing:
                if k == "ENTER":
                    self.args, self.editing = self.buf.strip(), False
                elif k == "ESC":
                    self.editing = False
                elif k == "BACKSPACE":
                    self.buf = self.buf[:-1]
                elif k == "CTRL_U":
                    self.buf = ""
                elif k == "CTRL_C":
                    return self.result("quit")
                elif len(k) == 1 and k.isprintable():
                    self.buf += k
                self.draw()
                continue

            self.msg, self.msg_style = "", S_PINK
            kind, idx = self.row_kind(self.focus)
            if k in ("q", "ESC", "CTRL_C"):
                return self.result("quit")
            elif k in ("UP", "k"):
                self.focus = (self.focus - 1) % self.n_rows
            elif k in ("DOWN", "j"):
                self.focus = (self.focus + 1) % self.n_rows
            elif k == " ":
                if kind == "model":
                    self.model = idx
                elif kind == "opt":
                    key = OPTIONS[idx][0]
                    self.opts[key] = not self.opts[key]
                elif kind == "args":
                    self.editing, self.buf = True, self.args
                else:
                    r = self.try_launch()
                    if r:
                        return r
            elif k == "ENTER":
                if kind == "args":
                    self.editing, self.buf = True, self.args
                else:
                    r = self.try_launch()
                    if r:
                        return r
            elif k.isdigit() and 1 <= int(k) <= len(MODELS):
                self.model = int(k) - 1
                self.focus = self.model
            elif k == "a":
                self.focus = len(MODELS) + len(OPTIONS)
                self.editing, self.buf = True, self.args
            elif k in [o[1] for o in OPTIONS]:
                key = next(o[0] for o in OPTIONS if o[1] == k)
                self.opts[key] = not self.opts[key]
                self.focus = len(MODELS) + [o[0] for o in OPTIONS].index(key)
            elif k == "m":
                return self.result("mem")
            elif k == "c":
                return self.result("status")
            elif k == "l":
                return self.result("laya")
            elif k == "x":
                self.msg_style = S_YELLOW
                self.msg = "Apagando llama-server..."
                self.draw()
                ok, text = stop_servers()
                self.msg, self.msg_style = text, (S_GREEN if ok else S_PINK)
                self.llama_up = port_open(LLAMA_PORT)
                self.laya_up = port_open(LAYA_PORT)
            elif k == "r":
                self.refresh()
            self.draw()


def main():
    try:
        term = Tty()
    except OSError:
        sys.stdout.write("ACTION=quit\n")
        return 0
    try:
        with term:
            res = Menu(term).run()
    except KeyboardInterrupt:
        res = "ACTION=quit\n"
    sys.stdout.write(res)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
