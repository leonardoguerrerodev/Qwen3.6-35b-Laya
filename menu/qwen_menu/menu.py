"""Estado del menú, entrada de teclado y resultado para el shell."""
import os
import shlex

from .config import (DEFAULT_ON, HOME, KEV_PORT, LAYA_PORT, LLAMA_PORT, MODELS, MODELS_DIR,
                     OPTIONS)
from .style import S_DIM, S_GREEN, S_PINK, S_YELLOW
from .system import (complete_dir, find_mmproj, find_model, load_state, pick_dir_gui,
                     port_open, save_state, short_path, stop_servers)
from .view import ViewMixin

OPT_KEYS = {o[1]: o[0] for o in OPTIONS}            # tecla → clave de opción
ACTION_KEYS = {"m": "mem", "c": "status", "l": "laya"}   # tecla → ACTION de salida


class Menu(ViewMixin):
    def __init__(self, term):
        self.t = term
        st = load_state()
        self.model = st.get("model", 0) if isinstance(st.get("model"), int) else 0
        if not -1 <= self.model < len(MODELS):   # -1 = «Ninguno» (sin modelo grande)
            self.model = 0
        self.opts = {k: bool(st.get("opts", {}).get(k, k in DEFAULT_ON))
                     for k, *_ in OPTIONS}
        self.args = st.get("args", "") if isinstance(st.get("args"), str) else ""
        # Carpeta de Claude: la actual del shell (donde ejecutaste `qwen`); si es ~, la última usada.
        saved = st.get("cdir", "") if isinstance(st.get("cdir"), str) else ""
        cwd = os.getcwd()
        self.cdir = os.environ.get("QWEN_CLAUDE_DIR") or (
            saved if cwd == HOME and os.path.isdir(saved) else cwd)
        # Presets de qwenh / qwen-edit / qwen-incognito...: sobreescriben lo recordado.
        pm = os.environ.get("QWEN_MENU_MODEL", "")
        ids = [m[0] for m in MODELS]
        if pm in ids:
            self.model = ids.index(pm)
        elif pm == "none":
            self.model = -1
        po = [x for x in os.environ.get("QWEN_MENU_OPTS", "").split(",") if x]
        if po:
            keep_laya, keep_kev = self.opts["laya"], self.opts["kev"]
            self.opts = {k: k in po for k, *_ in OPTIONS}
            self.opts["laya"] = keep_laya and "nolaya" not in po or "laya" in po
            self.opts["kev"] = keep_kev and "nokev" not in po or "kev" in po
        self.normalize()
        self.focus = 0
        self.editing = False
        self.edit_target = "args"   # "args" | "dir"
        self.buf = ""
        self.msg = ""
        self.msg_style = S_PINK
        self.paths = {}
        self.mmproj = ""
        self.llama_up = False
        self.laya_up = False
        self.kev_up = False
        self.refresh()
        self._init_view()

    def normalize(self, prefer=None):
        """Reglas entre opciones. `prefer` = opción que el usuario acaba de tocar.
        - kev necesita laya; Claude y Kev GPU necesitan kev.
        - Claude y Kev GPU comparten GPU con el modelo grande: exigen «Ninguno» y no valen con Ollama.
        """
        o = self.opts
        if prefer == "laya" and not o["laya"]:
            o["kev"] = False
        if prefer in ("laya", "kev") and not o["kev"]:
            o["claude"] = o["kevgpu"] = False
        if prefer in ("claude", "kevgpu") and o[prefer]:
            self.model = -1
            o["ollama"] = False
        if prefer == "ollama" and o["ollama"]:
            o["claude"] = o["kevgpu"] = False
        if self.model >= 0 or o["ollama"]:
            o["claude"] = o["kevgpu"] = False
        if o["claude"] or o["kevgpu"]:
            o["kev"] = True
        if o["kev"]:
            o["laya"] = True

    def toggle(self, key):
        """Marca/desmarca una opción y aplica las reglas de normalize()."""
        before, model0 = dict(self.opts), self.model
        self.opts[key] = not self.opts[key]
        self.normalize(key)
        # aviso: qué se activó/cambió solo por las dependencias (kev→laya, Claude/Kev GPU→«Ninguno»)
        if self.opts[key]:
            names = {k: lbl for k, _h, lbl, _d in OPTIONS}
            extra = [names[k] for k in self.opts if k != key and self.opts[k] and not before[k]]
            notes = []
            if extra:
                notes.append("activó también " + ", ".join(extra))
            if model0 >= 0 and self.model < 0:
                notes.append("modelo → Ninguno")
            if notes:
                self.msg, self.msg_style = f"{names[key]}: " + " · ".join(notes), S_YELLOW
        elif key == "kevgpu" and self.opts["claude"]:
            self.msg, self.msg_style = "Claude seguirá con kev en CPU", S_YELLOW

    def set_model(self, i, toggle=False):
        """i = -1 → Ninguno. Con toggle, pulsar el modelo ya elegido lo deselecciona."""
        self.model = -1 if (toggle and i >= 0 and i == self.model) else i
        self.normalize()

    @property
    def nm(self):
        return len(MODELS) + 1   # filas de la sección Modelo (Ninguno + modelos)

    # rows: modelos | opciones | args | lanzar
    @property
    def n_rows(self):
        return self.nm + len(OPTIONS) + 3

    def row_kind(self, i):
        if i < self.nm:
            return "model", i - 1      # idx -1 = Ninguno
        i -= self.nm
        if i < len(OPTIONS):
            return "opt", i
        i -= len(OPTIONS)
        return ("args", 0) if i == 0 else ("dir", 0) if i == 1 else ("launch", 0)

    def refresh(self):
        override = os.environ.get("QWENX_MODEL")
        for idx, (mid, _l, _d, pats) in enumerate(MODELS):
            self.paths[mid] = find_model(pats, override if idx == 0 else None)
        self.mmproj = find_mmproj()
        self._poll_servers()

    # ── resultado ──
    def result(self, action):
        nomodel = self.model < 0 and not self.opts["ollama"]
        mid = "" if self.model < 0 else MODELS[self.model][0]
        use_vision = self.opts["vision"] and not nomodel
        save_state({"model": self.model, "opts": self.opts, "args": self.args,
                    "cdir": self.cdir})
        q = shlex.quote
        out = [
            f"ACTION={action}",
            f"MODEL_ID={mid}",
            f"MODEL_PATH={q(self.paths.get(mid, ''))}",
            f"OPT_EDIT={int(self.opts['edit'] and not nomodel)}",
            f"OPT_VISION={int(use_vision)}",
            f"OPT_INCOGNITO={int(self.opts['incognito'])}",
            f"OPT_OLLAMA={int(self.opts['ollama'])}",
            f"OPT_LAYA={int(self.opts['laya'])}",
            f"OPT_KEV={int(self.opts['kev'] and self.opts['laya'])}",
            f"OPT_NOMODEL={int(nomodel)}",
            f"OPT_CLAUDE={int(self.opts['claude'] and nomodel)}",
            f"OPT_KEVGPU={int(self.opts['kevgpu'] and nomodel)}",
            f"MMPROJ_PATH={q(self.mmproj if use_vision else '')}",
            f"PI_ARGS={q(self.args)}",
            f"CLAUDE_DIR={q(self.cdir)}",
        ]
        return "\n".join(out) + "\n"

    def try_launch(self):
        if self.model < 0 and not self.opts["ollama"]:
            if not (self.opts["claude"] or self.opts["laya"]):
                self.msg = "Sin modelo: marca Claude, Laya o Kev (o elige un modelo)"
                return None
            if self.opts["claude"] and not os.path.isdir(self.cdir):
                self.msg = f"La carpeta de Claude no existe: {short_path(self.cdir)}"
                return None
            return self.result("launch")
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
                last = self._idle(last)
                continue
            self._follow = True
            res = self._edit_key(k) if self.editing else self._nav_key(k)
            if res:
                return res
            self.draw()

    def _idle(self, last):
        """Sin tecla: refresca estado de servidores y tamaño; redibuja si cambió algo."""
        before = (self.llama_up, self.laya_up, self.kev_up)
        self._poll_servers()
        cur = self.t.size()
        if cur != last or before != (self.llama_up, self.laya_up, self.kev_up):
            self.draw()
        return cur

    def _poll_servers(self):
        self.llama_up = port_open(LLAMA_PORT)
        self.laya_up = port_open(LAYA_PORT)
        self.kev_up = port_open(KEV_PORT)

    # ── teclas ──
    def _start_edit(self, target):
        self.editing, self.edit_target = True, target
        self.buf = self.args if target == "args" else short_path(self.cdir)

    def _edit_key(self, k):
        """Tecla mientras se edita args/carpeta. Devuelve resultado o None."""
        if k == "ENTER":
            if self.edit_target == "dir":
                d = os.path.abspath(os.path.expanduser(self.buf.strip() or self.cdir))
                if os.path.isdir(d):
                    self.cdir, self.editing = d, False
                else:
                    self.msg, self.msg_style = f"No existe: {short_path(d)}", S_PINK
            else:
                self.args, self.editing = self.buf.strip(), False
        elif k == "TAB" and self.edit_target == "dir":
            self.buf, n = complete_dir(self.buf)
            self.msg, self.msg_style = (f"{n} coincidencias" if n > 1 else ""), S_DIM
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
        return None

    def _press(self, kind, idx, k):
        """Espacio / enter sobre la fila con foco."""
        if k == " " and kind == "model":
            self.set_model(idx, toggle=True)
        elif k == " " and kind == "opt":
            self.toggle(OPTIONS[idx][0])
        elif kind in ("args", "dir"):
            self._start_edit(kind)
        else:
            return self.try_launch()
        return None

    def _pick_dir(self):
        self.focus = self.nm + len(OPTIONS) + 1
        self.msg, self.msg_style = "Abriendo selector de carpetas…", S_YELLOW
        self.draw()
        d = pick_dir_gui(self.cdir)
        if d:
            self.cdir, self.msg = d, ""
        else:
            self.msg, self.msg_style = "Sin selector gráfico o cancelado (usa d)", S_PINK

    def _stop(self):
        self.msg_style = S_YELLOW
        self.msg = "Apagando llama-server..."
        self.draw()
        ok, text = stop_servers()
        self.msg, self.msg_style = text, (S_GREEN if ok else S_PINK)
        self._poll_servers()

    def _nav_key(self, k):
        """Tecla en modo navegación. Devuelve resultado (cadena para eval) o None."""
        self.msg, self.msg_style = "", S_PINK
        kind, idx = self.row_kind(self.focus)
        if k in ("q", "ESC", "CTRL_C"):
            return self.result("quit")
        if k in ("UP", "k"):
            self.focus = (self.focus - 1) % self.n_rows
        elif k in ("DOWN", "j"):
            self.focus = (self.focus + 1) % self.n_rows
        elif k in (" ", "ENTER"):
            return self._press(kind, idx, k)
        elif k.isdigit() and 0 <= int(k) <= len(MODELS):
            self.set_model(int(k) - 1)       # 0 = Ninguno
            self.focus = self.model + 1
        elif k == "a":
            self.focus = self.nm + len(OPTIONS)
            self._start_edit("args")
        elif k == "d":
            self.focus = self.nm + len(OPTIONS) + 1
            self._start_edit("dir")
        elif k == "D":
            self._pick_dir()
        elif k in OPT_KEYS:
            self.toggle(OPT_KEYS[k])
            self.focus = self.nm + [o[0] for o in OPTIONS].index(OPT_KEYS[k])
        elif k in ACTION_KEYS:
            return self.result(ACTION_KEYS[k])
        elif k == "x":
            self._stop()
        elif k == "r":
            self.refresh()
        elif k in ("PgUp", "PgDn", "Home", "End"):
            self.scroll_by(k)
        return None
