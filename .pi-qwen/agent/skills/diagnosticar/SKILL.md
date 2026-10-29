---
name: diagnosticar
description: Encuentra la causa raíz de un fallo con evidencia antes de tocar el código. Reproduce el error con el programa real, revisa el entorno (intérprete, paquetes instalados frente a lo que importa el código, duplicados, versiones), localiza la línea, prueba una hipótesis por vez y verifica el arreglo con la misma reproducción. Usar ante error, traza, excepción, crash, segfault, «Violación de segmento», cuelgue, ImportError, «no funciona», «no arranca», «antes andaba», bug, traceback, regression. No usar para escribir funcionalidades nuevas ni para revisar código que no falla.
---

# Diagnosticar

**No edites código hasta tener dos cosas:** una reproducción que falla y la línea (o la capa) donde se rompe. Un arreglo sin eso es una apuesta.
Si el usuario pidió solo responder, sin ejecutar: no corras nada. Dale los comandos de los pasos 2 y 3 y pídele la salida.

## 1. Captura
Copia literal el error y el comando que lo produce. Si el usuario solo dice "no funciona", pídele el comando exacto y la salida completa (una sola pregunta) y detente.

## 2. Reproduce con el programa real
| Caso | Comando |
|---|---|
| Python | `./venv/bin/python -u -X faulthandler <entrada>.py` (sin venv: `python3 -u -X faulthandler …`) |
| pygame o ventana | `SDL_VIDEODRIVER=dummy timeout 15 ./venv/bin/python -u -X faulthandler <juego>.py; echo "exit=$?"` |
| Node | `node --test test/*.test.js` · `node <script>.js` |
| bash | `bash -x <script>.sh 2>&1 \| tail -40` |

- Esa receta es la prueba del arreglo: anótala.
- Si no se reproduce, dilo y pide el dato que falta. No arregles a ciegas.

## 3. Entorno, antes de sospechar de tu código
**Obligatorio** si hay segfault (139), un cuelgue dentro de una librería, `ImportError` o import circular, "antes andaba", o si la traza termina en `site-packages` o `node_modules`. Si no, haz solo a y b.

a. Intérprete que corre: `./venv/bin/python -c "import sys; print(sys.executable, sys.version)"`
b. Lo que importa el código: `grep -rhoE '^\s*(import|from)\s+[A-Za-z_]\w*' --include='*.py' --exclude-dir=venv --exclude-dir=.venv . | awk '{print $2}' | sort -u`
c. Lo instalado y si está sano: `./venv/bin/python -m pip list` · `./venv/bin/python -m pip check`
d. Dos paquetes que dan el mismo módulo (se rompe en C, sin aviso):
   `./venv/bin/python -c "import importlib.metadata as m; d={k:sorted(set(v)) for k,v in m.packages_distributions().items() if len(set(v))>1}; print(d or 'sin duplicados')"`
   Típicos: `pygame` + `pygame-ce` · `opencv-python` + `-headless` o `-contrib` · `PIL` + `Pillow` · `jwt` + `PyJWT` · `serial` + `pyserial`.
e. Qué archivo se carga de verdad: `./venv/bin/python -c "import X; print(X.__file__, getattr(X, '__version__', '?'))"`
f. Node: `node -v` · `npm ls 2>&1 | grep -E 'invalid|missing|extraneous|ERR'`

Un problema aquí explica el fallo hasta que se demuestre lo contrario: arregla el entorno primero. Para instalar o quitar paquetes, propón el comando y pide permiso.

## 4. Localiza
- Lee la traza de abajo hacia arriba: la primera línea que es de tu código es donde mirar.
- Donde explota no siempre es donde se rompe: sigue el valor malo hacia atrás.
- Sin traza: imprime con `flush=True` en las fronteras (entrada, tu función, la llamada a la librería) y mira dónde lo válido se vuelve inválido.

## 5. Hipótesis, de a una
Escribe esta tabla en tu respuesta y complétala:

| # | Hipótesis | Si es cierta, veré… | Prueba (UN cambio) | Resultado literal | Veredicto |

- La prueba más barata, primero. Un solo cambio por prueba. Nunca repitas una hipótesis descartada.
- **Sala limpia:** el mismo código en un entorno nuevo con lo mínimo (`python3 -m venv /tmp/qwen-limpio && /tmp/qwen-limpio/bin/python -m pip install <dep>`) y la receta del paso 2. Si ahí funciona, la causa es el entorno.
- **Un mini-script aparte que pasa no descarta nada:** el fallo se confirma o se descarta en el programa real.
- Con tres hipótesis descartadas seguidas, para. Vuelve al paso 3 o reporta ABIERTO con lo observado.

## 6. Arregla y verifica
- Arreglo mínimo, en el origen. Antes, busca quién más llama a lo que vas a tocar: `grep -rn "<función>(" .`
- Quita los prints de debug.
- La receta del paso 2 ahora da una señal positiva, y la suite (o la compilación) del proyecto sigue en verde.

## Reporte
```
DIAGNÓSTICO: CERRADO | ABIERTO
Síntoma: <literal>
Causa: <qué y dónde> · Evidencia: `<comando>` → `<salida>`
Arreglo: <archivo:línea, o el comando de entorno que propones>
Verificación: `<receta del paso 2>` → `<salida>`
Descartado: <hipótesis — por qué, una línea cada una>
```

## Caso real (octubre de 2026)
Síntoma: "Violación de segmento" al dibujar en un juego de pygame. **Mal:** reescribir el archivo por intuición (quitar `border_radius`, precrear superficies), probar con mini-scripts que pasaban y concluir "muere antes de imprimir" porque los `print` sin `-u` se perdieron. **Bien:** `-u -X faulthandler` → `font.render` en la línea 60 → paso 3d: `pygame` y `pygame-ce` instalados juntos → venv limpio con solo `pygame-ce` → funciona. El código no tenía nada.

## Gotchas
- Un proceso que muere (segfault) pierde los `print` que no se vaciaron: usa `python -u`. Que no veas un print no prueba que no se ejecutó.
- `pip install` dentro de un `run.sh`, o con `2>/dev/null`, reinstala encima en silencio y esconde el error.
- Si `pip install` dice "Building wheel" o "sdl2-config: not found", no hay wheel para ese Python. Busca la variante con wheel (p. ej. `pygame-ce`) y desinstala la otra.
- Usa `./venv/bin/python -m pip`, no `pip` suelto: puede ser el de otro Python.
