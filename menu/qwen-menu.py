#!/usr/bin/env python3
"""qwen-menu.py — lanzador TUI para Qwen3.6-35B + Pi + llama.cpp + laya.

Solo librería estándar (sin venv, sin rich). Dibuja en /dev/tty y escribe el
resultado en stdout como asignaciones de shell, listas para `eval`:

    ACTION=launch|mem|status|laya|quit
    MODEL_ID=base|heretic|iq3
    MODEL_PATH=/ruta/al/modelo.gguf
    OPT_EDIT=0|1  OPT_VISION=0|1  OPT_INCOGNITO=0|1  OPT_OLLAMA=0|1
    OPT_LAYA=0|1  OPT_KEV=0|1       (kev es un backend de laya: solo vale con laya activo)
    OPT_NOMODEL=0|1  OPT_CLAUDE=0|1  OPT_KEVGPU=0|1
                                    (sin modelo grande: MODEL_ID y MODEL_PATH vacíos)
    MMPROJ_PATH=/ruta/mmproj.gguf   (vacío si no hay visión)
    PI_ARGS='...'                   (argumentos extra para pi, ya entrecomillados)
    CLAUDE_DIR=/ruta/proyecto       (carpeta donde abrir Claude; tecla d / D)

Variables de entorno opcionales:
    QWEN_MODELS_DIR   directorio de modelos (~/models)
    QWENX_MODEL       sobreescribe la ruta del modelo Base
    QWENX_MMPROJ      sobreescribe la ruta del mmproj
    QWEN_PORT         puerto de llama-server (8001; el mismo que usa lib/config.sh)
    LAYA_PORT         puerto de laya (8765)
    KEV_PORT          puerto de kev.serve (8009)
"""

import sys

from qwen_menu.menu import Menu
from qwen_menu.term import Tty


def main():
    try:
        term = Tty()
    except OSError:
        sys.stdout.write("ACTION=quit\n")
        return 0
    try:
        with term:
            res = Menu(term).run()
    except KeyboardInterrupt:
        res = "ACTION=quit\n"
    sys.stdout.write(res)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
