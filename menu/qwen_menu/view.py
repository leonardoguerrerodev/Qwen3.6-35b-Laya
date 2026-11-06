"""Vista: construcción de líneas, viewport con scroll y pintado."""
import os
import shlex
import textwrap

from .config import (CTX_AUTO, HOME, KEV_PORT, LAYA_PORT, LLAMA_PORT, MIN_COLS, MIN_ROWS, MODELS, NO_VISION,
                     OPTIONS, PARAMS, VOZ_PORT, WARN_EDIT, WIDTH_DEFAULT, APP_NAME, APP_TAGLINE)
from .style import (BG_FOCUS, S_ACCENT, S_BOLD, S_BORDER, S_DIM, S_FAINT, S_GREEN, S_PINK,
                    S_KEY, S_ORANGE, S_TEAL, S_TEXT, S_TITLE, S_YELLOW,
                    fit, render_segs, seg_len)
from . import flags, profiles
from .system import gb, short_path, voz_perfil


def _cut(s, n):
    """Recorta por el medio con … si no cabe en n columnas (rutas largas de .gguf)."""
    if len(s) <= n:
        return s
    k = max(1, n - 1)
    return s[:k // 2] + "…" + s[len(s) - (k - k // 2):]


def _status(name, port, up):
    return [("●" if up else "○", S_GREEN if up else S_DIM),
            (f" {name} ", S_TEXT),
            ("activo" if up else "apagado", S_GREEN if up else S_FAINT),
            (f" :{port}", S_DIM)]


def _short_tail(p, n):
    """Ruta con ~ y, si no cabe en n columnas, solo el final: …/carpeta/subcarpeta."""
    p = short_path(p)
    if len(p) <= n:
        return p
    partes = [x for x in p.split(os.sep) if x]
    fin = partes[-1] if partes else p
    for parte in reversed(partes[:-1]):
        cand = parte + os.sep + fin
        if len(cand) + 2 > n:
            break
        fin = cand
    return ("…" + os.sep + fin)[-n:]


class ViewMixin:
    """Dibujo del menú. Espera que la clase hija defina el estado
    (opts, model, focus, args, cdir, editing, buf, msg, paths, *_up, nm, n_rows)."""

    # ── viewport ──
    def _init_view(self):
        self._t_size = self.t.size()
        self.width = WIDTH_DEFAULT
        self.scroll = 0
        self._follow = True          # el viewport sigue al foco (False tras PgUp/PgDn)
        self._all_lines = []
        self._focus_lines = []
        self._total_lines = 0
        self._visible_rows = 5
        self._max_scroll = 0
        self._indicators = False

    def _recalc(self):
        """Reconstruye líneas, ancho y viewport según el estado y el tamaño actuales."""
        cols, rows = self._t_size
        self.width = max(MIN_COLS - 2, min(WIDTH_DEFAULT, cols - 2))
        self._all_lines = self._build_all()
        self._total_lines = len(self._all_lines)
        if self._total_lines <= rows - 1:
            self._visible_rows, self._indicators = self._total_lines, False
        else:   # reserva 1 fila arriba y 1 abajo para los indicadores ▲ ▼
            self._visible_rows, self._indicators = max(3, rows - 2), True
        self._max_scroll = max(0, self._total_lines - self._visible_rows)
        self.scroll = max(0, min(self.scroll, self._max_scroll))

    def _adjust_scroll(self):
        """Ajusta el scroll para que la fila con foco quede visible."""
        if not self._focus_lines or self.focus >= len(self._focus_lines):
            return
        fl = self._focus_lines[self.focus]
        if self.focus == 0:
            self.scroll = 0
        elif self.focus == len(self._focus_lines) - 1:
            self.scroll = self._max_scroll
        elif fl < self.scroll:
            self.scroll = fl
        elif fl >= self.scroll + self._visible_rows:
            self.scroll = fl - self._visible_rows + 1
        self.scroll = max(0, min(self.scroll, self._max_scroll))

    def scroll_by(self, key):
        """PgUp / PgDn / Home / End: mueve el viewport sin seguir al foco."""
        self._follow = False
        page = max(1, self._visible_rows - 3)
        if key == "PgUp":
            self.scroll = max(0, self.scroll - page)
        elif key == "PgDn":
            self.scroll = min(self._max_scroll, self.scroll + page)
        elif key == "Home":
            self.scroll = 0
        elif key == "End":
            self.scroll = self._max_scroll

    # ── helpers de construcción ──
    @property
    def _W(self):
        return self.width - 2

    @property
    def _to_claude(self):
        return self.opts["claude"] and self.model < 0 and not self.opts["ollama"]

    def _bg(self, row):
        return BG_FOCUS if self.focus == row else ""

    def _add(self, line, focus=False):
        if focus:
            self._fl.append(len(self._ln))
        self._ln.append(line)

    def _rule(self, left, right):
        return render_segs([(left + "─" * self._W + right, S_BORDER)])

    def _box(self, segs, bg=""):
        return (render_segs([("│ ", S_BORDER)])
                + render_segs(fit(segs, self._W - 2), bg)
                + render_segs([(" │", S_BORDER)]))

    def _section(self, title):
        head = f"─ {title} "
        return render_segs([("├" + head + "─" * (self._W - len(head)) + "┤", S_BORDER)])

    def _lr(self, left, right, trim=True):
        """Une izquierda y derecha con hueco; si trim, recorta la izquierda para que quepa."""
        gap = self._W - 2 - seg_len(left) - seg_len(right)
        if trim and gap < 1:
            left = fit(left, self._W - 2 - seg_len(right) - 1)[:-1] + [("", "")]
            gap = 1
        return left + [(" " * max(1, gap), "")] + right

    # ── secciones ──
    def _build_all(self):
        self._ln, self._fl = [], []   # líneas y línea de cada fila enfocable
        self._sec_header()
        if self.fl:   # todos los flags: se abre desde el editor de perfil con ?
            self._sec_flags()
            self._focus_lines = self._fl
            return self._ln
        if self.pe:   # editor de perfil: reemplaza al menú principal
            self._sec_pe()
            self._focus_lines = self._fl
            return self._ln
        self._sec_models()
        self._sec_options()
        self._sec_params()
        self._sec_args()
        self._sec_dir()
        self._sec_launch()
        self._sec_help()
        self._focus_lines = self._fl
        return self._ln

    def _sec_header(self):
        self._add(self._rule("╭", "╮"))
        self._add(self._box([("◆ ", S_ACCENT), (APP_NAME, S_TITLE),
                             ("  " + APP_TAGLINE, S_DIM)]))
        self._add(self._box(_status("llama", LLAMA_PORT, self.llama_up) + [("  ", "")]
                            + _status("laya", LAYA_PORT, self.laya_up)))
        self._add(self._box(_status("kev", KEV_PORT, self.kev_up) + [("  ", "")]
                            + _status("voz", VOZ_PORT, self.voz_up)))

    def _sec_models(self):
        self._add(self._section("Modelo"))
        lw = min(12, max(8, *(len(m[1]) for m in MODELS)))
        ollama = self.opts["ollama"]
        sel0 = self.model < 0
        self._add(self._box(
            [("◉" if sel0 else "○", S_GREEN if sel0 and not ollama else S_DIM),
             (" 0 ", S_DIM),
             (f"{'Ninguno':<{lw}}", S_FAINT if ollama else (S_BOLD if sel0 else S_TEXT)),
             (" sin modelo local · solo Kev, Laya o Claude", S_FAINT if ollama else S_DIM)],
            self._bg(0)), focus=True)
        for i, (mid, label, desc, _p) in enumerate(MODELS):
            path = self.paths.get(mid, "")
            sel = i == self.model
            fg_lbl = S_FAINT if ollama else (S_BOLD if sel else S_TEXT)
            fg_desc = S_FAINT if ollama else S_DIM
            right = ([("no encontrado", S_PINK)] if not path
                     else [(gb(path), S_TEAL if not ollama else S_FAINT)])
            left = [("◉" if sel else "○", S_GREEN if sel and not ollama else S_DIM),
                    (f" {i + 1} ", S_DIM), (f"{label[:lw]:<{lw}}", fg_lbl),
                    (f" {desc}", fg_desc)]
            self._add(self._box(self._lr(left, right, trim=False), self._bg(i + 1)),
                      focus=True)

    def _sec_options(self):
        ollama = self.opts["ollama"]
        self._add(self._section("Opciones"))
        for j, (key, hot, label, desc) in enumerate(OPTIONS):
            on = self.opts[key]
            na = (self.model < 0 and not ollama and key in ("edit", "vision", "incognito")
                  or key == "vision" and not ollama and self.model >= 0
                  and MODELS[self.model][0] in NO_VISION)
            if key == "voz":   # perfil y motor activos (se cambian con Z)
                nombre, motor = voz_perfil()
                if nombre:
                    desc = f"«{nombre}» · {motor} · Z cambia de perfil"
            segs = [("[", S_DIM), ("✓" if on else " ", S_YELLOW), ("] ", S_DIM),
                    (f"{hot} ", S_DIM),
                    (f"{label:<9}", S_FAINT if na else (S_BOLD if on else S_TEXT)),
                    (f" {desc}", S_DIM)]
            self._add(self._box(segs, self._bg(self.nm + j)), focus=True)
        if self.opts["edit"] and (self.model >= 0 or ollama):
            self._add(self._box([("  " + WARN_EDIT, S_ORANGE)]))

    def _sec_profile(self):
        """Resumen del perfil activo (solo lectura; p cambia de perfil, P abre el editor)."""
        if self.model < 0 or self.opts["ollama"] or not self.pname:
            return
        names = list(self.pdoc.get(MODELS[self.model][0], {}).get("perfiles", {}))
        pos = f"{names.index(self.pname) + 1}/{len(names)}" if self.pname in names else "1/1"
        p = {**self.prof, **{k: self.params[k] for k in profiles.SHARED}}
        ctx = p["ctx"]
        if ctx == "auto":
            n = CTX_AUTO.get(MODELS[self.model][0])
            ctx = f"auto·{int(n) // 1024}k" if n else "auto·120k"
        left = [("◆ ", S_ACCENT), (self.pname, S_BOLD), (f" {pos}", S_DIM)]
        self._add(self._box(self._lr(left, [("p cambia · P edita", S_DIM)])))
        self._add(self._box([("  ", ""), (f"temp {p['temp']} · top-p {p['top_p']} · top-k {p['top_k']}"
                                         f" · ctx {ctx} · kv {p['kvq']}", S_TEXT)]))

    def _sec_pe(self):
        """Editor del perfil activo: una fila por parámetro."""
        mid, label = MODELS[self.model][0], MODELS[self.model][1]
        names = list(self.pdoc[mid]["perfiles"])
        self._add(self._section(f"Perfil «{self.pname}» · {label} · {names.index(self.pname) + 1}/{len(names)}"))
        for j, (key, lbl, desc, vals) in enumerate(profiles.FIELDS):
            v = self._pget(key) or "—"
            desc, vals = self._field(key, desc, vals)
            segs = [(" ⇄  " if vals else " ✎  ", S_DIM), (f"{lbl:<11}", S_TEXT),
                    (f" {v:<10}", S_YELLOW), (f" {desc}", S_DIM)]
            self._add(self._box(segs, self._bg(j)), focus=True)
        if self.editing and self.edit_target.startswith("p"):
            self._add(self._section("Nombre" if self.edit_target in ("pnew", "pren") else "Valor"))
            left = [("› ", S_KEY), (self.buf, "7;" + S_TEXT if self.sel else S_TEXT),
                    ("" if self.sel else "▏", S_KEY)]
            self._add(self._box(self._lr(left, [("enter ok · esc cancela", S_FAINT)])))
        self._sec_cmd()
        self._add(self._rule("╰", "╯"))
        self._add("")
        for pairs in (
            [("↑↓", "mover"), ("espacio", "valores"), ("enter", "escribir"), ("esc", "volver")],
            [("p", "otro perfil"), ("n", "nuevo (copia)"), ("R", "renombrar"), ("X", "borrar")],
            [("c", "copiar comando"), ("L", "lanzar a mano"), ("?", "todos los flags")],
        ):
            for ln in self._hint(pairs):
                self._add(ln)
        if self.msg:
            self._add("")
            self._add(self._centered([(self.msg[:self.width], self.msg_style)]))

    def _sec_cmd(self):
        """Comando completo de llama-server con el perfil actual: lo arma lib/llama.sh, igual que al lanzar."""
        words, aviso = self.command()
        self._add(self._section("Comando de llama-server"))
        if not words:
            self._add(self._box([("✘ " + (aviso or "no se pudo armar"), S_PINK)]))
            return
        w = self._W - 2
        line, n = [], 0
        for i, g in enumerate(flags.groups(words)):
            vals = [shlex.quote(x).replace(HOME, "~", 1) if x.startswith(HOME) else shlex.quote(x) for x in g[1:]]
            head = short_path(g[0]) if i == 0 else g[0]
            segs = [(_cut(head, w - 2), S_TEXT if i == 0 else S_KEY)]
            room = max(8, w - 4 - len(head))
            segs += [(" " + _cut(v, room), S_TEXT) for v in vals]
            ln = seg_len(segs)
            if line and n + 1 + ln > w:
                self._add(self._box(line))
                line, n = [], 0
            if line:
                line.append((" ", ""))
                n += 1
            elif i:
                line, n = [("  ", "")], 2
            line += segs
            n += ln
        if line:
            self._add(self._box(line))
        if aviso:
            self._add(self._box([("! " + aviso, S_ORANGE)]))

    def _sec_flags(self):
        """Pantalla «todos los flags»: el --help del binario, con explicación en español donde la hay."""
        items = self.fl_items()
        total = len(flags.catalog())
        used = set(self.command()[0])
        self._add(self._section(f"Flags de llama-server · {len(items)} de {total}"))
        if self.editing and self.edit_target == "ffilter":
            left = [("/ ", S_KEY), (self.buf, S_TEXT), ("▏", S_KEY)]
            right = [("enter ok · esc", S_FAINT)]
        else:
            left = [("/ ", S_KEY), (self.fl_filter or "filtrar", S_TEXT if self.fl_filter else S_FAINT)]
            right = [("↑↓ · esc vuelve · ✓ = en tu comando", S_DIM)]
        self._add(self._box(self._lr(left, right)))
        if not items:
            self._add(self._box([("sin coincidencias" if total else f"no pude leer {flags.LLAMA_BIN} --help",
                                  S_PINK)]))
        width = self._W - 2 - 4
        sec = None
        for j, (s, alias, names, desc) in enumerate(items):
            if s != sec:
                sec = s
                self._add(self._section(s))
            on, foc = any(a in used for a in alias), j == self.focus
            self._add(self._box([("✓ " if on else "  ", S_GREEN),
                                 (names, S_YELLOW if on else S_BOLD if foc else S_TEXT)], self._bg(j)), focus=True)
            txt = flags.es(alias)
            body = [(t, S_TEXT) for t in textwrap.wrap(txt, width)]
            if foc or not txt:   # el inglés completo solo en la fila con foco; si no hay español, su 1.ª línea
                en = textwrap.wrap(desc, width) or [""]
                body += [(t, S_DIM) for t in (en if foc else en[:1])]
            for t, st in body:
                self._add(self._box([("    " + t, st)]))
        self._add(self._rule("╰", "╯"))
        if self.msg:
            self._add("")
            self._add(self._centered([(self.msg[:self.width], self.msg_style)]))

    def _sec_params(self):
        """Sección Perfil: resumen del perfil activo + los parámetros que no son del perfil (Kev, Idioma)."""
        self._add(self._section("Perfil y ajustes"))
        self._sec_profile()
        for j, (key, hot, label, _vals, _d, desc) in enumerate(profiles.ROW_PARAMS):
            off = (key == "kev" and not self.opts["kev"]) or (key == "harness" and (self.model < 0 or self.opts["ollama"]))   # sin Kev activo, el tamaño no se usa
            segs = [(" ⇄  ", S_DIM), (f"{hot} ", S_DIM), (f"{label:<9}", S_FAINT if off else S_TEXT),
                    (f" {self.params[key]:<9}", S_FAINT if off else S_YELLOW),
                    (f" {desc}", S_FAINT if off else S_DIM)]
            self._add(self._box(segs, self._bg(self.nm + len(OPTIONS) + j)), focus=True)

    def _sec_args(self):
        solo_server = (self.params["harness"] == "servidor" and self.model >= 0
                       and not self.opts["ollama"] and not self._to_claude)
        self._add(self._section("Argumentos para claude" if self._to_claude
                                else "Argumentos (no se usan en modo servidor)" if solo_server
                                else "Argumentos para " + ("pi" if self.opts["ollama"] else self.params["harness"])))
        if self.editing and self.edit_target == "args":
            left = [("› ", S_KEY), (self.buf, S_TEXT), ("▏", S_KEY)]
            right = [("enter ok · esc cancela", S_FAINT)]
        elif self.args:
            left = [("› ", S_DIM), (self.args, S_TEXT)]
            right = [("espacio edita", S_DIM)]
        else:
            left = [("› ", S_DIM), ('opcional · ej: -p "resume este repo"', S_FAINT)]
            right = [("espacio edita", S_DIM)]
        bg = "" if self.editing else self._bg(self.na)
        self._add(self._box(self._lr(left, right), bg), focus=True)

    def _sec_dir(self):
        self._add(self._section("Carpeta de trabajo"))
        if self.editing and self.edit_target == "dir":
            left = [("› ", S_KEY), (self.buf, S_TEXT), ("▏", S_KEY)]
            right = [("tab completa · enter ok · esc", S_FAINT)]
        else:
            left = [("› ", S_DIM),
                    (_short_tail(self.cdir, self._W - 2 - 31),
                     S_TEXT if self.opts["claude"] or self.model >= 0 or self.opts["ollama"]
                     else S_FAINT)]
            right = [("espacio edita · D selector", S_DIM)]
        bg = "" if self.editing else self._bg(self.na + 1)
        self._add(self._box(self._lr(left, right), bg), focus=True)

    def _sec_launch(self):
        ollama = self.opts["ollama"]
        self._add(self._rule("├", "┤"))
        parts = ([MODELS[self.model][1].lower(), self.params["harness"]] if self.model >= 0 else ["sin modelo"])
        if ollama:
            parts = ["ollama"]
        parts += [(f"claude@{os.path.basename(self.cdir.rstrip(os.sep)) or os.sep}"
                   if k == "claude" else lbl.lower())
                  for k, _h, lbl, _d in OPTIONS
                  if self.opts[k] and k != "ollama"
                  and not (self.model < 0 and not ollama
                           and k in ("edit", "vision", "incognito"))]
        left = [("▶ ", S_GREEN), ("Lanzar", "1;38;5;151"), ("  enter", S_FAINT)]
        right = [(" · ".join(parts), S_DIM)]
        self._add(self._box(self._lr(left, right, trim=False), self._bg(self.n_rows - 1)),
                  focus=True)
        self._add(self._rule("╰", "╯"))

    def _centered(self, segs):
        """Centra una línea de segmentos respecto al ancho de la caja."""
        if seg_len(segs) > self.width:
            segs = fit(segs, self.width)
        return " " * max(0, (self.width - seg_len(segs)) // 2) + render_segs(segs)

    def _hint(self, pairs):
        """Reparte los atajos en varias líneas si no caben en el ancho."""
        out, cur = [], []
        for k, d in pairs:
            item = [(k, S_KEY), (f" {d}", S_FAINT)]
            trial = cur + ([(" · ", S_FAINT)] if cur else []) + item
            if cur and seg_len(trial) > self.width:
                out.append(self._centered(cur))
                cur = item
            else:
                cur = trial
        if cur:
            out.append(self._centered(cur))
        return out

    def _sec_help(self):
        self._add("")
        for pairs in (
            [("↑↓", "mover"), ("espacio", "marcar/cambiar"), ("enter", "lanzar"), ("q", "salir")],
            [(f"0-{len(MODELS)}", "modelo"), ("a", "argumentos"), ("m", "memoria"),
             ("c", "estado"), ("l", "laya"), ("w", "voz web"), ("Z", "perfil de voz"),
             ("x", "apagar servidores")],
            [("d", "carpeta"), ("D", "selector gráfico"), ("t/T/C", "contexto/temp./KV"), ("H", "agente"),
             ("p", "cambiar perfil"), ("P", "editar perfil")],
            [("PgUp/PgDn", "desplazar"), ("Home/End", "inicio/fin")],
        ):
            for ln in self._hint(pairs):
                self._add(ln)
        if self.msg:
            self._add("")
            self._add(self._centered([(self.msg[:self.width], self.msg_style)]))

    # ── pintado ──
    def draw(self):
        cols, rows = self.t.size()
        self._t_size = (cols, rows)
        if cols < MIN_COLS or rows < MIN_ROWS:
            self.t.write("\x1b[H\x1b[J" + f"Terminal muy pequeña ({cols}x{rows})"[:max(1, cols)]
                         + "\r\n" + f"mínimo {MIN_COLS}x{MIN_ROWS} · q para salir"[:max(1, cols)])
            return
        self._recalc()
        if self._follow:
            self._adjust_scroll()
        pad = " " * max(0, (cols - self.width) // 2)
        body = [pad + ln + "\x1b[0m" for ln in
                self._all_lines[self.scroll:self.scroll + self._visible_rows]]
        if self._indicators:
            up = pad + "\x1b[38;5;245m ▲ más arriba\x1b[0m" if self.scroll > 0 else ""
            dn = (pad + "\x1b[38;5;245m ▼ más abajo\x1b[0m"
                  if self.scroll < self._max_scroll else "")
            body = [up] + body + [dn]
        # \x1b[K limpia el resto de cada fila; sin salto final para no provocar scroll
        self.t.write("\x1b[H\x1b[J" + "\x1b[K\r\n".join(body))
