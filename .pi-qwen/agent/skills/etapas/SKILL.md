---
name: etapas
description: >-
  Ejecuta una tarea de código dividida en etapas numeradas (archivo tareas/NNN-*.md), una etapa por vez, verificando cada una y deteniéndose a esperar "continua". Usar cuando el mensaje pida trabajar una tarea o tarjeta por etapas, "haz la etapa N", "continua: etapa N", "/sigue N", "work stage by stage", "next stage". No usar para diseñar, opinar sobre el juego, refactorizar por iniciativa propia ni para tareas sin archivo de tarea.
---

# Etapas

Eres quien escribe el código. El diseño ya está decidido en la tarea: no inventes ni cambies nada que la tarea no pida.

## Procedimiento (una etapa)

1. **Ubica la etapa N.** Si el mensaje dice `etapa N`, `continua: etapa N` o `/sigue N`, esa es N. Si dice solo `continua`, N = la siguiente a la última que reportaste.
2. **Ten la tarea a mano.** Si en esta sesión todavía no leíste el archivo de la tarea, léelo completo una vez. Si ya lo leíste y todavía ves la etapa N completa en tu contexto, no lo vuelvas a leer. Si la conversación se resumió (compactación) y ya no la ves palabra por palabra, léelo de nuevo.
3. **Lee la etapa N palabra por palabra.** Anota para ti: archivos que toca, nombres exactos (funciones, exports, mensajes de error, colores, números) y cómo se verifica.
4. **Edita con cuidado.**
   - Antes de editar un archivo que ya existe, léelo (`read`), salvo que lo hayas escrito o leído en esta misma sesión y no haya cambiado desde entonces.
   - En `edit`, copia el texto viejo **exacto** de lo que leíste.
   - Si un `edit` falla: vuelve a leer el archivo y reintenta una vez. Si falla de nuevo y el archivo tiene menos de 150 líneas, reescríbelo completo con `write` conservando todo lo demás. Si es más largo, responde `ETAPA N BLOQUEADA`.
5. **Escribe solo lo que pide la etapa N.** Nada de etapas siguientes, aunque sea fácil o "ya que estás". Si para cumplir la etapa N es imprescindible corregir algo de una etapa anterior, hazlo y dilo en el reporte.
6. **Verifica:**
   - Si la etapa trae un comando de verificación, ejecútalo tal cual.
   - Si no trae, usa el comando de tests de `AGENTS.md`. Si tampoco hay, según el archivo:

     | Tipo | Comando |
     |---|---|
     | JS | `node --check <archivo>` |
     | Python | `python3 -m py_compile <archivo>` (con venv: `./venv/bin/python -m py_compile <archivo>`) |
     | bash | `bash -n <archivo>` |
     | Programa que no termina (juego, GUI, servidor) | `timeout 10 <comando>; echo "exit=$?"` (pygame: antepón `SDL_VIDEODRIVER=dummy`). `exit=124` sin traza = no se cayó en 10 s |

   - Éxito = una línea de salida que puedes citar. `(no output)` o un código distinto de 0 no es éxito.
7. **Si la verificación falla:** copia la línea de error, ubica en la traza la primera línea de tu código y cambia **una** cosa que la explique; vuelve al paso 6. Si el fallo sale de una librería o del entorno (segfault, `ImportError`, cuelgue), sigue la skill `diagnosticar` antes de tocar código. **Máximo 3 vueltas.** A la tercera, responde `ETAPA N BLOQUEADA`.
8. **Reporta y detente:**

```
ETAPA N LISTA
<qué hiciste, en una frase> · Verificación: `<comando>` → `<línea literal de la salida, ej. "# pass 21">`
Hallazgos: <solo si viste algo fuera de esta etapa que no tocaste; si no, omite esta línea>
```

o, si no pudiste:

```
ETAPA N BLOQUEADA
<qué falla: la línea de error clave o la duda exacta> · Intenté: <qué probaste>
```

No escribas nada más. Espera `continua`.

## Reglas

- Archivos: solo los que la tarea permite. Nada de `package.json`, dependencias ni archivos auxiliares. No borres archivos que la tarea no pida borrar.
- Rutas **relativas** al directorio actual (`src/mundo.js`).
- Nombres, firmas y textos: **exactamente** como la tarea los escribe (mayúsculas, acentos y comillas incluidos).
- **No arranques procesos que no terminan**: servidores (`python3 -m http.server`, `npx serve`), `--watch` ni nada interactivo. Te quedas colgado. Si tienes que probar uno, siempre con `timeout` (paso 6). La prueba en el navegador la hace una persona.
- **git solo para mirar** (`git status`, `git diff`, `git log`). Nada que cambie el repo: ni `commit`, `checkout`, `reset` ni `stash`.
- Si la tarea es ambigua o contradictoria, no adivines: responde `ETAPA N BLOQUEADA` con la duda.

## Gotchas (observados en corridas reales)

- **Los datos de prueba son donde más fallas.** Al escribir tests con mapas pequeños, antes de cada `assert` cuenta las coordenadas a mano: fila = y, columna = x, desde 0. Comprueba que el mapa tiene lo que el test supone (el `@`, el muro justo en la casilla destino).
- Si un test falla, decide primero si el error está en el **código** o en el **test**. Relee la tarea: la tarea manda, no tu test.
- `continua` a secas no autoriza hacer varias etapas juntas: siempre es **una**.
- No repitas un comando que acaba de fallar sin cambiar algo antes.
- Rutas absolutas largas: se corrompen al copiarlas (ya pasó: `scratchpad` → `scratch-pad`). Usa la relativa.
- Node 22: `node --test test/` (la carpeta) falla con "Cannot find module". Usa `node --test test/*.test.js`.
- `pkill -f` o `pgrep -f` con un texto que también está en tu propio comando te matan a ti mismo (`exit 143`) y no sabrás si el programa funcionó. Usa `timeout`, o el PID: `<cmd> & pid=$!; …; kill $pid`.
- Si Python muere (segfault), se pierden los `print` que no se vaciaron: corre con `python3 -u`.
