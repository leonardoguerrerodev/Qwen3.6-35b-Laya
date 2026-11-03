#!/usr/bin/env bash
# La fila «Kev» (tamaño) se ve tenue cuando la opción Kev está apagada: sin Kev no se usa.
# Uso: bash kev-tenue.sh [RAIZ_DE_LA_REPO]
set -euo pipefail
ROOT="$(cd "${1:-$PWD}" && pwd)"
cd "$ROOT"
F=menu/qwen_menu/view.py
[ -f "$F" ] || { echo "falta $F: ejecuta desde la raíz de la repo o pasa su ruta" >&2; exit 1; }
grep -q "profiles.ROW_PARAMS" "$F" || { echo "primero aplica actualizar-perfiles.sh" >&2; exit 1; }

BK="$ROOT/.bak-kev-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BK/$(dirname "$F")"; cp -a "$F" "$BK/$F"

python3 - "$F" <<'PY' || { cp -a "$BK/$F" "$F"; echo "Restaurado desde $BK" >&2; exit 1; }
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
if "S_FAINT if off" in text:
    print("  ya estaba aplicado"); sys.exit(0)
old = r'''            segs = [(" ⇄  ", S_DIM), (f"{hot} ", S_DIM), (f"{label:<9}", S_TEXT),
                    (f" {self.params[key]:<9}", S_YELLOW), (f" {desc}", S_DIM)]
            self._add(self._box(segs, self._bg(self.nm + len(OPTIONS) + j)), focus=True)
'''
new = r'''            off = key == "kev" and not self.opts["kev"]   # sin Kev activo, el tamaño no se usa
            segs = [(" ⇄  ", S_DIM), (f"{hot} ", S_DIM), (f"{label:<9}", S_FAINT if off else S_TEXT),
                    (f" {self.params[key]:<9}", S_FAINT if off else S_YELLOW),
                    (f" {desc}", S_FAINT if off else S_DIM)]
            self._add(self._box(segs, self._bg(self.nm + len(OPTIONS) + j)), focus=True)
'''
n = text.count(old)
if n != 1:
    sys.exit(f"ERROR: el ancla aparece {n} veces (debe ser 1). No se tocó nada.")
open(path, "w", encoding="utf-8").write(text.replace(old, new))
print("  view.py: actualizado")
PY

python3 -c "import ast; ast.parse(open('$F', encoding='utf-8').read())" \
  || { cp -a "$BK/$F" "$F"; echo "Restaurado desde $BK" >&2; exit 1; }
(cd menu && PYTHONDONTWRITEBYTECODE=1 python3 -c "import qwen_menu.menu") \
  || { cp -a "$BK/$F" "$F"; echo "Restaurado desde $BK" >&2; exit 1; }
echo "Listo. Respaldo en $BK"
