#!/usr/bin/env bash
# qwen-setup.sh — instalador de Qwen3.6-35B-A3B local (Pi + llama.cpp + laya).
# Todo el código vive en la repo; este script solo crea symlinks y la config de Pi.
#
# Uso:
#   ./setup/qwen-setup.sh              instala/actualiza
#   ./setup/qwen-setup.sh --check      comprueba el estado sin modificar nada
#   ./setup/qwen-setup.sh --no-laya    instala sin preparar el venv de laya
#   ./setup/qwen-setup.sh --uninstall  quita el symlink y la línea de ~/.bashrc
#
# Qué hace:
#   ~/.qwen-local.sh  →  <repo>/qwen-local.sh   (symlink)
#   ~/.bashrc         →  una línea que carga ~/.qwen-local.sh
#   ~/.pi-qwen/agent  →  models.json / settings.json / AGENTS.md de Pi (no toca ~/.pi/agent)
#   laya venv         →  ~/.local/share/qwen/laya-venv (o laya/.venv si ya existe)
#   kev               →  solo avisa si falta su venv (kev/kev-repo/.venv); no lo crea
#   menú              →  menu/qwen-menu.py (entrada) + menu/qwen_menu/ (paquete); solo se comprueban
set -euo pipefail

QWEN_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
export QWEN_ROOT

LINK="$HOME/.qwen-local.sh"
TARGET="$QWEN_ROOT/qwen-local.sh"
BASHRC="$HOME/.bashrc"
MARK='# Qwen local (Pi + llama.cpp + laya) — qwen-setup.sh'
SOURCE_LINE='[ -f "$HOME/.qwen-local.sh" ] && { unalias qwen qwenx qwen-ollama qwen-incognito qwen-edit qwen-edit-incognito qwenh qwenh-incognito qwenh-edit qwenh-edit-incognito qwen-vision qwen-vision-incognito qwenh-vision qwenh-vision-incognito qwen-lite 2>/dev/null || true; source "$HOME/.qwen-local.sh"; }'

# Archivos que qwen-local.sh y el menú necesitan (qwen-local.sh carga config laya llama pi claude).
REQUIRED=(qwen-local.sh lib/config.sh lib/laya.sh lib/llama.sh lib/pi.sh lib/claude.sh
          menu/qwen-menu.py menu/qwen_menu/__init__.py menu/qwen_menu/config.py
          menu/qwen_menu/style.py menu/qwen_menu/system.py menu/qwen_menu/term.py
          menu/qwen_menu/view.py menu/qwen_menu/menu.py)

say() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# Sintaxis de un .py sin escribir __pycache__ (no ensucia la repo).
py_syntax() {
  python3 -B -c 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")' "$1" 2>/dev/null
}

# El menú debe ser la entrada delgada que usa el paquete qwen_menu; si no, hay una versión monolítica.
menu_entry_ok() {
  grep -q 'from qwen_menu' "$QWEN_ROOT/menu/qwen-menu.py" 2>/dev/null
}

# Quita de ~/.bashrc nuestra línea (y las de versiones anteriores), conservando el resto.
bashrc_without_ours() {
  [ -f "$BASHRC" ] || return 0
  grep -vF -e "$SOURCE_LINE" -e "$MARK" \
           -e '# Config local Qwen + Pi (qwen-setup-pi.sh)' \
           -e '[ -f "$HOME/.qwen-local.sh" ] && source "$HOME/.qwen-local.sh"' "$BASHRC" || true
}

write_bashrc() {   # write_bashrc [--add]
  local tmp
  tmp="$(mktemp "$HOME/.bashrc.qwen.XXXXXX")"
  bashrc_without_ours > "$tmp"
  if [ "${1:-}" = "--add" ]; then
    printf '\n%s\n%s\n' "$MARK" "$SOURCE_LINE" >> "$tmp"
  fi
  chmod --reference="$BASHRC" "$tmp" 2>/dev/null || chmod 644 "$tmp"
  mv -f "$tmp" "$BASHRC"
}

check() {
  say "== Instalación de Qwen =="
  if [ -L "$LINK" ] && [ "$(readlink -f "$LINK")" = "$(readlink -f "$TARGET")" ]; then
    say "symlink:  $LINK → $TARGET"
  elif [ -e "$LINK" ]; then
    say "symlink:  $LINK existe pero NO apunta a la repo (ejecuta el instalador)"
  else
    say "symlink:  $LINK no existe (ejecuta el instalador)"
  fi
  grep -qF "$SOURCE_LINE" "$BASHRC" 2>/dev/null \
    && say "~/.bashrc: carga ~/.qwen-local.sh" \
    || say "~/.bashrc: NO carga ~/.qwen-local.sh con la línea actual"
  for f in "${REQUIRED[@]}"; do
    if [ -f "$QWEN_ROOT/$f" ]; then
      case "$f" in
        *.sh) bash -n "$QWEN_ROOT/$f" && say "sintaxis OK: $f" || say "ERROR de sintaxis: $f" ;;
        *.py) py_syntax "$QWEN_ROOT/$f" && say "sintaxis OK: $f" || say "ERROR de sintaxis: $f" ;;
      esac
    else
      say "FALTA: $f"
    fi
  done
  menu_entry_ok || say "AVISO: menu/qwen-menu.py NO usa el paquete qwen_menu (¿versión monolítica antigua?)"
  if grep -qF "qwen-local:begin" "${QWEN_PI_DIR:-$HOME/.pi-qwen/agent}/AGENTS.md" 2>/dev/null; then
    say "pi AGENTS.md: aviso de carpeta de agente presente"
  else
    say "pi AGENTS.md: falta el aviso (ejecuta el instalador o abre qwen)"
  fi
  say
  bash -c '. "$1" && qwen-status' _ "$TARGET"
}

case "${1:-}" in
  --check) check; exit 0 ;;
  --help|-h) awk 'NR > 1 { if (/^#/) print; else exit }' "${BASH_SOURCE[0]}"; exit 0 ;;
  --uninstall)
    [ -L "$LINK" ] && rm -f "$LINK" && say "symlink eliminado: $LINK"
    write_bashrc && say "línea eliminada de $BASHRC"
    say "La repo y ~/.pi-qwen no se han tocado."
    exit 0 ;;
  ""|--no-laya) ;;
  *) die "opción desconocida: $1 (usa --help)" ;;
esac
WITH_LAYA=1; [ "${1:-}" = "--no-laya" ] && WITH_LAYA=0

for dep in python3 curl; do
  command -v "$dep" >/dev/null 2>&1 || die "falta dependencia requerida: $dep"
done
for f in "${REQUIRED[@]}"; do
  [ -f "$QWEN_ROOT/$f" ] || die "falta $QWEN_ROOT/$f (repo incompleta)"
done
menu_entry_ok || say "AVISO: menu/qwen-menu.py NO usa el paquete qwen_menu (¿versión monolítica antigua?)"
chmod +x "$QWEN_ROOT/menu/qwen-menu.py" "$QWEN_ROOT/setup/qwen-setup.sh"

# 1) Symlink ~/.qwen-local.sh → repo (respalda un archivo real previo)
if [ -e "$LINK" ] && [ ! -L "$LINK" ]; then
  bak="$LINK.bak-$(date +%Y%m%d-%H%M%S)"
  mv -f "$LINK" "$bak"
  say "respaldo del ~/.qwen-local.sh anterior: $bak"
fi
ln -sfn "$TARGET" "$LINK"
say "symlink: $LINK → $TARGET"

# 2) Configuración de Pi (reutiliza lib/pi.sh; no toca ~/.pi/agent)
(
  # shellcheck source=/dev/null
  . "$QWEN_ROOT/lib/config.sh"
  . "$QWEN_ROOT/lib/pi.sh"
  _qwen_pi_init
)

# 3) Laya: venv (necesita red solo la primera vez)
if [ "$WITH_LAYA" = 1 ]; then
  (
    . "$QWEN_ROOT/lib/config.sh"
    . "$QWEN_ROOT/lib/laya.sh"
    if [ -f "$LAYA_SERVER" ]; then _laya_ensure_venv || say "AVISO: no se pudo preparar el venv de laya; qwen funcionará sin laya"
    else say "AVISO: no encuentro $LAYA_SERVER"; fi
  )
fi

# 3b) Kev: solo avisa (opciones Kev / Claude lo necesitan; no se instala aquí)
(
  . "$QWEN_ROOT/lib/config.sh"
  if [ ! -x "$KEV_PY" ]; then
    if [ -z "$(ls -A "$KEV_DIR" 2>/dev/null)" ]; then
      say "AVISO: $KEV_DIR está vacío (submódulo sin clonar); las opciones Kev/Claude no arrancarán"
    else
      say "AVISO: kev sin venv ($KEV_PY); crea con:  cd $KEV_DIR && uv sync --extra serve"
    fi
  fi
)

# 4) ~/.bashrc: una sola línea de carga
write_bashrc --add
say "~/.bashrc actualizado"

# 5) Limpieza de restos de versiones anteriores (solo los generados por el instalador viejo)
rm -f "$HOME"/.cache/qwenx/llama-*.log "$HOME"/.cache/qwenx/laya.log
[ -L /tmp/llama-server.log ] && rm -f /tmp/llama-server.log || true
if [ -f "$HOME/.local/share/qwen/qwen-menu.py" ] || [ -d "$HOME/.local/share/qwen/rich-venv" ]; then
  say "Restos del menú antiguo (ya no se usan; puedes borrarlos):"
  [ -f "$HOME/.local/share/qwen/qwen-menu.py" ] && say "  rm ~/.local/share/qwen/qwen-menu.py"
  [ -d "$HOME/.local/share/qwen/rich-venv" ] && say "  rm -r ~/.local/share/qwen/rich-venv"
  true
fi

say
say "Listo. Ejecuta:  source ~/.bashrc   y luego:  qwen"
say "  qwen / qwenh sin argumentos → menú TUI;  con argumentos → lanza directo a pi"
say "  ./setup/qwen-setup.sh --check para revisar el estado"
say "AVISO: la opción Edición da a Pi escritura y bash. Úsala solo en proyectos de confianza."
