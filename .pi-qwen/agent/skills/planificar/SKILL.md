---
name: planificar
description: >-
  Arma un plan corto y verificable antes de programar una tarea nueva sin tarjeta. Lee lo que se toca, fija el objetivo y lo que queda fuera, comprueba los supuestos con comandos, resuelve ambigüedades chicas y elige librería o enfoque con criterios. Usar cuando la tarea tiene 3 o más pasos o toca más de un archivo, cuando el pedido es ambiguo o al elegir entre librerías o enfoques: «implementa», «agrega», «crea», «refactoriza», «plan», «build», «add feature». No usar si hay un archivo tareas/NNN-*.md (usar etapas) ni para arreglar un fallo (usar diagnosticar).
---

# Planificar

El plan es corto, va en tu respuesta y cada paso se puede comprobar con un comando. Primero entiendes, después escribes el plan y recién entonces ejecutas.

## Antes del plan
1. **Lee lo que vas a tocar y quién lo usa:** `grep -rn "<nombre>" --include='*.<ext>' .` Lista los archivos.
2. **Copia la forma de la casa:** busca cómo resuelve el proyecto algo parecido (nombres, estructura, tests) y hazlo igual.
3. **Supuestos:** todo hecho del que dependes y no viste (que existe una función, una versión, un formato, que una librería está instalada) se comprueba con un comando **antes** de usarlo. Ese es el paso 0.
4. **Ambigüedad:**
   - Si cambia **qué** se construye: haz una pregunta con tu opción por defecto, y espera.
   - Si no: elige lo más chico y reversible, y anótalo en Decisiones.
5. **Elegir librería o enfoque** (solo si hace falta):
   - Primero lo que ya hay: stdlib, dependencias instaladas, código del proyecto. "No agregar nada" también es una opción.
   - Criterios antes que opciones: que encaje con el proyecto, cuánto cuesta sacarlo después, que funcione en este Python o Node (compruébalo, no lo recuerdes).
   - Para una dependencia nueva, consulta antes.

## Formato (en tu respuesta)
```
PLAN: <título>
Objetivo: <qué existe al terminar> · Fuera: <lo que no harás>
Decisiones: <duda → elección (por qué)>
0. Supuestos → `<comando>` = <lo que esperas>
1. <archivo>: <cambio> → ✔ `<comando>` = <señal>
2. …
N. Integral: `<tests / compilación>` = <señal> · lo que ya andaba sigue andando: `<comando>`
```

## Revisa el plan antes de empezar
- ¿Cada paso tiene un ✔ que puedes ejecutar ahora?
- ¿Cada supuesto se comprueba antes de usarse?
- ¿Hay algo que no se pidió? Pásalo a "Fuera".
- ¿Los nombres (funciones, archivos, claves) son iguales en todos los pasos?

Si algo falla, corrige el plan y vuelve a revisarlo.

## Ejecuta
- Un paso por vez: cambio → ✔ → siguiente. No adelantes pasos.
- Si el plan tiene más de 6 pasos, guárdalo también en `.qwen-plan.md` (si el contexto se compacta, ahí está) y bórralo al cerrar.
- ✔ en rojo: aplica `diagnosticar` en corto (reproduce, localiza, una hipótesis, un cambio). Máximo 3 vueltas por paso; después reporta BLOQUEADO con la línea de error.
- Si un supuesto resultó falso, dilo y reescribe solo los pasos que dependían de él.
- Si encuentras algo fuera del plan (un bug vecino, una mejora), anótalo en `Hallazgos:` del reporte y no lo toques.
- Al final: compuerta de cierre y reporte de `AGENTS.md`.
