---
name: revisar
description: Revisa código o un conjunto de cambios con evidencia. Compara lo pedido con el diff real, re-ejecuta las comprobaciones, busca tests debilitados, residuos y cambios fuera de alcance, y emite un veredicto con hallazgos confirmados y sospechosos. Usar al pedir «revisa», «audita», «review», «code review», «qué le falta» y antes de dar por terminado un cambio de varios archivos. No usar para escribir funcionalidades nuevas ni para depurar un error concreto (usar diagnosticar).
---

# Revisar

No creas: comprueba. Algo está bien porque lo re-ejecutaste y viste la señal, no porque alguien (o tú) lo diga.
Al revisar no arreglas: reportas. Arreglar es otra tarea, salvo que te lo pidan.

## Procedimiento
1. **Criterios:** lista lo que se pidió (en el mensaje, la tarjeta o el plan). Sin criterios claros, dilo y revisa solo bugs reales.
2. **Qué cambió de verdad:** `git status --short` y `git diff --stat`. Sin git: compara con la copia de `/tmp/qwen/` o lista los archivos tocados. Lee el diff, no tu memoria.
3. **Cruza:** cada cambio debe corresponder a un criterio; si no, es "fuera de alcance". Cada criterio debe tener un cambio; si no, es "omitido".
4. **Re-ejecuta tú** las comprobaciones (tests, compilación, la receta del fallo) y copia la salida. "Ya pasaba antes" no cuenta.
5. **Tests debilitados:** `git diff -- '*test*'` → asserts borrados o comentados, `skip`, números relajados para que pase. Cualquiera de ellos es BLOQUEANTE.
6. **Residuos en lo cambiado:**
   - `git diff | grep -nE '^\+.*(print\(|console\.log|debugger|TODO)'`
   - archivos temporales o `.bak`; procesos que quedaron vivos (`jobs`, `pgrep -a python`)
   - secretos en claro (tokens, claves)
7. **Código ajeno (review):** cada hallazgo es **Confirmado** (lo reprodujiste ejecutando algo) o **Sospechoso** (un patrón dudoso que no reprodujiste). No supongas precedencias ni lógica invertida: pruébalo con una línea (`python3 -c …`, `node -e …`).

## Veredicto (mecánico)
- **RECHAZADO:** algo esencial falla, hay un test debilitado o un cambio irreversible fuera de lo pedido.
- **CON HALLAZGOS:** lo esencial pasa; solo hay cosas menores.
- **APROBADO:** todo pasa y no hay hallazgos.
- **NO CONCLUYENTE:** no pudiste ejecutar algo; di qué y por qué.

## Formato
```
REVISIÓN: <veredicto> — <qué lo determinó, una frase>
| # | archivo:línea | severidad | esperado → encontrado (literal) | acción |
Comprobado: `<comando>` → `<salida literal>`
```
Severidad: BLOQUEANTE o MENOR. El estilo y los gustos no son hallazgos, salvo que se hayan pedido.
