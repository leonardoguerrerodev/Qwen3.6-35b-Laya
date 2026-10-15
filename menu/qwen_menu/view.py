"""Vista: construcción de líneas, viewport con scroll y pintado."""
import os

from .config import (KEV_PORT, LAYA_PORT, LLAMA_PORT, MIN_COLS, MIN_ROWS, MODELS,
                     OPTIONS, WARN_EDIT, WIDTH_DEFAULT)
from .style import (BG_FOCUS, S_ACCENT, S_BOLD, S_BORDER, S_DIM, S_FAINT, S_GREEN, S_PINK,
                    S_KEY, S_ORANGE, S_TEAL, S_TEXT, S_TITLE, S_YELLOW,
                    fit, render_segs, seg_len)
from .system import gb, short_path


def _status(name, port, up):
    return [("●" if up else "○", S_GREEN if up else S_DIM),
            (f" {name} ", S_TEXT),
            ("online" if up else "offline", S_GREEN if up else S_FAINT),
            (f" :{port}", S_DIM)]


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
        self._sec_models()
        self._sec_options()
        self._sec_args()
        self._sec_dir()
        self._sec_launch()
        self._sec_help()
        self._focus_lines = self._fl
        return self._ln

    def _sec_header(self):
        self._add(self._rule("╭", "╮"))
        self._add(self._box([("◆ ", S_ACCENT), ("QWEN3.6-35B", S_TITLE),
                             ("  pi · llama.cpp · laya · kev · claude", S_DIM)]))
        self._add(self._box(_status("llama", LLAMA_PORT, self.llama_up) + [("  ", "")]
                            + _status("laya", LAYA_PORT, self.laya_up) + [("  ", "")]
                            + _status("kev", KEV_PORT, self.kev_up)))

    def _sec_models(self):
        self._add(self._section("Modelo"))
        ollama = self.opts["ollama"]
        sel0 = self.model < 0
        self._add(self._box(
            [("◉" if sel0 else "○", S_GREEN if sel0 and not ollama else S_DIM),
             (" 0 ", S_DIM),
             (f"{'Ninguno':<8}", S_FAINT if ollama else (S_BOLD if sel0 else S_TEXT)),
             (" sin modelo grande · solo kev/laya/claude", S_FAINT if ollama else S_DIM)],
            self._bg(0)), focus=True)
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
            self._add(self._box(self._lr(left, right, trim=False), self._bg(i + 1)),
                      focus=True)

    def _sec_options(self):
        ollama = self.opts["ollama"]
        self._add(self._section("Opciones"))
        for j, (key, hot, label, desc) in enumerate(OPTIONS):
            on = self.opts[key]
            na = self.model < 0 and not ollama and key in ("edit", "vision", "incognito")
            segs = [("[", S_DIM), ("✓" if on else " ", S_YELLOW), ("] ", S_DIM),
                    (f"{hot} ", S_DIM),
                    (f"{label:<9}", S_FAINT if na else (S_BOLD if on else S_TEXT)),
                    (f" {desc}", S_DIM)]
            self._add(self._box(segs, self._bg(self.nm + j)), focus=True)
        if self.opts["edit"] and (self.model >= 0 or ollama):
            self._add(self._box([("  " + WARN_EDIT, S_ORANGE)]))

    def _sec_args(self):
        self._add(self._section("Argumentos para claude" if self._to_claude
                                else "Argumentos para pi"))
        if self.editing and self.edit_target == "args":
            left = [("› ", S_KEY), (self.buf, S_TEXT), ("▏", S_KEY)]
            right = [("enter ok · esc cancela", S_FAINT)]
        elif self.args:
            left = [("› ", S_DIM), (self.args, S_TEXT)]
            right = [("a", S_DIM)]
        else:
            left = [("› ", S_DIM), ('opcional · ej: -p "resume este repo"', S_FAINT)]
            right = [("a", S_DIM)]
        bg = "" if self.editing else self._bg(self.nm + len(OPTIONS))
        self._add(self._box(self._lr(left, right), bg), focus=True)

    def _sec_dir(self):
        self._add(self._section("Carpeta para claude"))
        if self.editing and self.edit_target == "dir":
            left = [("› ", S_KEY), (self.buf, S_TEXT), ("▏", S_KEY)]
            right = [("tab completa · enter ok · esc", S_FAINT)]
        else:
            left = [("› ", S_DIM),
                    (short_path(self.cdir, self._W - 2 - 6),
                     S_TEXT if self._to_claude else S_FAINT)]
            right = [("d · D selector", S_DIM)]
        bg = "" if self.editing else self._bg(self.nm + len(OPTIONS) + 1)
        self._add(self._box(self._lr(left, right), bg), focus=True)

    def _sec_launch(self):
        ollama = self.opts["ollama"]
        self._add(self._rule("├", "┤"))
        parts = [MODELS[self.model][1].lower()] if self.model >= 0 else ["sin modelo"]
        if ollama:
            parts = ["ollama"]
        parts += [(f"claude@{os.path.basename(self.cdir.rstrip(os.sep)) or os.sep}"
                   if k == "claude" else lbl.lower())
                  for k, _h, lbl, _d in OPTIONS
                  if self.opts[k] and k != "ollama"
                  and not (self.model < 0 and not ollama
                           and k in ("edit", "vision", "incognito"))]
        left = [("▶ ", S_GREEN), ("Lanzar", "1;38;5;151")]
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
            [("↑↓", "mover"), ("espacio", "marcar"), ("enter", "lanzar"), ("q", "salir")],
            [(f"0-{len(MODELS)}", "modelo"), ("a", "argumentos"), ("m", "memoria"),
             ("c", "estado"), ("l", "laya"), ("x", "apagar")],
            [("d", "carpeta de claude"), ("D", "selector gráfico")],
            [("PgUp/PgDn", "scroll"), ("Home/End", "inicio/fin")],
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
            self.t.write("\x1b[H\x1b[J" + f"Terminal chica {cols}x{rows}"[:max(1, cols)]
                         + "\r\n" + f"min {MIN_COLS}x{MIN_ROWS} · q sale"[:max(1, cols)])
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
