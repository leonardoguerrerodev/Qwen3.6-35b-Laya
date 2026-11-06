#!/usr/bin/env python3
"""qwen-model.py — agrega, lista, edita y quita modelos GGUF del menú de qwen.

    qwen-model                 menú interactivo
    qwen-model add [ruta]      agrega un modelo
    qwen-model list            lista los de fábrica y los agregados
    qwen-model edit [id]       cambia nombre, descripción, visión o ruta
    qwen-model rm [id]         quita un modelo agregado (no borra el .gguf)

Guarda en $QWEN_DATA/models.json (por defecto ~/.local/share/qwen/models.json).
qwen_menu/config.py lo lee y añade los modelos al FINAL de la lista del menú.
Si el .gguf está fuera de MODELS_DIR (~/models), crea un enlace simbólico ahí:
el menú solo busca dentro de esa carpeta.
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from qwen_menu.config import BUILTIN_IDS, CUSTOM_MODELS_FILE, MODELS, MODELS_DIR  # noqa: E402

RESERVED = set(BUILTIN_IDS) | {"none"}
ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]*")
SHARD_RE = re.compile(r"-(\d{5})-of-\d{5}\.gguf$", re.I)
MAX_LABEL, MAX_DESC = 14, 50   # el menú recorta lo más largo


# ── utilidades ──
def short(p):
    home = os.path.expanduser("~")
    return "~" + p[len(home):] if p.startswith(home + os.sep) else p


def ask(prompt, default=""):
    suf = f" [{default}]" if default else ""
    return input(f"{prompt}{suf}: ").strip() or default


def yes(prompt, default=True):
    r = input(f"{prompt} [{'S/n' if default else 's/N'}]: ").strip().lower()
    return default if not r else r[0] in "sy"


def load():
    try:
        with open(CUSTOM_MODELS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as e:
        sys.exit(f"No puedo leer {short(CUSTOM_MODELS_FILE)}: {e}")
    return data if isinstance(data, list) else []


def save(items):
    os.makedirs(os.path.dirname(CUSTOM_MODELS_FILE), exist_ok=True)
    tmp = CUSTOM_MODELS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, CUSTOM_MODELS_FILE)


def used(e):
    """Nombres de archivo (dentro de MODELS_DIR) que usa una entrada."""
    return {n for n in (e.get("file"), e.get("mmproj_file")) if n}


def key_of(i):
    """Tecla del menú: 1-9 (0 = Ninguno); más allá de 9 solo con flechas."""
    n = len(BUILTIN_IDS) + i + 1
    return str(n) if n <= 9 else "—"


# ── archivos ──
def read_gguf(raw, mmproj=False):
    """Ruta absoluta validada, o None (y dice por qué)."""
    p = os.path.abspath(os.path.expanduser(raw.strip().strip("'\"").replace("\\ ", " ")))
    if not os.path.isfile(p):
        print(f"  no existe: {p}")
        return None
    if not p.lower().endswith(".gguf"):
        print("  tiene que ser un archivo .gguf")
        return None
    name = os.path.basename(p).lower()
    if not mmproj and "mmproj" in name:
        print("  eso es un mmproj (visión), no un modelo: va en la pregunta de visión")
        return None
    if mmproj and "mmproj" not in name and not yes("  el nombre no dice «mmproj». ¿Seguir?", False):
        return None
    m = SHARD_RE.search(p)
    if m and m.group(1) != "00001":
        print("  es un fragmento; usa el primero (…-00001-of-…)")
        return None
    return p


def ask_path(prompt, mmproj=False):
    """Pregunta hasta que la ruta sirva; Enter vacío cancela (None)."""
    while True:
        raw = input(f"{prompt}: ").strip()
        if not raw:
            return None
        p = read_gguf(raw, mmproj)
        if p:
            return p


def expose(path):
    """Nombre con el que el menú halla el archivo dentro de MODELS_DIR → (nombre, enlace_creado)."""
    name = os.path.basename(path)
    if os.path.realpath(os.path.dirname(path)) == os.path.realpath(MODELS_DIR):
        return name, False
    dest = os.path.join(MODELS_DIR, name)
    if os.path.lexists(dest):
        if os.path.realpath(dest) == os.path.realpath(path):
            return name, False
        sys.exit(f"Ya hay otro «{name}» en {short(MODELS_DIR)}: renombra uno de los dos.")
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.symlink(path, dest)
    return name, True


def build(mid, label, desc, path, mm, old_links=()):
    """Arma la entrada y crea los enlaces que falten."""
    name, made = expose(path)
    e = {"id": mid, "label": label, "desc": desc, "pattern": glob.escape(name), "file": name,
         "path": path, "mmproj": "", "mmproj_file": "", "mmproj_path": "", "links": []}
    if made:
        e["links"].append(name)
    if mm:
        mname, mmade = expose(mm)
        e.update(mmproj=glob.escape(mname), mmproj_file=mname, mmproj_path=mm)
        if mmade:
            e["links"].append(mname)
    e["links"] += [n for n in old_links if n in used(e) and n not in e["links"]]
    return e


def drop_links(entry, others):
    """Borra los enlaces que creó `entry` y que nadie más usa; si otro modelo aún usa uno, lo hereda."""
    for name in entry.get("links", []):
        heirs = [o for o in others if name in used(o)]
        if heirs:
            if name not in heirs[0].setdefault("links", []):
                heirs[0]["links"].append(name)
            continue
        dest = os.path.join(MODELS_DIR, name)
        if os.path.islink(dest):
            os.remove(dest)


# ── entrada de datos ──
def default_id(stem, taken):
    base = re.sub(r"[^a-z0-9_-]+", "-", stem.lower()).strip("-_")[:24] or "modelo"
    mid, n = base, 2
    while mid in taken:
        mid, n = f"{base}-{n}", n + 1
    return mid


def ask_id(default, taken):
    while True:
        mid = ask("ID (sin espacios; letras minúsculas, números, - y _)", default)
        if not ID_RE.fullmatch(mid):
            print("  solo a-z, 0-9, - y _ (sin espacios)")
        elif mid in taken:
            print("  ese ID ya existe")
        else:
            return mid


def warn_len(label, desc):
    if len(label) > MAX_LABEL:
        print(f"  aviso: el nombre tiene {len(label)} caracteres; el menú puede recortarlo")
    if len(desc) > MAX_DESC:
        print(f"  aviso: la descripción tiene {len(desc)} caracteres; el menú puede recortarla")


def pick(items, mid, verb):
    if not items:
        print("No hay modelos agregados.")
        return None
    if not mid:
        for i, e in enumerate(items, 1):
            print(f"  {i}) {e['id']:<16} {e['label']}")
        mid = input(f"¿Cuál quieres {verb}? (número o id, Enter cancela): ").strip()
        if not mid:
            return None
        if mid.isdigit() and 1 <= int(mid) <= len(items):
            return items[int(mid) - 1]
    for e in items:
        if e["id"] == mid:
            return e
    print(f"«{mid}» es de fábrica (se cambia en config.py)." if mid in BUILTIN_IDS
          else f"No hay un modelo agregado con id «{mid}».")
    return None


# ── comandos ──
def cmd_add(arg=None):
    items = load()
    path = read_gguf(arg) if arg else None
    if not path:
        path = ask_path("Ruta del .gguf (Enter cancela)")
    if not path:
        return print("Cancelado.")
    stem = re.sub(r"\.gguf$", "", os.path.basename(path), flags=re.I)
    taken = RESERVED | {e["id"] for e in items}
    mid = ask_id(default_id(stem, taken), taken)
    label = ask("Nombre en el menú", stem)
    desc = ask("Descripción", os.path.splitext(os.path.basename(path))[0])   # el tamaño ya sale en su columna
    warn_len(label, desc)
    mm = ask_path("mmproj para visión (ruta; Enter = sin visión)", mmproj=True)
    print(f"\n  id:          {mid}\n  nombre:      {label}\n  descripción: {desc}"
          f"\n  archivo:     {short(path)}\n  visión:      {short(mm) if mm else 'no'}")
    if not yes("¿Guardar?"):
        return print("Cancelado.")
    items.append(build(mid, label, desc, path, mm))
    save(items)
    print(f"Listo. En el menú (`qwen`) sale con la tecla {key_of(len(items) - 1)}.")


def cmd_list(_=None):
    items = load()
    print("De fábrica:")
    for i, m in enumerate(MODELS[:len(BUILTIN_IDS)], 1):
        print(f"  {i}  {m[0]:<16} {m[1]:<12} {m[2]}")
    print("Agregados:" if items else "Agregados: (ninguno; usa `qwen-model add`)")
    for i, e in enumerate(items):
        ok = os.path.isfile(os.path.join(MODELS_DIR, e["file"]))
        vis = "con visión" if e.get("mmproj") else "sin visión"
        print(f"  {key_of(i)}  {e['id']:<16} {e['label']:<12} {e['desc']}")
        print(f"       {'✓' if ok else '✗ NO ENCUENTRO'} {short(e['path'])} · {vis}")


def cmd_edit(mid=None):
    items = load()
    old = pick(items, mid, "editar")
    if not old:
        return
    print("Enter = dejar igual")
    label = ask("Nombre", old["label"])
    desc = ask("Descripción", old["desc"])
    warn_len(label, desc)
    cur = short(old["mmproj_path"]) if old.get("mmproj_path") else "sin visión"
    r = input(f"mmproj [{cur}] (ruta nueva, - = quitar): ").strip()
    mm = old.get("mmproj_path", "")
    if r == "-":
        mm = ""
    elif r:
        mm = read_gguf(r, mmproj=True) or mm
    r = input(f"Ruta del .gguf [{short(old['path'])}]: ").strip()
    path = (read_gguf(r) if r else None) or old["path"]
    new = build(old["id"], label, desc, path, mm, old.get("links", []))
    items[items.index(old)] = new
    drop_links(old, items)
    save(items)
    print("Guardado.")


def cmd_rm(mid=None):
    items = load()
    e = pick(items, mid, "quitar")
    if not e:
        return
    if not yes(f"¿Quitar «{e['label']}» del menú? (el .gguf no se borra)", False):
        return print("Cancelado.")
    items.remove(e)
    drop_links(e, items)
    save(items)
    print("Quitado.")


def interactive():
    acts = {"1": cmd_add, "2": cmd_list, "3": cmd_edit, "4": cmd_rm}
    while True:
        print("\nqwen-model:  1) agregar  2) listar  3) editar  4) quitar  q) salir")
        k = input("> ").strip().lower()
        if k in ("q", ""):
            return
        if k in acts:
            acts[k]()


def main(argv):
    cmds = {"add": cmd_add, "list": cmd_list, "ls": cmd_list, "edit": cmd_edit,
            "rm": cmd_rm, "remove": cmd_rm}
    try:
        if not argv:
            interactive()
        elif argv[0] in cmds:
            cmds[argv[0]](*argv[1:2])
        else:
            print(__doc__)
            return 1
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
