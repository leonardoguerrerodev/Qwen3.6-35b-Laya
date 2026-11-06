"""Estado del menú, entrada de teclado y resultado para el shell."""
import os
import shlex
import subprocess

from .config import (CHAT_MODELS, DEFAULT_ON, HOME, KEV_PORT, LAYA_PORT, LLAMA_PORT, MODELS, MODELS_DIR,
                     NO_VISION, OPTIONS, PARAMS, QWEN_DATA, VOZ_PORT, WEB_PORT)
from . import flags
from .style import S_DIM, S_GREEN, S_PINK, S_YELLOW
from .system import (complete_dir, ctx_for, kv_for, find_mmproj, find_model, lan_ip, web_toggle, load_params, load_state,
                     pick_dir_gui, port_open, save_state, short_path, stop_servers, voz_perfil)
from . import profiles
from .view import ViewMixin

OPT_KEYS = {o[1]: o[0] for o in OPTIONS}            # tecla → clave de opción
PARAM_KEYS = {p[1]: p[0] for p in PARAMS}           # tecla → clave de parámetro
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
        self.params = load_params(st)
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
        # Perfiles por modelo (qwen_menu/profiles.py): ctx/temp/KV viven en self.params; el resto en self.prof
        self.pdoc = profiles.load_all()
        self.prof = {}
        self.pname = ""
        self.pe = False             # editor de perfil abierto
        self._pdel = False          # «X» pulsada una vez (confirma el borrado)
        self._pe_main_focus = 0
        self.sel = False            # texto del campo seleccionado: la primera tecla lo reemplaza
        self.manual, self.manual_ctx = "", ""   # «lanzar a mano» (L en el editor de perfil)
        self._cmd = (None, [], "")              # caché de la vista del comando
        self.fl, self.fl_filter, self._fl_focus = False, "", 0   # pantalla de flags (? en el editor)
        self._load_profile()
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
        self.voz_up = False
        self.refresh()
        self._init_view()

    def normalize(self, prefer=None):
        """Reglas entre opciones. `prefer` = opción que el usuario acaba de tocar.
        Solo dependencias técnicas: kev necesita laya; Claude y Kev GPU necesitan kev.
        Cualquier modelo (o «Ninguno», u Ollama) se combina con cualquier opción.
        """
        o = self.opts
        if prefer in ("edit", "laya", "kev", "claude", "kevgpu") and o[prefer]:
            o["chat"] = False   # pedir algo de código/laya saca del modo Chat
        if o["chat"]:           # Chat: sin escritura ni laya (su extensión no corre)
            o["edit"] = False
            o["laya"] = o["kev"] = o["claude"] = o["kevgpu"] = False
            if prefer == "chat":
                o["incognito"] = True   # solo al activarlo: después Incógnito se quita y pone libre
        if prefer == "laya" and not o["laya"]:
            o["kev"] = False
        if prefer in ("laya", "kev") and not o["kev"]:
            o["claude"] = o["kevgpu"] = False
        if o["claude"] or o["kevgpu"]:
            o["kev"] = True
        if o["kev"]:
            o["laya"] = True

    def toggle(self, key):
        """Marca/desmarca una opción y aplica las reglas de normalize()."""
        before = dict(self.opts)
        self.opts[key] = not self.opts[key]
        self.normalize(key)
        # aviso: qué se activó solo por las dependencias (kev→laya, Claude/Kev GPU→kev)
        if self.opts[key]:
            names = {k: lbl for k, _h, lbl, _d in OPTIONS}
            extra = [names[k] for k in self.opts if k != key and self.opts[k] and not before[k]]
            notes = []
            if extra:
                notes.append("activó también " + ", ".join(extra))
            if notes:
                self.msg, self.msg_style = f"{names[key]}: " + " · ".join(notes), S_YELLOW
        elif key == "kevgpu" and self.opts["claude"]:
            self.msg, self.msg_style = "Claude seguirá con kev en CPU", S_YELLOW

    def cycle(self, key):
        """Pasa el parámetro `key` a su siguiente valor (vuelve al primero tras el último)."""
        vals = next(p[3] for p in PARAMS if p[0] == key)
        cur = self.params[key]   # un valor de perfil fuera de la lista vuelve al primero
        self.params[key] = vals[(vals.index(cur) + 1) % len(vals)] if cur in vals else vals[0]

    def set_model(self, i, toggle=False):
        """i = -1 → Ninguno. Con toggle, pulsar el modelo ya elegido lo deselecciona."""
        self._store_profile()
        prev = self.model
        self.model = -1 if (toggle and i >= 0 and i == self.model) else i
        was, now = (0 <= x and MODELS[x][0] in CHAT_MODELS for x in (prev, self.model))
        if now and not was:        # modelo de chat: Chat solo, recordando cómo estaban las opciones
            self._pre_chat = dict(self.opts)
            self.opts["chat"] = self.opts["incognito"] = True
        elif was and not now:      # sale de un modelo de chat: vuelve a como estaba
            self.opts = {**getattr(self, "_pre_chat", self.opts), "chat": False}
        self.normalize()
        self._load_profile()

    @property
    def nm(self):
        return len(MODELS) + 1   # filas de la sección Modelo (Ninguno + modelos)

    @property
    def na(self):
        return self.nm + len(OPTIONS) + len(profiles.ROW_PARAMS)   # fila de los argumentos

    # rows: modelos | opciones | parámetros | args | carpeta | lanzar
    @property
    def n_rows(self):
        return self.na + 3

    def row_kind(self, i):
        if i < self.nm:
            return "model", i - 1      # idx -1 = Ninguno
        i -= self.nm
        if i < len(OPTIONS):
            return "opt", i
        i -= len(OPTIONS)
        if i < len(profiles.ROW_PARAMS):
            return "param", i
        i -= len(profiles.ROW_PARAMS)
        return ("args", 0) if i == 0 else ("dir", 0) if i == 1 else ("launch", 0)

    def refresh(self):
        override = os.environ.get("QWENX_MODEL")
        for idx, (mid, _l, _d, pats) in enumerate(MODELS):
            self.paths[mid] = find_model(pats, override if idx == 0 else None)
        self.mmproj = {mid: find_mmproj(mid) for mid, *_ in MODELS}   # cada modelo, su visión
        self._poll_servers()

    # ── resultado ──
    def launch_vars(self):
        """Variables que recibe el shell (sin ACTION). Las mismas arman la vista del comando (flags.build_cmd)."""
        nomodel = self.model < 0 and not self.opts["ollama"]
        mid = "" if self.model < 0 else MODELS[self.model][0]
        use_vision = self.opts["vision"] and not nomodel and mid not in NO_VISION
        p = self.prof.get
        return {
            "MODEL_ID": mid,
            "MODEL_PATH": self.paths.get(mid, ""),
            "OPT_EDIT": str(int(self.opts["edit"] and not nomodel)),
            "OPT_VISION": str(int(use_vision)),
            "OPT_INCOGNITO": str(int(self.opts["incognito"])),
            "OPT_CHAT": str(int(self.opts["chat"] and not nomodel)),
            "OPT_OLLAMA": str(int(self.opts["ollama"])),
            "OPT_LAYA": str(int(self.opts["laya"])),
            "OPT_KEV": str(int(self.opts["kev"] and self.opts["laya"])),
            "OPT_VOZ": str(int(self.opts["voz"])),
            "OPT_NOMODEL": str(int(nomodel)),
            "OPT_CLAUDE": str(int(self.opts["claude"])),
            "OPT_KEVGPU": str(int(self.opts["kevgpu"])),
            "MMPROJ_PATH": self.mmproj.get(mid, "") if use_vision else "",
            "PI_ARGS": self.args,
            "CLAUDE_DIR": self.cdir,
            # a mano: Pi debe conocer el -c real (su ventana de contexto sale de QWENX_CTX)
            "P_CTX": self.manual_ctx if self.manual else ctx_for(mid, self.params["ctx"]),
            "P_TEMP": self.params["temp"],
            "P_KVQ": kv_for(mid, self.params["kvq"]),
            "P_IDIOMA": self.params["idioma"],
            "P_HARNESS": self.params["harness"],
            "P_KEV": self.params["kev"],
            "P_TOPP": p("top_p", ""), "P_TOPK": p("top_k", ""), "P_MINP": p("min_p", ""),
            "P_NCMOE": p("ncmoe", ""), "P_NGL": p("ngl", ""), "P_LOADMODE": p("loadmode", ""),
            "P_BATCH": p("batch", ""), "P_UB": p("ub", ""),
            "P_RAZON": p("razon", ""), "P_EFFORT": p("effort", ""), "P_MTP": p("mtp", "auto"),
            "P_DRAFT": p("draft", ""),
            "P_EXTRA": profiles.extra_words(p("extra", "")),   # palabras ya entrecomilladas (eval en llama.sh)
            "P_MANUAL": self.manual,                            # idem: reemplaza todo el armado
        }

    def result(self, action):
        self._store_profile()
        save_state({"model": self.model, "opts": self.opts, "args": self.args,
                    "cdir": self.cdir, "params": self.params})
        q = shlex.quote
        out = [f"ACTION={action}"] + [f"{k}={q(v)}" for k, v in self.launch_vars().items()]
        return "\n".join(out) + "\n"

    def command(self):
        """(palabras, aviso) del comando de llama-server con el perfil actual; lo arma lib/llama.sh (con caché)."""
        v = self.launch_vars()
        key = tuple(sorted(v.items()))
        if self._cmd[0] != key:
            self._cmd = (key, *flags.build_cmd(v))
        return self._cmd[1], self._cmd[2]

    def try_launch(self):
        if self.opts["claude"] and not os.path.isdir(self.cdir):
            self.msg = f"La carpeta de Claude no existe: {short_path(self.cdir)}"
            return None
        if self.model < 0 and not self.opts["ollama"]:
            if not (self.opts["claude"] or self.opts["laya"]):
                self.msg = "Sin modelo: marca Claude, Laya o Kev (o elige un modelo)"
                return None
            return self.result("launch")
        if not self.opts["ollama"]:
            mid = MODELS[self.model][0]
            if not self.paths.get(mid):
                self.msg = f"No hay GGUF para «{MODELS[self.model][1]}» en {MODELS_DIR}"
                return None
        mid = MODELS[self.model][0]
        if (self.opts["vision"] and not self.opts["ollama"] and not self.mmproj.get(mid)
                and mid not in NO_VISION):
            self.msg = f"No encuentro el mmproj de «{MODELS[self.model][1]}» en {MODELS_DIR}"
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
            res = (self._edit_key(k) if self.editing else self._fl_key(k) if self.fl
                   else self._pe_key(k) if self.pe else self._nav_key(k))
            if res:
                return res
            self.draw()

    def _idle(self, last):
        """Sin tecla: refresca estado de servidores y tamaño; redibuja si cambió algo."""
        before = (self.llama_up, self.laya_up, self.kev_up, self.voz_up)
        self._poll_servers()
        cur = self.t.size()
        if cur != last or before != (self.llama_up, self.laya_up, self.kev_up, self.voz_up):
            self.draw()
        return cur

    def _poll_servers(self):
        self.llama_up = port_open(LLAMA_PORT)
        self.laya_up = port_open(LAYA_PORT)
        self.kev_up = port_open(KEV_PORT)
        self.voz_up = port_open(VOZ_PORT)

    # ── teclas ──
    def _start_edit(self, target):
        self.editing, self.edit_target, self.sel = True, target, False
        self.buf = self.args if target == "args" else short_path(self.cdir)

    def _edit_key(self, k):
        """Tecla mientras se edita args/carpeta. Devuelve resultado o None."""
        if k == "ENTER":
            if self.edit_target == "ffilter":
                self.fl_filter, self.editing = self.buf.strip(), False
            elif self.edit_target.startswith("p"):
                self._pe_commit()
            elif self.edit_target == "dir":
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
            self.buf, self.sel = ("" if self.sel else self.buf[:-1]), False
            if self.edit_target == "ffilter":
                self.focus = 0
        elif k == "CTRL_U":
            self.buf = ""
        elif k == "CTRL_C":
            return self.result("quit")
        elif len(k) == 1 and k.isprintable():
            self.buf, self.sel = (k if self.sel else self.buf + k), False
            if self.edit_target == "ffilter":   # el filtro se aplica mientras escribes
                self.focus = 0
        return None

    def _press(self, kind, idx, k):
        """Espacio sobre la fila con foco: marca, cambia o abre la edición (enter solo lanza)."""
        if k == " " and kind == "model":
            self.set_model(idx, toggle=True)
        elif k == " " and kind == "opt":
            self.toggle(OPTIONS[idx][0])
        elif kind == "param":            # siguiente valor
            self.cycle(profiles.ROW_PARAMS[idx][0])
        elif kind in ("args", "dir"):
            self._start_edit(kind)
        else:  # fila Lanzar: solo enter lanza
            self.msg, self.msg_style = "Pulsa enter para lanzar", S_YELLOW
        return None

    def _pick_dir(self):
        self.focus = self.na + 1
        self.msg, self.msg_style = "Abriendo selector de carpetas…", S_YELLOW
        self.draw()
        d = pick_dir_gui(self.cdir)
        if d:
            self.cdir, self.msg = d, ""
        else:
            self.msg, self.msg_style = "Sin selector gráfico o cancelado (usa d)", S_PINK

    def _stop(self):
        self.msg_style = S_YELLOW
        self.msg = "Apagando servidores…"
        self.draw()
        ok, text = stop_servers()
        self.msg, self.msg_style = text, (S_GREEN if ok else S_PINK)
        self._poll_servers()

    # ── perfiles por modelo (qwen_menu/profiles.py) ──
    def _mid(self):
        return MODELS[self.model][0] if self.model >= 0 else ""

    def _load_profile(self):
        """Carga el perfil activo del modelo: ctx/temp/KV a self.params, el resto a self.prof."""
        mid = self._mid()
        if not mid:
            self.prof, self.pname = {}, ""
            return
        seed = {**profiles.DEFAULTS, **{k: self.params[k] for k in profiles.SHARED}}
        ent = profiles.entry(self.pdoc, mid, seed)
        self.pname = ent["activo"]
        p = ent["perfiles"][self.pname]
        for k in profiles.SHARED:
            self.params[k] = p[k]
        self.prof = {k: p[k] for k in profiles.EXTRA_KEYS}

    def _store_profile(self):
        """Guarda los valores de trabajo en el perfil activo (al cambiar de modelo/perfil, lanzar o salir)."""
        mid = self._mid()
        ent = self.pdoc.get(mid) if mid else None
        if not ent or self.pname not in ent["perfiles"]:
            return
        cur = ent["perfiles"][self.pname]
        new = {**cur, **{k: self.params[k] for k in profiles.SHARED}, **self.prof}
        if new != cur:
            ent["perfiles"][self.pname] = new
            profiles.save_all(self.pdoc)

    def _cycle_profile(self):
        """Tecla p: siguiente perfil del modelo."""
        if self.model < 0:
            self.msg, self.msg_style = "Elige un modelo para usar perfiles", S_YELLOW
            return
        self._store_profile()
        ent = self.pdoc[self._mid()]
        names = list(ent["perfiles"])
        ent["activo"] = names[(names.index(self.pname) + 1) % len(names)]
        profiles.save_all(self.pdoc)
        self._load_profile()
        self.msg, self.msg_style = f"perfil «{self.pname}»", S_GREEN

    def _field(self, key, desc, vals):
        """(descripción, valores de ciclo) de un campo del perfil; Capas GPU, Effort y MTP dependen del modelo."""
        if key == "effort":
            return profiles.effort_info(self.paths.get(self._mid(), ""))
        if key == "mtp":
            return profiles.mtp_info(self.paths.get(self._mid(), ""))
        if key != "ngl":
            return desc, vals
        mid = self._mid()
        cache = self.__dict__.setdefault("_ngl", {})
        if mid not in cache:
            cache[mid] = profiles.ngl_info(self.paths.get(mid, ""))[1:]
        return cache[mid]

    def _pget(self, k):
        return self.params[k] if k in profiles.SHARED else self.prof.get(k, "")

    def _pset(self, k, v):
        if k in profiles.SHARED:
            self.params[k] = v
        else:
            self.prof[k] = v

    def _pe_open(self):
        """Tecla P: abre el editor del perfil activo."""
        if self.model < 0:
            self.msg, self.msg_style = "Elige un modelo para editar su perfil", S_YELLOW
            return
        self.pe, self._pe_main_focus, self.focus, self._pdel = True, self.focus, 0, False
        self.scroll = 0

    def _pe_close(self):
        self._store_profile()
        self.pe, self.editing, self.focus = False, False, self._pe_main_focus

    def _pdelete(self, ent):
        old = self.pname
        names = list(ent["perfiles"])
        nxt = names[(names.index(old) + 1) % len(names)]
        del ent["perfiles"][old]
        ent["activo"] = nxt
        profiles.save_all(self.pdoc)
        self._load_profile()
        self.msg, self.msg_style = f"borrado «{old}» · ahora «{self.pname}»", S_GREEN

    def _pe_commit(self):
        """ENTER mientras se escribe un valor, un nombre nuevo o un renombrado."""
        t, ent = self.edit_target, self.pdoc[self._mid()]
        if t.startswith("pfield:"):
            key = t.split(":", 1)[1]
            ok, val, msg = profiles.validate(key, self.buf)
            if ok:
                self._pset(key, val)
                self.editing = False
            else:
                self.msg, self.msg_style = msg, S_PINK
            return
        ok, name, msg = profiles.check_name(ent, self.buf, current=self.pname if t == "pren" else None)
        if not ok:
            self.msg, self.msg_style = msg, S_PINK
            return
        self._store_profile()
        if t == "pren":
            profiles.rename(ent, self.pname, name)
        else:                          # pnew: copia del perfil actual
            ent["perfiles"][name] = dict(ent["perfiles"][self.pname])
            ent["activo"] = name
        profiles.save_all(self.pdoc)
        self._load_profile()
        self.editing = False
        self.msg, self.msg_style = f"perfil «{name}»", S_GREEN

    def _pe_key(self, k):
        """Tecla con el editor de perfil abierto. Devuelve resultado o None."""
        self.msg, self.msg_style = "", S_PINK
        armed, self._pdel = self._pdel, False
        key, _lbl, _desc, vals = profiles.FIELDS[self.focus]
        vals = self._field(key, _desc, vals)[1]
        ent = self.pdoc[self._mid()]
        if k in ("q", "ESC"):
            self._pe_close()
        elif k == "CTRL_C":
            return self.result("quit")
        elif k in ("UP", "k"):
            self.focus = (self.focus - 1) % len(profiles.FIELDS)
        elif k in ("DOWN", "j"):
            self.focus = (self.focus + 1) % len(profiles.FIELDS)
        elif k == " " and vals:        # siguiente valor de la lista
            cur = self._pget(key)
            self._pset(key, vals[(vals.index(cur) + 1) % len(vals)] if cur in vals else vals[0])
        elif k in (" ", "ENTER"):      # escribir un valor libre
            self.editing, self.edit_target, self.buf = True, f"pfield:{key}", self._pget(key)
            self.sel = bool(self.buf)
        elif k == "p":
            self._cycle_profile()
        elif k == "c":
            self._copy_cmd()
        elif k == "L":
            return self._manual_launch()
        elif k == "?":
            self.fl, self._fl_focus, self.focus, self.scroll = True, self.focus, 0, 0
        elif k == "n":
            self.editing, self.edit_target = True, "pnew"
            self.buf = profiles.unique_name(ent, self.pname)
            self.sel = True
        elif k == "R":
            self.editing, self.edit_target, self.buf = True, "pren", self.pname
            self.sel = True
        elif k == "X":
            if len(ent["perfiles"]) < 2:
                self.msg = "No puedes borrar el único perfil del modelo"
            elif armed:
                self._pdelete(ent)
            else:
                self._pdel = True
                self.msg, self.msg_style = f"Pulsa X otra vez para borrar «{self.pname}»", S_YELLOW
        elif k in ("PgUp", "PgDn", "Home", "End"):
            self.scroll_by(k)
        return None

    # ── comando de llama-server (editor de perfil) ──
    def _copy_cmd(self):
        words, err = self.command()
        if not words:
            self.msg, self.msg_style = f"sin comando: {err}", S_PINK
            return
        prog = flags.copy(shlex.join(words))
        self.msg, self.msg_style = ((f"comando copiado ({prog}) · pégalo en una terminal", S_GREEN) if prog
                                    else ("no hay wl-copy ni xclip para copiar", S_PINK))

    def _manual_launch(self):
        """Tecla L: abre el comando en $EDITOR (una opción por línea), y al guardar lo lanza tal cual + el agente."""
        words, err = self.command()
        if not words:
            self.msg, self.msg_style = f"sin comando: {err}", S_PINK
            return None
        path = os.path.join(QWEN_DATA, "comando-manual.txt")
        head = [f"# Lanzar a mano · perfil «{self.pname}» de {MODELS[self.model][1]} · agente: {self.params['harness']}",
                "# Una opción por línea; # comenta. Cambia lo que quieras, guarda y cierra el editor para lanzar.",
                "# Borra todo (o deja solo comentarios) para cancelar y volver al menú.",
                f"# Deja --port {LLAMA_PORT}: ahí se conectan el agente, laya y la web.", ""]
        try:
            os.makedirs(QWEN_DATA, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(head + [shlex.join(g) for g in flags.groups(words)]) + "\n")
            editor = shlex.split(os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano")
            with self.t.suspended():   # ponytail: editor de terminal; uno gráfico (kate) vuelve antes de guardar
                subprocess.call(editor + [path], stdin=self.t.fd, stdout=self.t.fd, stderr=self.t.fd)
            with open(path, encoding="utf-8") as f:
                words = shlex.split(f.read(), comments=True)
        except (OSError, ValueError) as e:
            self.msg, self.msg_style = f"lanzar a mano: {e}", S_PINK
            return None
        if not words:
            self.msg, self.msg_style = "lanzar a mano: cancelado", S_YELLOW
            return None
        val = lambda *names: next((words[i + 1] for i, w in enumerate(words[:-1]) if w in names), "")
        if val("--port") != str(LLAMA_PORT):
            self.msg, self.msg_style = f"lanzar a mano: falta --port {LLAMA_PORT} (el agente se conecta ahí)", S_PINK
            return None
        self.manual = " ".join(shlex.quote(w) for w in words)
        self.manual_ctx = val("-c", "--ctx-size")
        res = self.try_launch()
        if res is None:
            self.manual = self.manual_ctx = ""
        return res

    # ── pantalla de flags (? en el editor de perfil) ──
    def fl_items(self):
        """Catálogo de llama-server --help filtrado por el texto de / (nombre, sección o explicación)."""
        f = (self.buf if self.editing and self.edit_target == "ffilter" else self.fl_filter).lower()
        cat = flags.catalog()
        return [it for it in cat if not f or f in " ".join((it[0], it[2], it[3], flags.es(it[1]))).lower()]

    def _fl_key(self, k):
        self.msg, self.msg_style = "", S_PINK
        n = max(1, len(self.fl_items()))
        if k in ("q", "ESC", "?"):
            self.fl, self.focus, self.scroll = False, self._fl_focus, 0
        elif k == "CTRL_C":
            return self.result("quit")
        elif k in ("UP", "k"):
            self.focus = (self.focus - 1) % n
        elif k in ("DOWN", "j"):
            self.focus = (self.focus + 1) % n
        elif k == "/":
            self.editing, self.edit_target, self.buf, self.sel = True, "ffilter", self.fl_filter, bool(self.fl_filter)
            self.focus = 0
        elif k in ("PgUp", "PgDn", "Home", "End"):
            self.scroll_by(k)
        return None

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
        elif k == "ENTER":  # enter solo lanza
            return self.try_launch()
        elif k == " ":  # espacio marca, cambia o edita
            return self._press(kind, idx, k)
        elif k.isdigit() and 0 <= int(k) <= len(MODELS):
            self.set_model(int(k) - 1)       # 0 = Ninguno
            self.focus = self.model + 1
        elif k == "a":
            self.focus = self.na
            self._start_edit("args")
        elif k == "d":
            self.focus = self.na + 1
            self._start_edit("dir")
        elif k == "D":
            self._pick_dir()
        elif k in PARAM_KEYS:        # t / T / C cambian el perfil activo sin mover el foco; K / L son filas
            self.cycle(PARAM_KEYS[k])
            rows = [p[0] for p in profiles.ROW_PARAMS]
            if PARAM_KEYS[k] in rows:
                self.focus = self.nm + len(OPTIONS) + rows.index(PARAM_KEYS[k])
        elif k in OPT_KEYS:
            self.toggle(OPT_KEYS[k])
            self.focus = self.nm + [o[0] for o in OPTIONS].index(OPT_KEYS[k])
        elif k in ACTION_KEYS:
            return self.result(ACTION_KEYS[k])
        elif k == "Z":
            nombre, motor = voz_perfil(avanzar=True)
            self.focus = self.nm + [o[0] for o in OPTIONS].index("voz")
            self.msg, self.msg_style = ((f"voz: perfil «{nombre}» · {motor}", S_GREEN) if nombre else
                                        ("Sin perfiles de voz todavía: créalos en /voz.html", S_YELLOW))
            if motor == "s2":
                self.msg += " · lento: ~10 min por frase, sin el Qwen 35B"
        elif k == "w":                 # prende/apaga qwen-web
            url = f"http://{lan_ip()}:{WEB_PORT}/voz.html"
            on, aviso = web_toggle(WEB_PORT)
            if aviso:
                self.msg, self.msg_style = f"qwen-web: {aviso}", S_YELLOW
            elif on:
                self.msg, self.msg_style = f"voz: {url} · w apaga", S_GREEN
            else:
                self.msg, self.msg_style = "qwen-web apagado", S_YELLOW
        elif k == "p":
            self._cycle_profile()
        elif k == "P":
            self._pe_open()
        elif k == "x":
            self._stop()
        elif k == "r":
            self.refresh()
        elif k in ("PgUp", "PgDn", "Home", "End"):
            self.scroll_by(k)
        return None
