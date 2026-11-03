#!/usr/bin/env bash
# Actualiza los perfiles ya instalados: valor seleccionado al editar, sección Perfil
# absorbe Parámetros (quedan Kev e Idioma) y descripciones compactas.
# Uso: bash actualizar-perfiles.sh [RAIZ_DE_LA_REPO]   (por defecto: carpeta actual)
set -euo pipefail

ROOT="$(cd "${1:-$PWD}" && pwd)"
cd "$ROOT"

ALL=(menu/qwen_menu/menu.py menu/qwen_menu/view.py menu/qwen_menu/profiles.py menu/qwen_menu/config.py)

for f in "${ALL[@]}"; do
  [ -f "$f" ] || { echo "falta $f: ejecuta desde la raíz de la repo o pasa su ruta" >&2; exit 1; }
done
grep -q "profiles.load_all()" menu/qwen_menu/menu.py \
  || { echo "primero aplica aplicar-perfiles.sh (no encuentro los perfiles instalados)" >&2; exit 1; }

BK="$ROOT/.bak-perfiles2-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BK"
for f in "${ALL[@]}"; do mkdir -p "$BK/$(dirname "$f")"; cp -a "$f" "$BK/$f"; done

restore() {
  local f
  for f in "${ALL[@]}"; do cp -a "$BK/$f" "$f"; done
  echo "Restaurado desde $BK" >&2
}

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
        print(f"  {rel}: ya estaba actualizado")
        return
    for old, new in edits:
        n = text.count(old)
        if n != 1:
            sys.exit(f"ERROR en {rel}: el ancla aparece {n} veces (debe ser 1). No se tocó ningún archivo.\n--- ancla ---\n{old}")
        text = text.replace(old, new)
    results[rel] = text


# ─────────────── profiles.py ───────────────
plan("menu/qwen_menu/profiles.py", "ROW_PARAMS", [
    (r'''FIELDS = [
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
''',
     r'''FIELDS = [
    ("temp", "Temp.", "0-2 · 0.6 código, 1.0 general", _PV["temp"]),
    ("top_p", "Top-p", "0-1 · rec. 0.95", ("0.8", "0.9", "0.95", "1.0")),
    ("top_k", "Top-k", "0 = sin límite · rec. 20", ("0", "20", "40", "64")),
    ("min_p", "Min-p", "0-1 · rec. 0.0", ("0.0", "0.02", "0.05")),
    ("ctx", "Contexto", "tokens · 32k vale · auto = lanzador", _PV["ctx"]),
    ("kvq", "KV cache", "q8_0 / q4_0 ahorran memoria", _PV["kvq"]),
    ("ncmoe", "MoE en CPU", "--n-cpu-moe · vacío = lanzador", ("", "20", "28", "36", "40")),
    ("ngl", "Capas GPU", "-ngl · vacío = según modelo", ("", "auto", "20", "30", "45", "99")),
    ("loadmode", "Carga", "--load-mode · vacío = lanzador", ("", "none", "mmap", "mlock")),
    ("batch", "Batch", "-b · vacío = lanzador", ("", "512", "1024", "2048", "4096")),
    ("ub", "Ubatch", "-ub · vacío = lanzador", ("", "256", "512", "1024")),
    ("extra", "Flags extra", "flags crudos, sin comillas", ()),
]
'''),
    (r'''EXTRA_KEYS = tuple(k for k in KEYS if k not in SHARED)
''',
     r'''EXTRA_KEYS = tuple(k for k in KEYS if k not in SHARED)
ROW_PARAMS = tuple(p for p in PARAMS if p[0] not in SHARED)   # filas de la pantalla principal (no están en el perfil)
'''),
])

# ─────────────── config.py ───────────────
plan("menu/qwen_menu/config.py", "clasifica prompts (CPU)", [
    (r'''    ("ollama", "o", "Ollama", "respaldo · ignora el modelo grande"),
    ("laya", "s", "Laya", "system 1 · clasifica prompts en CPU"),
    ("kev", "y", "Kev", "backend de laya: kev en vez del checkpoint"),
    ("kevgpu", "g", "Kev GPU", "kev en CUDA en vez de CPU · con cualquier modelo o «Ninguno»"),
    ("claude", "h", "Claude", "abre Claude Code con kev de filtro (System One) · con cualquier modelo"),
    ("voz", "z", "Voz", "TTS piper/kokoro/f5/s2 · Pi responde con etiquetas de voz"),
''',
     r'''    ("ollama", "o", "Ollama", "respaldo · ignora el modelo grande"),
    ("laya", "s", "Laya", "clasifica prompts (CPU)"),
    ("kev", "y", "Kev", "backend de laya"),
    ("kevgpu", "g", "Kev GPU", "kev en CUDA, no en CPU"),
    ("claude", "h", "Claude", "Claude Code con kev de filtro"),
    ("voz", "z", "Voz", "TTS · Pi responde con etiquetas"),
'''),
    (r'''     "tamaño de kev · auto: 4b sin modelo grande, 0.8b con modelo (cabe en RAM/VRAM)"),
''',
     r'''     "auto: 4b sin modelo, 0.8b con modelo"),
'''),
    (r'''     "de la respuesta (Pi y Claude) · auto: el de tu mensaje · la voz va aparte"),
''',
     r'''     "de la respuesta · auto: el de tu mensaje"),
'''),
])

# ─────────────── menu.py ───────────────
plan("menu/qwen_menu/menu.py", "ROW_PARAMS", [
    # las filas de «Parámetros» son ahora solo las que no están en el perfil (Kev, Idioma)
    (r'''        return self.nm + len(OPTIONS) + len(PARAMS)   # fila de los argumentos
''',
     r'''        return self.nm + len(OPTIONS) + len(profiles.ROW_PARAMS)   # fila de los argumentos
'''),
    (r'''        i -= len(OPTIONS)
        if i < len(PARAMS):
            return "param", i
        i -= len(PARAMS)
''',
     r'''        i -= len(OPTIONS)
        if i < len(profiles.ROW_PARAMS):
            return "param", i
        i -= len(profiles.ROW_PARAMS)
'''),
    (r'''            self.cycle(PARAMS[idx][0])
''',
     r'''            self.cycle(profiles.ROW_PARAMS[idx][0])
'''),
    (r'''        elif k in PARAM_KEYS:
            self.cycle(PARAM_KEYS[k])
            self.focus = self.nm + len(OPTIONS) + [p[0] for p in PARAMS].index(PARAM_KEYS[k])
''',
     r'''        elif k in PARAM_KEYS:        # t / T / C cambian el perfil activo sin mover el foco; K / L son filas
            self.cycle(PARAM_KEYS[k])
            rows = [p[0] for p in profiles.ROW_PARAMS]
            if PARAM_KEYS[k] in rows:
                self.focus = self.nm + len(OPTIONS) + rows.index(PARAM_KEYS[k])
'''),
    # al pulsar enter sobre un campo, el valor viejo queda seleccionado: la primera tecla lo reemplaza
    (r'''        self._pe_main_focus = 0
''',
     r'''        self._pe_main_focus = 0
        self.sel = False            # texto del campo seleccionado: la primera tecla lo reemplaza
'''),
    (r'''        self.editing, self.edit_target = True, target
        self.buf = self.args if target == "args" else short_path(self.cdir)
''',
     r'''        self.editing, self.edit_target, self.sel = True, target, False
        self.buf = self.args if target == "args" else short_path(self.cdir)
'''),
    (r'''        elif k == "BACKSPACE":
            self.buf = self.buf[:-1]
''',
     r'''        elif k == "BACKSPACE":
            self.buf, self.sel = ("" if self.sel else self.buf[:-1]), False
'''),
    (r'''        elif len(k) == 1 and k.isprintable():
            self.buf += k
''',
     r'''        elif len(k) == 1 and k.isprintable():
            self.buf, self.sel = (k if self.sel else self.buf + k), False
'''),
    (r'''            self.editing, self.edit_target, self.buf = True, f"pfield:{key}", self._pget(key)
''',
     r'''            self.editing, self.edit_target, self.buf = True, f"pfield:{key}", self._pget(key)
            self.sel = bool(self.buf)
'''),
    (r'''            self.buf = profiles.unique_name(ent, self.pname)
''',
     r'''            self.buf = profiles.unique_name(ent, self.pname)
            self.sel = True
'''),
    (r'''            self.editing, self.edit_target, self.buf = True, "pren", self.pname
''',
     r'''            self.editing, self.edit_target, self.buf = True, "pren", self.pname
            self.sel = True
'''),
])

# ─────────────── view.py ───────────────
plan("menu/qwen_menu/view.py", "profiles.ROW_PARAMS", [
    # resumen del perfil: dos líneas (nombre + valores); el encabezado de sección lo pone _sec_params
    (r'''        self._add(self._section("Perfil"))
        left = [("◆ ", S_ACCENT), (self.pname, S_BOLD), (f" {pos}  ", S_DIM),
                (f"temp {p['temp']} · top-p {p['top_p']} · top-k {p['top_k']}", S_TEXT)]
        self._add(self._box(self._lr(left, [("p · P edita", S_DIM)])))
''',
     r'''        ctx = p["ctx"]
        if ctx == "auto":
            n = CTX_AUTO.get(MODELS[self.model][0])
            ctx = f"auto·{int(n) // 1024}k" if n else "auto·120k"
        left = [("◆ ", S_ACCENT), (self.pname, S_BOLD), (f" {pos}", S_DIM)]
        self._add(self._box(self._lr(left, [("p cambia · P edita", S_DIM)])))
        self._add(self._box([("  ", ""), (f"temp {p['temp']} · top-p {p['top_p']} · top-k {p['top_k']}"
                                         f" · ctx {ctx} · kv {p['kvq']}", S_TEXT)]))
'''),
    (r'''        self._sec_models()
        self._sec_profile()
        self._sec_options()
''',
     r'''        self._sec_models()
        self._sec_options()
'''),
    (r'''    def _sec_params(self):
        self._add(self._section("Parámetros"))
        for j, (key, hot, label, _vals, _d, desc) in enumerate(PARAMS):
            v = self.params[key]
            if key == "ctx" and v == "auto" and self.model >= 0:
                n = CTX_AUTO.get(MODELS[self.model][0])
                v = f"auto·{int(n) // 1024}k" if n else "auto·120k"
            segs = [(" ⇄  ", S_DIM), (f"{hot} ", S_DIM), (f"{label:<9}", S_TEXT),
                    (f" {v:<9}", S_YELLOW), (f" {desc}", S_DIM)]
            self._add(self._box(segs, self._bg(self.nm + len(OPTIONS) + j)), focus=True)
''',
     r'''    def _sec_params(self):
        """Sección Perfil: resumen del perfil activo + los parámetros que no son del perfil (Kev, Idioma)."""
        self._add(self._section("Perfil"))
        self._sec_profile()
        for j, (key, hot, label, _vals, _d, desc) in enumerate(profiles.ROW_PARAMS):
            segs = [(" ⇄  ", S_DIM), (f"{hot} ", S_DIM), (f"{label:<9}", S_TEXT),
                    (f" {self.params[key]:<9}", S_YELLOW), (f" {desc}", S_DIM)]
            self._add(self._box(segs, self._bg(self.nm + len(OPTIONS) + j)), focus=True)
'''),
    (r'''                    desc = f"{motor} · «{nombre}» · Z cambia · con etiquetas"
''',
     r'''                    desc = f"{motor} · «{nombre}» · Z cambia"
'''),
    # el texto seleccionado se ve en vídeo inverso
    (r'''            left = [("› ", S_KEY), (self.buf, S_TEXT), ("▏", S_KEY)]
            self._add(self._box(self._lr(left, [("enter ok · esc cancela", S_FAINT)])))
''',
     r'''            left = [("› ", S_KEY), (self.buf, "7;" + S_TEXT if self.sel else S_TEXT),
                    ("" if self.sel else "▏", S_KEY)]
            self._add(self._box(self._lr(left, [("enter ok · esc cancela", S_FAINT)])))
'''),
])

for rel, text in results.items():
    with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  {rel}: actualizado")
PATCH_EOF

echo "Aplicando cambios..."
if ! python3 "$PATCH" "$ROOT"; then restore; exit 1; fi

# ───────────────────────── verificación ─────────────────────────
echo "Verificando..."
ok=1
python3 - menu/qwen_menu/menu.py menu/qwen_menu/view.py menu/qwen_menu/profiles.py menu/qwen_menu/config.py <<'CHK_EOF' || ok=0
import ast, sys
for f in sys.argv[1:]:
    ast.parse(open(f, encoding="utf-8").read(), f)
CHK_EOF
TMPH="$(mktemp -d)"
(cd menu && HOME="$TMPH" QWEN_DATA="$TMPH/data" XDG_STATE_HOME="$TMPH/state" PYTHONDONTWRITEBYTECODE=1 python3 - <<'SMOKE_EOF') || ok=0
from qwen_menu.menu import Menu
class T:
    def size(self): return (100, 45)
    def write(self, s): pass
    def key(self, timeout=1.0): return None
m = Menu(T())
def press(*ks):
    for k in ks:
        (m._edit_key if m.editing else m._pe_key if m.pe else m._nav_key)(k)
        m.draw()
m.draw()
press("1", "K", "L", "t", "T", "C")                   # filas Kev/Idioma y atajos del perfil
press("P", "DOWN", "ENTER", "0", ".", "9", "ENTER")   # el valor viejo se reemplaza al escribir
assert m.prof["top_p"] == "0.9", m.prof["top_p"]
press("ESC")
assert not m.pe and not m.editing
SMOKE_EOF
rm -rf "$TMPH"
if [ "$ok" != 1 ]; then restore; echo "Falló la verificación: nada quedó modificado." >&2; exit 1; fi

echo "Listo. Respaldo en $BK"
