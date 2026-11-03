#!/usr/bin/env bash
# Perfiles de lanzamiento por modelo para el menú de qwen.
# Uso: bash aplicar-perfiles.sh [RAIZ_DE_LA_REPO]   (por defecto: carpeta actual)
set -euo pipefail

ROOT="$(cd "${1:-$PWD}" && pwd)"
cd "$ROOT"

PATCHED=(menu/qwen_menu/menu.py menu/qwen_menu/view.py qwen-local.sh lib/llama.sh lib/pi.sh)
ALL=("${PATCHED[@]}" menu/qwen_menu/profiles.py)

for f in "${PATCHED[@]}" menu/qwen_menu/config.py; do
  [ -f "$f" ] || { echo "falta $f: ejecuta desde la raíz de la repo o pasa su ruta" >&2; exit 1; }
done

BK="$ROOT/.bak-perfiles-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BK"
for f in "${ALL[@]}"; do
  [ -f "$f" ] && { mkdir -p "$BK/$(dirname "$f")"; cp -a "$f" "$BK/$f"; }
done

restore() {
  local f
  for f in "${ALL[@]}"; do
    if [ -f "$BK/$f" ]; then cp -a "$BK/$f" "$f"; else rm -f "$f"; fi
  done
  echo "Restaurado desde $BK" >&2
}

# ───────────────────────── menu/qwen_menu/profiles.py ─────────────────────────
cat > menu/qwen_menu/profiles.py <<'PROFILES_EOF'
"""Perfiles de lanzamiento por modelo: muestreo y parámetros de llama-server, guardados en JSON.

$QWEN_DATA/profiles.json  →  {"<id de modelo>": {"activo": "nombre", "perfiles": {"nombre": {campo: valor}}}}
Todos los valores son texto. Vacío = «el valor por defecto del lanzador» (no se pasa el flag).
ctx, temp y kvq son además los «Parámetros» t / T / C del menú: el perfil los refleja.
"""
import json
import os
import re

from .config import PARAMS, QWEN_DATA

PROFILES_FILE = os.path.join(QWEN_DATA, "profiles.json")

_PV = {p[0]: p[3] for p in PARAMS}   # valores de ciclo de ctx/temp/kvq: los mismos que t/T/C

# clave, etiqueta, descripción, valores de ciclo (espacio)
FIELDS = [
    ("temp", "Temp.", "0-2 · 0.6 código · 1.0 general", _PV["temp"]),
    ("top_p", "Top-p", "0-1 · recomendado 0.95", ("0.8", "0.9", "0.95", "1.0")),
    ("top_k", "Top-k", "0 = sin límite · recomendado 20", ("0", "20", "40", "64")),
    ("min_p", "Min-p", "0-1 · recomendado 0.0", ("0.0", "0.02", "0.05")),
    ("ctx", "Contexto", "tokens (acepta 32k) · auto = el del lanzador", _PV["ctx"]),
    ("kvq", "KV cache", "cuantización del KV · q8_0/q4_0 ahorran memoria", _PV["kvq"]),
    ("ncmoe", "MoE en CPU", "--n-cpu-moe · expertos en RAM · vacío = el del lanzador", ("", "20", "28", "36", "40")),
    ("ngl", "Capas GPU", "-ngl · vacío = según el modelo", ("", "auto", "20", "30", "45", "99")),
    ("loadmode", "Carga", "--load-mode · vacío = el del lanzador", ("", "none", "mmap", "mlock")),
    ("batch", "Batch", "-b · vacío = el del lanzador", ("", "512", "1024", "2048", "4096")),
    ("ub", "Ubatch", "-ub · vacío = el del lanzador", ("", "256", "512", "1024")),
    ("extra", "Flags extra", "flags crudos de llama-server, sin comillas", ()),
]
KEYS = tuple(f[0] for f in FIELDS)
SHARED = ("ctx", "temp", "kvq")                     # también viven en los Parámetros del menú
EXTRA_KEYS = tuple(k for k in KEYS if k not in SHARED)

DEFAULTS = {"temp": "0.6", "top_p": "0.95", "top_k": "20", "min_p": "0.0", "ctx": "auto", "kvq": "auto",
            "ncmoe": "", "ngl": "", "loadmode": "", "batch": "", "ub": "", "extra": ""}


def _float(t, lo, hi):
    try:
        v = float(t)
    except ValueError:
        return None
    return str(v) if lo <= v <= hi else None


def _int(t, lo, hi):
    return str(int(t)) if re.fullmatch(r"\d+", t) and lo <= int(t) <= hi else None


def validate(key, text):
    """(ok, valor_normalizado, mensaje). Vacío → por defecto del campo."""
    t = (text or "").strip()
    if key == "extra":
        if re.search(r"""['"`$;&|<>\\]""", t):
            return False, t, "sin comillas ni caracteres de shell (solo flags separados por espacios)"
        return True, " ".join(t.split()), ""
    if t == "":
        return True, DEFAULTS[key], ""
    if key == "ctx":
        if t.lower() == "auto":
            return True, "auto", ""
        m = re.fullmatch(r"(\d+)([kK]?)", t)
        if m:
            n = int(m.group(1)) * (1024 if m.group(2) else 1)
            if 256 <= n <= 2_000_000:
                return True, str(n), ""
        return False, t, "contexto: auto, un entero (≥256) o con k (32k)"
    choices = {"kvq": ("auto", "f16", "q8_0", "q4_0"), "loadmode": ("none", "mmap", "mlock")}
    if key in choices:
        return ((True, t, "") if t in choices[key] else (False, t, "valores: " + ", ".join(choices[key])))
    if key == "ngl":
        v = "auto" if t == "auto" else _int(t, 0, 999)
        return (True, v, "") if v else (False, t, "-ngl: auto o un entero 0-999")
    rules = {"temp": (_float, 0, 2, "0 a 2"), "top_p": (_float, 0, 1, "0 a 1"), "min_p": (_float, 0, 1, "0 a 1"),
             "top_k": (_int, 0, 1000, "entero 0 a 1000"), "ncmoe": (_int, 0, 999, "entero 0 a 999"),
             "batch": (_int, 1, 65536, "entero 1 a 65536"), "ub": (_int, 1, 65536, "entero 1 a 65536")}
    fn, lo, hi, hint = rules[key]
    v = fn(t, lo, hi)
    return (True, v, "") if v is not None else (False, t, f"{key}: {hint}")


def sanitize(p):
    """Perfil completo y válido: lo que falte o esté roto vuelve al valor por defecto."""
    p = p if isinstance(p, dict) else {}
    out = {}
    for k in KEYS:
        ok, v, _ = validate(k, str(p.get(k, DEFAULTS[k])))
        out[k] = v if ok else DEFAULTS[k]
    return out


def load_all():
    try:
        with open(PROFILES_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_all(doc):
    try:
        os.makedirs(os.path.dirname(PROFILES_FILE), exist_ok=True)
        tmp = PROFILES_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, PROFILES_FILE)
        return True
    except OSError:
        return False


def entry(doc, mid, seed=None):
    """Entrada del modelo `mid` (la crea, o repara, con un perfil «default» a partir de `seed`)."""
    ent = doc.get(mid)
    perfiles = ent.get("perfiles") if isinstance(ent, dict) else None
    if not isinstance(perfiles, dict) or not perfiles:
        ent = doc[mid] = {"activo": "default", "perfiles": {"default": sanitize(seed or DEFAULTS)}}
    else:
        ent["perfiles"] = {str(n): sanitize(p) for n, p in perfiles.items()}
        if ent.get("activo") not in ent["perfiles"]:
            ent["activo"] = next(iter(ent["perfiles"]))
    return ent


def check_name(ent, name, current=None):
    """(ok, nombre, mensaje): sin vacíos, ≤24 caracteres, sin repetir (salvo el mismo al renombrar)."""
    n = " ".join((name or "").split())
    if not n:
        return False, n, "el nombre no puede estar vacío"
    if len(n) > 24 or not n.isprintable():
        return False, n, "máximo 24 caracteres"
    if n in ent["perfiles"] and n != current:
        return False, n, "ya existe un perfil con ese nombre"
    return True, n, ""


def unique_name(ent, base):
    n, i = f"{base}-2", 2
    while n in ent["perfiles"]:
        i += 1
        n = f"{base}-{i}"
    return n


def rename(ent, old, new):
    ent["perfiles"] = {(new if n == old else n): p for n, p in ent["perfiles"].items()}
    if ent["activo"] == old:
        ent["activo"] = new
PROFILES_EOF

# ───────────────────────── parche (todo o nada) ─────────────────────────
PATCH="$(mktemp --suffix=.py)"
trap 'rm -f "$PATCH"' EXIT
cat > "$PATCH" <<'PATCH_EOF'
import os
import sys

root = sys.argv[1]
results = {}   # ruta relativa -> texto nuevo; se escribe todo o nada


def plan(rel, marker, edits):
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        text = f.read()
    if marker in text:
        print(f"  {rel}: ya estaba parchado")
        return
    for old, new in edits:
        n = text.count(old)
        if n != 1:
            sys.exit(f"ERROR en {rel}: el ancla aparece {n} veces (debe ser 1). No se tocó ningún archivo.\n--- ancla ---\n{old}")
        text = text.replace(old, new)
    results[rel] = text


# ─────────────── menu.py ───────────────
MENU_METHODS = r'''    # ── perfiles por modelo (qwen_menu/profiles.py) ──
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
        elif k == "p":
            self._cycle_profile()
        elif k == "n":
            self.editing, self.edit_target = True, "pnew"
            self.buf = profiles.unique_name(ent, self.pname)
        elif k == "R":
            self.editing, self.edit_target, self.buf = True, "pren", self.pname
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

    def _nav_key(self, k):
'''

plan("menu/qwen_menu/menu.py", "profiles.load_all()", [
    (r'''from .view import ViewMixin
''',
     r'''from . import profiles
from .view import ViewMixin
'''),
    (r'''        self.normalize()
        self.focus = 0
''',
     r'''        self.normalize()
        # Perfiles por modelo (qwen_menu/profiles.py): ctx/temp/KV viven en self.params; el resto en self.prof
        self.pdoc = profiles.load_all()
        self.prof = {}
        self.pname = ""
        self.pe = False             # editor de perfil abierto
        self._pdel = False          # «X» pulsada una vez (confirma el borrado)
        self._pe_main_focus = 0
        self._load_profile()
        self.focus = 0
'''),
    (r'''        vals = next(p[3] for p in PARAMS if p[0] == key)
        self.params[key] = vals[(vals.index(self.params[key]) + 1) % len(vals)]
''',
     r'''        vals = next(p[3] for p in PARAMS if p[0] == key)
        cur = self.params[key]   # un valor de perfil fuera de la lista vuelve al primero
        self.params[key] = vals[(vals.index(cur) + 1) % len(vals)] if cur in vals else vals[0]
'''),
    (r'''        self.model = -1 if (toggle and i >= 0 and i == self.model) else i
        self.normalize()
''',
     r'''        self._store_profile()
        self.model = -1 if (toggle and i >= 0 and i == self.model) else i
        self.normalize()
        self._load_profile()
'''),
    (r'''    def result(self, action):
        nomodel = self.model < 0 and not self.opts["ollama"]
''',
     r'''    def result(self, action):
        self._store_profile()
        nomodel = self.model < 0 and not self.opts["ollama"]
'''),
    (r'''            f"P_KEV={q(self.params['kev'])}",
        ]
''',
     r'''            f"P_KEV={q(self.params['kev'])}",
            f"P_TOPP={q(self.prof.get('top_p', ''))}",
            f"P_TOPK={q(self.prof.get('top_k', ''))}",
            f"P_MINP={q(self.prof.get('min_p', ''))}",
            f"P_NCMOE={q(self.prof.get('ncmoe', ''))}",
            f"P_NGL={q(self.prof.get('ngl', ''))}",
            f"P_LOADMODE={q(self.prof.get('loadmode', ''))}",
            f"P_BATCH={q(self.prof.get('batch', ''))}",
            f"P_UB={q(self.prof.get('ub', ''))}",
            f"P_EXTRA={q(self.prof.get('extra', ''))}",
        ]
'''),
    (r'''            res = self._edit_key(k) if self.editing else self._nav_key(k)
''',
     r'''            res = self._edit_key(k) if self.editing else self._pe_key(k) if self.pe else self._nav_key(k)
'''),
    (r'''        if k == "ENTER":
            if self.edit_target == "dir":
''',
     r'''        if k == "ENTER":
            if self.edit_target.startswith("p"):
                self._pe_commit()
            elif self.edit_target == "dir":
'''),
    (r'''        elif k == "x":
            self._stop()
''',
     r'''        elif k == "p":
            self._cycle_profile()
        elif k == "P":
            self._pe_open()
        elif k == "x":
            self._stop()
'''),
    (r'''    def _nav_key(self, k):
''', MENU_METHODS),
])

# ─────────────── view.py ───────────────
VIEW_METHODS = r'''    def _sec_profile(self):
        """Resumen del perfil activo (solo lectura; p cambia de perfil, P abre el editor)."""
        if self.model < 0 or self.opts["ollama"] or not self.pname:
            return
        names = list(self.pdoc.get(MODELS[self.model][0], {}).get("perfiles", {}))
        pos = f"{names.index(self.pname) + 1}/{len(names)}" if self.pname in names else "1/1"
        p = {**self.prof, **{k: self.params[k] for k in profiles.SHARED}}
        self._add(self._section("Perfil"))
        left = [("◆ ", S_ACCENT), (self.pname, S_BOLD), (f" {pos}  ", S_DIM),
                (f"temp {p['temp']} · top-p {p['top_p']} · top-k {p['top_k']}", S_TEXT)]
        self._add(self._box(self._lr(left, [("p · P edita", S_DIM)])))

    def _sec_pe(self):
        """Editor del perfil activo: una fila por parámetro."""
        mid, label = MODELS[self.model][0], MODELS[self.model][1]
        names = list(self.pdoc[mid]["perfiles"])
        self._add(self._section(f"Perfil «{self.pname}» · {label} · {names.index(self.pname) + 1}/{len(names)}"))
        for j, (key, lbl, desc, vals) in enumerate(profiles.FIELDS):
            v = self._pget(key) or "—"
            segs = [(" ⇄  " if vals else " ✎  ", S_DIM), (f"{lbl:<11}", S_TEXT),
                    (f" {v:<10}", S_YELLOW), (f" {desc}", S_DIM)]
            self._add(self._box(segs, self._bg(j)), focus=True)
        if self.editing and self.edit_target.startswith("p"):
            self._add(self._section("Nombre" if self.edit_target in ("pnew", "pren") else "Valor"))
            left = [("› ", S_KEY), (self.buf, S_TEXT), ("▏", S_KEY)]
            self._add(self._box(self._lr(left, [("enter ok · esc cancela", S_FAINT)])))
        self._add(self._rule("╰", "╯"))
        self._add("")
        for pairs in (
            [("↑↓", "mover"), ("espacio", "valores"), ("enter", "escribir"), ("esc", "volver")],
            [("p", "otro perfil"), ("n", "nuevo (copia)"), ("R", "renombrar"), ("X", "borrar")],
        ):
            for ln in self._hint(pairs):
                self._add(ln)
        if self.msg:
            self._add("")
            self._add(self._centered([(self.msg[:self.width], self.msg_style)]))

    def _sec_params(self):
'''

plan("menu/qwen_menu/view.py", "_sec_pe", [
    (r'''from .system import gb, short_path, voz_perfil
''',
     r'''from . import profiles
from .system import gb, short_path, voz_perfil
'''),
    (r'''        self._sec_header()
        self._sec_models()
        self._sec_options()
''',
     r'''        self._sec_header()
        if self.pe:   # editor de perfil: reemplaza al menú principal
            self._sec_pe()
            self._focus_lines = self._fl
            return self._ln
        self._sec_models()
        self._sec_profile()
        self._sec_options()
'''),
    (r'''            [("d", "carpeta de claude"), ("D", "selector gráfico"), ("t/T", "contexto/temp.")],
''',
     r'''            [("d", "carpeta de claude"), ("D", "selector gráfico"), ("t/T/C", "contexto/temp./KV"),
             ("p", "perfil"), ("P", "editar perfil")],
'''),
    (r'''    def _sec_params(self):
''', VIEW_METHODS),
])

# ─────────────── qwen-local.sh ───────────────
plan("qwen-local.sh", "P_NCMOE", [
    (r'''P_CTX P_TEMP P_IDIOMA P_KEV P_KVQ _lb_prev''',
     r'''P_CTX P_TEMP P_IDIOMA P_KEV P_KVQ P_TOPP P_TOPK P_MINP P_NCMOE P_NGL P_LOADMODE P_BATCH P_UB P_EXTRA _lb_prev'''),
    (r'''          QWENX_CTX="${P_CTX:-$QWENX_CTX}" QWENX_TEMP="${P_TEMP:-0.6}" QWENX_KV="${P_KVQ:-$QWENX_KV}" \
''',
     r'''          QWENX_CTX="${P_CTX:-$QWENX_CTX}" QWENX_TEMP="${P_TEMP:-0.6}" QWENX_KV="${P_KVQ:-$QWENX_KV}" \
          QWENX_TOPP="${P_TOPP:-}" QWENX_TOPK="${P_TOPK:-}" QWENX_MINP="${P_MINP:-}" \
          QWENX_NCMOE="${P_NCMOE:-$QWENX_NCMOE}" QWENX_NGL="${P_NGL:-${QWENX_NGL:-}}" \
          QWENX_LOADMODE="${P_LOADMODE:-$QWENX_LOADMODE}" QWENX_BATCH="${P_BATCH:-$QWENX_BATCH}" \
          QWENX_UB="${P_UB:-$QWENX_UB}" QWENX_EXTRA="${P_EXTRA:-${QWENX_EXTRA:-}}" \
'''),
])

# ─────────────── lib/llama.sh ───────────────
plan("lib/llama.sh", "QWENX_TOPP", [
    (r'''_qwen_fingerprint() {
  printf '%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s\n' \
    "$1" "$2" "$QWENX_NCMOE" "$QWENX_CTX" "$QWENX_BATCH" "$QWENX_UB" "$QWENX_LOADMODE" "${QWENX_NOTHINK:-0}" \
    "${QWENX_TEMP:-0.6}" "$QWENX_KV" "${QWENX_FLAGS:-}"
}
''',
     r'''_qwen_fingerprint() {
  printf '%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s\n' \
    "$1" "$2" "$QWENX_NCMOE" "$QWENX_CTX" "$QWENX_BATCH" "$QWENX_UB" "$QWENX_LOADMODE" "${QWENX_NOTHINK:-0}" \
    "${QWENX_TEMP:-0.6}" "$QWENX_KV" "${QWENX_FLAGS:-}" \
    "${QWENX_TOPP:-0.95}" "${QWENX_TOPK:-20}" "${QWENX_MINP:-0.0}" "${QWENX_NGL:-}" "${QWENX_EXTRA:-}" "$QWENX_CRAM"
}
'''),
    (r'''    --temp "${QWENX_TEMP:-0.6}" --top-p 0.95 --top-k 20 --min-p 0.0 \
''',
     r'''    --temp "${QWENX_TEMP:-0.6}" --top-p "${QWENX_TOPP:-0.95}" --top-k "${QWENX_TOPK:-20}" --min-p "${QWENX_MINP:-0.0}" \
'''),
])

# ─────────────── lib/pi.sh ───────────────
plan("lib/pi.sh", "sp_.update", [
    (r'''  python3 - "$QWEN_PI_DIR" "$provider" "$model" "$ctx" "$vision" <<'PY'
''',
     r'''  python3 - "$QWEN_PI_DIR" "$provider" "$model" "$ctx" "$vision" \
    "${QWENX_TEMP:-0.6}" "${QWENX_TOPP:-0.95}" "${QWENX_TOPK:-20}" "${QWENX_MINP:-0.0}" <<'PY'
'''),
    (r'''m["maxTokens"] = min(16384, max(512, ctx // 4))   # con 8192 el thinking se cortaba sin responder
''',
     r'''m["maxTokens"] = min(16384, max(512, ctx // 4))   # con 8192 el thinking se cortaba sin responder
sp_ = m.get("samplingParams")   # solo el proveedor local lo trae: Pi manda el mismo muestreo que llama-server
if isinstance(sp_, dict):
    try:
        sp_.update(temperature=float(sys.argv[6]), top_p=float(sys.argv[7]), top_k=int(sys.argv[8]), min_p=float(sys.argv[9]))
    except ValueError:
        pass
'''),
])

for rel, text in results.items():
    with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  {rel}: parchado")
PATCH_EOF

echo "Aplicando parche..."
if ! python3 "$PATCH" "$ROOT"; then restore; exit 1; fi

# ───────────────────────── verificación ─────────────────────────
echo "Verificando..."
ok=1
python3 - menu/qwen_menu/menu.py menu/qwen_menu/view.py menu/qwen_menu/profiles.py <<'CHK_EOF' || ok=0
import ast, sys
for f in sys.argv[1:]:
    ast.parse(open(f, encoding="utf-8").read(), f)
CHK_EOF
for f in qwen-local.sh lib/llama.sh lib/pi.sh; do bash -n "$f" || ok=0; done
(cd menu && PYTHONDONTWRITEBYTECODE=1 python3 -c "import qwen_menu.menu") || ok=0
if [ "$ok" != 1 ]; then restore; echo "Falló la verificación: nada quedó modificado." >&2; exit 1; fi

echo "Listo. Respaldo en $BK"
echo "Perfiles en: ${QWEN_DATA:-$HOME/.local/share/qwen}/profiles.json (se crea al primer cambio)"
