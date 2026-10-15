#!/usr/bin/env bash
# qwen-setup.sh — instalador de Qwen3.6-35B-A3B local (Pi + llama.cpp + laya).
# El código, la config de Pi y los skills viven en la repo; este script solo crea symlinks en ~/.
#
# Uso:
#   ./setup/qwen-setup.sh              instala/actualiza
#   ./setup/qwen-setup.sh --check      comprueba el estado sin modificar nada
#   ./setup/qwen-setup.sh --no-laya    instala sin preparar el venv de laya
#   ./setup/qwen-setup.sh --uninstall  quita los symlinks y la línea de ~/.bashrc
#
# Qué hace:
#   ~/.qwen-local.sh  →  <repo>/qwen-local.sh   (symlink)
#   ~/.pi-qwen        →  <repo>/.pi-qwen        (symlink; Pi usa ~/.pi-qwen/agent; no toca ~/.pi/agent)
#   ~/.agents         →  <repo>/.agents         (symlink; skills globales en ~/.agents/skills)
#   ~/.bashrc         →  una línea que carga ~/.qwen-local.sh
#   pi agent-dir      →  models.json / settings.json / AGENTS.md vía lib/pi.sh (se registra si cambian)
#   laya venv         →  ~/.local/share/qwen/laya-venv (o laya/.venv si ya existe)
#   kev               →  solo avisa si falta su venv (kev/kev-repo/.venv); no lo crea
#   menú              →  menu/qwen-menu.py (entrada) + menu/qwen_menu/ (paquete); solo se comprueban
#
# Si un destino de symlink ya existe como archivo/directorio REAL, se mueve a <ruta>.bak-<fecha> antes
# de enlazar (no se migra su contenido a la repo). Un symlink previo que apunte a otra parte se reemplaza
# y su destino anterior queda en el log.
#
# Al final de cada instalación/--uninstall se imprime la lista de acciones y todo queda en:
#   ~/.cache/qwenx/setup-<fecha>.log   (QWEN_SETUP_LOG_DIR lo cambia; se conservan los 10 últimos)
set -euo pipefail

QWEN_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
export QWEN_ROOT
TS="$(date +%Y%m%d-%H%M%S)"

# --- Log: instalar/--uninstall se relanzan a sí mismos pasando por tee (captura también lib/*.sh) ---
LOG_DIR="${QWEN_SETUP_LOG_DIR:-$HOME/.cache/qwenx}"
if [ -z "${QWEN_SETUP_LOGFILE:-}" ]; then
  case "${1:-}" in
    ""|--no-laya|--uninstall)
      mkdir -p "$LOG_DIR"
      ( ls -1t "$LOG_DIR"/setup-*.log 2>/dev/null || true ) | tail -n +10 | xargs -r rm -f --
      QWEN_SETUP_LOGFILE="$LOG_DIR/setup-$TS-$$.log"
      export QWEN_SETUP_LOGFILE
      printf '# qwen-setup.sh %s\n# fecha:   %s\n# usuario: %s@%s\n# repo:    %s\n# HOME:    %s\n\n' \
        "${1:-(instalar)}" "$(date '+%F %T')" "$(id -un)" "${HOSTNAME:-?}" "$QWEN_ROOT" "$HOME" > "$QWEN_SETUP_LOGFILE"
      # con pipefail+errexit, si el hijo falla este script sale con su mismo código
      bash "${BASH_SOURCE[0]}" "$@" 2>&1 | tee -a "$QWEN_SETUP_LOGFILE"
      exit 0
      ;;
  esac
fi

BASHRC="$HOME/.bashrc"
MARK='# Qwen local (Pi + llama.cpp + laya) — qwen-setup.sh'
SOURCE_LINE='[ -f "$HOME/.qwen-local.sh" ] && { unalias qwen qwenx qwen-ollama qwen-incognito qwen-edit qwen-edit-incognito qwenh qwenh-incognito qwenh-edit qwenh-edit-incognito qwen-vision qwen-vision-incognito qwenh-vision qwenh-vision-incognito qwen-lite 2>/dev/null || true; source "$HOME/.qwen-local.sh"; }'

# Symlinks que gestiona el instalador: origen (en la repo) → destino (en ~).
LINK_SRC=("$QWEN_ROOT/qwen-local.sh" "$QWEN_ROOT/.pi-qwen" "$QWEN_ROOT/.agents")
LINK_DST=("$HOME/.qwen-local.sh"     "$HOME/.pi-qwen"      "$HOME/.agents")
# Directorios que deben existir dentro de la repo (en un clon nuevo no vienen si están en .gitignore).
REPO_DIRS=("$QWEN_ROOT/.pi-qwen/agent" "$QWEN_ROOT/.agents/skills")
# Archivos de Pi que escribe lib/pi.sh (_qwen_pi_init); se compara su hash antes/después.
PI_MANAGED=(models.json settings.json AGENTS.md)

# Archivos que qwen-local.sh y el menú necesitan (qwen-local.sh carga config laya llama pi claude).
REQUIRED=(qwen-local.sh lib/config.sh lib/laya.sh lib/llama.sh lib/pi.sh lib/claude.sh
          menu/qwen-menu.py menu/qwen_menu/__init__.py menu/qwen_menu/config.py
          menu/qwen_menu/style.py menu/qwen_menu/system.py menu/qwen_menu/term.py
          menu/qwen_menu/view.py menu/qwen_menu/menu.py)

ACTIONS=()

say() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# act ESTADO "texto": registra una acción para la lista final.
# Estados: CREADO · ACTUALIZADO · SIN_CAMBIOS · RESPALDADO · ELIMINADO · AVISO
act() { ACTIONS+=("$(printf '%-14s %s' "[$1]" "$2")"); }

print_summary() {
  [ "${#ACTIONS[@]}" -gt 0 ] || return 0
  say
  say "== Acciones realizadas =="
  local a
  for a in "${ACTIONS[@]}"; do say "  $a"; done
  [ -z "${QWEN_SETUP_LOGFILE:-}" ] || { say; say "Log completo: $QWEN_SETUP_LOGFILE"; }
  ACTIONS=()
  return 0
}
trap print_summary EXIT   # si algo falla a mitad, igual se muestra lo hecho hasta ahí

# Sintaxis de un .py sin escribir __pycache__ (no ensucia la repo).
py_syntax() {
  python3 -B -c 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")' "$1" 2>/dev/null
}

# El menú debe ser la entrada delgada que usa el paquete qwen_menu; si no, hay una versión monolítica.
menu_entry_ok() {
  grep -q 'from qwen_menu' "$QWEN_ROOT/menu/qwen-menu.py" 2>/dev/null
}

hash_of() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1 || true; }

# link_path <origen-en-repo> <symlink>: crea/actualiza el symlink; respalda lo que haya de real.
link_path() {
  local src="$1" link="$2" cur bak
  if [ -L "$link" ]; then
    cur="$(readlink "$link")"
    if [ "$(readlink -f "$link")" = "$(readlink -f "$src")" ]; then
      act SIN_CAMBIOS "symlink $link → $cur"
    else
      ln -sfn "$src" "$link"
      act ACTUALIZADO "symlink $link: antes → $cur, ahora → $src"
    fi
  elif [ -e "$link" ]; then
    bak="$link.bak-$TS"
    mv -- "$link" "$bak"
    ln -s "$src" "$link"
    act RESPALDADO "$link (era real) → $bak"
    act CREADO "symlink $link → $src"
    if [ -d "$src" ] && [ -z "$(ls -A "$src")" ]; then
      act AVISO "$src está vacío: el contenido anterior NO se migró, sigue en $bak"
    fi
  else
    mkdir -p "$(dirname "$link")"
    ln -s "$src" "$link"
    act CREADO "symlink $link → $src"
  fi
}

# unlink_ours <origen-en-repo> <symlink>: quita el symlink solo si apunta a la repo.
unlink_ours() {
  local src="$1" link="$2"
  if [ -L "$link" ]; then
    if [ "$(readlink -f "$link")" = "$(readlink -f "$src")" ]; then
      rm -f -- "$link"
      act ELIMINADO "symlink $link (apuntaba a $src)"
    else
      act AVISO "$link es un symlink a otra ruta ($(readlink "$link")); no se toca"
    fi
  elif [ -e "$link" ]; then
    act AVISO "$link no es un symlink; no se toca"
  else
    act SIN_CAMBIOS "$link no existía"
  fi
}

check_link() {
  local src="$1" link="$2"
  if [ -L "$link" ] && [ ! -e "$link" ]; then
    say "symlink:  $link ROTO → $(readlink "$link") (¿disco/ruta no disponible?)"
  elif [ -L "$link" ] && [ "$(readlink -f "$link")" = "$(readlink -f "$src")" ]; then
    say "symlink:  $link → $src"
  elif [ -L "$link" ]; then
    say "symlink:  $link apunta a $(readlink "$link"), NO a la repo (ejecuta el instalador)"
  elif [ -e "$link" ]; then
    say "symlink:  $link es un archivo/directorio real, no un symlink (el instalador lo respalda y enlaza)"
  else
    say "symlink:  $link no existe (ejecuta el instalador)"
  fi
  if [ ! -e "$src" ]; then say "FALTA en la repo: ${src#"$QWEN_ROOT"/}"; fi
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
  # sin líneas en blanco al final: así cada ejecución es idempotente (antes sumaba una línea en blanco por corrida)
  bashrc_without_ours | awk '{ l[NR] = $0 } END { n = NR; while (n > 0 && l[n] == "") n--; for (i = 1; i <= n; i++) print l[i] }' > "$tmp"
  if [ "${1:-}" = "--add" ]; then
    printf '\n%s\n%s\n' "$MARK" "$SOURCE_LINE" >> "$tmp"
  fi
  chmod --reference="$BASHRC" "$tmp" 2>/dev/null || chmod 644 "$tmp"
  mv -f "$tmp" "$BASHRC"
}

# bashrc_apply [--add]: write_bashrc + registro de si cambió algo.
bashrc_apply() {
  local existed=1 before after msg
  [ -f "$BASHRC" ] || existed=0
  before=""
  if [ -f "$BASHRC" ]; then before="$(cksum < "$BASHRC")"; fi
  write_bashrc "${1:-}"
  after="$(cksum < "$BASHRC")"
  if [ "${1:-}" = "--add" ]; then msg="línea de carga de ~/.qwen-local.sh"; else msg="línea de carga eliminada"; fi
  if [ "$existed" = 0 ]; then act CREADO "~/.bashrc: $msg"
  elif [ "$before" = "$after" ]; then act SIN_CAMBIOS "~/.bashrc: $msg"
  else act ACTUALIZADO "~/.bashrc: $msg"; fi
}

check() {
  local i f tracked PI_DIR
  PI_DIR="${QWEN_PI_DIR:-$HOME/.pi-qwen/agent}"
  say "== Instalación de Qwen =="
  for i in "${!LINK_SRC[@]}"; do check_link "${LINK_SRC[$i]}" "${LINK_DST[$i]}"; done
  for f in "${REPO_DIRS[@]}"; do
    if [ -d "$f" ]; then say "repo dir: ${f#"$QWEN_ROOT"/} OK"; else say "repo dir: FALTA ${f#"$QWEN_ROOT"/} (el instalador lo crea)"; fi
  done
  say "pi dir:   $PI_DIR → real: $(readlink -f "$PI_DIR")"
  if grep -qF "$SOURCE_LINE" "$BASHRC" 2>/dev/null; then
    say "~/.bashrc: carga ~/.qwen-local.sh"
  else
    say "~/.bashrc: NO carga ~/.qwen-local.sh con la línea actual"
  fi
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
  if grep -qF "qwen-local:begin" "$PI_DIR/AGENTS.md" 2>/dev/null; then
    say "pi AGENTS.md: aviso de carpeta de agente presente"
  else
    say "pi AGENTS.md: falta el aviso (ejecuta el instalador o abre qwen)"
  fi
  if command -v git >/dev/null 2>&1 && git -C "$QWEN_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    # archivos trackeados que el .gitignore actual ignora = cosas privadas/regenerables que no deberían estar en git
    tracked="$(git -C "$QWEN_ROOT" ls-files -ci --exclude-standard -- .pi-qwen .agents | head -n 3 || true)"
    if [ -n "$tracked" ]; then
      say "AVISO git: hay archivos trackeados que el .gitignore ignora (p. ej. $(printf '%s' "$tracked" | head -n 1)); hay que sacarlos de git"
    else
      say "git: ningún archivo privado/regenerable de .pi-qwen o .agents está trackeado"
    fi
  fi
  say
  bash -c '. "$1" && qwen-status' _ "$QWEN_ROOT/qwen-local.sh"
}

case "${1:-}" in
  --check) check; exit 0 ;;
  --help|-h) awk 'NR > 1 { if (/^#/) print; else exit }' "${BASH_SOURCE[0]}"; exit 0 ;;
  --uninstall)
    for i in "${!LINK_SRC[@]}"; do unlink_ours "${LINK_SRC[$i]}" "${LINK_DST[$i]}"; done
    bashrc_apply
    say "La repo no se ha tocado: .pi-qwen y .agents siguen en $QWEN_ROOT."
    print_summary
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

# 1) Directorios de la repo que deben existir (en un clon nuevo faltan si están en .gitignore)
for d in "${REPO_DIRS[@]}"; do
  [ -d "$d" ] || { mkdir -p "$d"; act CREADO "dir en repo: ${d#"$QWEN_ROOT"/}"; }
done

# 2) Symlinks ~/.qwen-local.sh, ~/.pi-qwen y ~/.agents → repo (respalda lo real que haya)
for i in "${!LINK_SRC[@]}"; do link_path "${LINK_SRC[$i]}" "${LINK_DST[$i]}"; done

# 2b) auth.json (credenciales de Pi) ahora vive dentro de la repo: dejarlo en 600
AUTH="$QWEN_ROOT/.pi-qwen/agent/auth.json"
if [ -f "$AUTH" ]; then
  perm="$(stat -c %a "$AUTH")"
  if [ "$perm" = 600 ]; then
    act SIN_CAMBIOS "permisos de auth.json: 600"
  else
    chmod 600 "$AUTH" 2>/dev/null || true
    perm2="$(stat -c %a "$AUTH")"
    if [ "$perm2" = 600 ]; then act ACTUALIZADO "permisos de auth.json: $perm → 600"
    else act AVISO "no pude dejar auth.json en 600 (¿sistema de archivos sin permisos POSIX?); sigue en $perm2"; fi
  fi
fi

# 3) Configuración de Pi (lib/pi.sh; no toca ~/.pi/agent). Escribe a través del symlink, o sea en la repo.
PI_DIR="${QWEN_PI_DIR:-$HOME/.pi-qwen/agent}"
declare -A PI_BEFORE=()
for f in "${PI_MANAGED[@]}"; do PI_BEFORE[$f]="$(hash_of "$PI_DIR/$f")"; done
(
  # shellcheck source=/dev/null
  . "$QWEN_ROOT/lib/config.sh"
  . "$QWEN_ROOT/lib/pi.sh"
  _qwen_pi_init
)
for f in "${PI_MANAGED[@]}"; do
  after="$(hash_of "$PI_DIR/$f")"
  if [ -z "$after" ]; then act AVISO "pi: $f no existe en $PI_DIR tras la inicialización"
  elif [ -z "${PI_BEFORE[$f]}" ]; then act CREADO "pi: $f"
  elif [ "${PI_BEFORE[$f]}" != "$after" ]; then act ACTUALIZADO "pi: $f reescrito por lib/pi.sh (revisa el diff)"
  else act SIN_CAMBIOS "pi: $f"; fi
done

# 4) Laya: venv (necesita red solo la primera vez)
if [ "$WITH_LAYA" = 1 ]; then
  rc=0
  (
    . "$QWEN_ROOT/lib/config.sh"
    . "$QWEN_ROOT/lib/laya.sh"
    if [ -f "$LAYA_SERVER" ]; then
      _laya_ensure_venv || { say "AVISO: no se pudo preparar el venv de laya; qwen funcionará sin laya"; exit 10; }
    else
      say "AVISO: no encuentro $LAYA_SERVER"; exit 11
    fi
  ) || rc=$?
  case "$rc" in
    0)  act SIN_CAMBIOS "laya: venv listo (preparado o ya existía)" ;;
    10) act AVISO "laya: no se pudo preparar el venv (qwen funciona sin laya)" ;;
    11) act AVISO "laya: no se encontró el servidor de laya" ;;
    *)  act AVISO "laya: comprobación falló (código $rc)" ;;
  esac
else
  act SIN_CAMBIOS "laya: omitido (--no-laya)"
fi

# 4b) Kev: solo avisa (opciones Kev / Claude lo necesitan; no se instala aquí)
rc=0
(
  . "$QWEN_ROOT/lib/config.sh"
  [ -x "$KEV_PY" ] && exit 0
  if [ -z "$(ls -A "$KEV_DIR" 2>/dev/null)" ]; then
    say "AVISO: $KEV_DIR está vacío (submódulo sin clonar); las opciones Kev/Claude no arrancarán"; exit 12
  fi
  say "AVISO: kev sin venv ($KEV_PY); crea con:  cd $KEV_DIR && uv sync --extra serve"; exit 13
) || rc=$?
case "$rc" in
  0)  act SIN_CAMBIOS "kev: venv presente" ;;
  12) act AVISO "kev: carpeta vacía (opciones Kev/Claude no arrancarán)" ;;
  13) act AVISO "kev: sin venv (no se instala aquí)" ;;
  *)  act AVISO "kev: comprobación falló (código $rc)" ;;
esac

# 5) ~/.bashrc: una sola línea de carga
bashrc_apply --add

# 6) Limpieza de restos de versiones anteriores (solo los generados por el instalador viejo)
for f in "$HOME"/.cache/qwenx/llama-*.log "$HOME"/.cache/qwenx/laya.log; do
  if [ -e "$f" ]; then rm -f -- "$f"; act ELIMINADO "log antiguo: $f"; fi
done
if [ -L /tmp/llama-server.log ]; then rm -f /tmp/llama-server.log; act ELIMINADO "symlink antiguo: /tmp/llama-server.log"; fi
if [ -f "$HOME/.local/share/qwen/qwen-menu.py" ] || [ -d "$HOME/.local/share/qwen/rich-venv" ]; then
  say "Restos del menú antiguo (ya no se usan; puedes borrarlos):"
  [ -f "$HOME/.local/share/qwen/qwen-menu.py" ] && say "  rm ~/.local/share/qwen/qwen-menu.py"
  [ -d "$HOME/.local/share/qwen/rich-venv" ] && say "  rm -r ~/.local/share/qwen/rich-venv"
  act AVISO "restos del menú antiguo en ~/.local/share/qwen (ver comandos arriba)"
fi

print_summary
say
say "Listo. Ejecuta:  source ~/.bashrc   y luego:  qwen"
say "  qwen / qwenh sin argumentos → menú TUI;  con argumentos → lanza directo a pi"
say "  ./setup/qwen-setup.sh --check para revisar el estado"
say "AVISO: la opción Edición da a Pi escritura y bash. Úsala solo en proyectos de confianza."
