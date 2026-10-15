"""Estilos ANSI y utilidades de segmentos (texto, estilo)."""

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
