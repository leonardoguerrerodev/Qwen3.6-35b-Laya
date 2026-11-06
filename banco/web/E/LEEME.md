# Variante E: Qwen3.8 + Qwen Code + presupuesto de razonamiento

Landing page de «Grano Sur» hecha por el Qwen3.8-27B local **en un solo pedido**, sin ayuda ni retoques.
Corrida del 6-nov-2026, 01:20–01:42 (hora de Chile). Resultado: **página completa y funcional**. Diseño aprobado por Leo («increíble, se ve de buena calidad»).

Ver: abrir `index.html`, o en la red local:
`python3 -m http.server 8080 --bind 0.0.0.0 --directory <esta carpeta>` → `http://192.168.0.4:8080`

## El pedido (prompt exacto)

> Crea una landing page de una cafetería ficticia llamada «Grano Sur»: cabecera con navegación, hero con llamado a la acción, menú de productos (al menos 9, con nombre, descripción corta y precio en pesos chilenos) filtrable por categoría (café, té, pastelería) con JavaScript, sección de horario y ubicación, pie de página, botón de modo oscuro que se recuerde con localStorage, y diseño responsive que se vea bien en celular y en escritorio. Archivos: index.html, styles.css y app.js, sin librerías ni CDNs. Cuida el diseño: tipografía, paleta coherente, espaciado y detalles.

Una sola llamada. Sin etapas, sin "continúa" y sin AGENTS.md/QWEN.md propio.

## Configuración

**Modelo:** `Qwen3.8-27B-GSQ-RCO-IQ3_XXS-mtp.gguf` (perfil `punto-dulce` de q38), RTX 3060 12 GB, monitor en la iGPU.

**Servidor** (comando del menú + las dos flags nuevas al final):
```
llama-server -m Qwen3.8-27B-GSQ-RCO-IQ3_XXS-mtp.gguf --alias qwen3.6-35b --host 127.0.0.1 --port 8001
  -ngl 99 -c 49152 -b 2048 -ub 256 -fa on -ctk q4_0 -ctv q4_0 --load-mode none --jinja
  --temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.0
  --spec-type draft-mtp --spec-draft-n-max 2 -np 1 -cram 2048
  --reasoning-budget 6000
  --reasoning-budget-message "Basta de planear: crea o edita el archivo ahora con la herramienta y mejóralo después."
```

**Harness:** Qwen Code 0.26.8 (`qcode`), config de `~/.qwen/settings.json` (proveedor openai → `:8001`).
```
qwen "Crea <pedido>" --approval-mode auto-edit -o stream-json --openai-logging
```
`auto-edit` aprueba solo editar archivos; el shell queda denegado. Script: `../correr_qcode.sh q38 6000`.

## Línea de tiempo

| Hora | Qué pasó |
|---|---|
| 01:20 | parte; consulta lateral de memoria de Qwen Code (46 tokens) |
| 01:20–01:27 | **turno 1:** piensa ~6000 tokens (diseña todo en la cabeza). El servidor corta el razonamiento e inyecta el mensaje → escribe `index.html` |
| 01:31 | **turno 2:** piensa 497 caracteres → escribe `styles.css` |
| 01:32 | **turno 3:** piensa 113 caracteres → escribe `app.js` |
| 01:36–01:38 | **turno 4:** verifica con `grep_search` que los ids y `data-filter`/`data-cat` del JS existan en el HTML; escribe el resumen final |
| 01:38–01:42 | Qwen Code corre su subagente `auto-memory-extractor` (4375 tokens, ~4 min) para guardar memorias en `~/.qwen/projects/…` |

**Página lista: 12 min** (último archivo a las 01:32). **Tarea cerrada: 18 min.** **Proceso completo: 22,5 min** (1350 s), incluida la memoria.

## Estadísticas (log del servidor)

| Llamada | Prompt (tok) | Generados (tok) | tok/s | MTP aceptación |
|---|---|---|---|---|
| memoria (lateral) | 749 | 46 | 38,9 | 100 % |
| turno 1 → index.html | 12 492 | 12 034 | 30,6 | 77 % |
| turno 2 → styles.css | 12 277* | 6 617 | 31,7 | 90 % |
| turno 3 → app.js | 87* | 1 773 | 30,9 | 90 % |
| turno 4 → verificación | 863* | 6 401 | 26,5 | 74 % |
| lateral | 19 612 | 357 | 29,5 | 81 % |
| resumen final | 26 288 | 668 | 25,7 | 69 % |
| subagente de memoria | 29 060 | 4 375 | 25,4 | 64 % |

\* tokens nuevos; el resto venía de la caché de prompt.

- **Total generado: 32 271 tokens**; la tarea en sí (sin memoria) ~27 900.
- **Lectura del prompt:** 400–480 tok/s. **Generación:** 25–32 tok/s (baja a medida que crece el contexto).
- **Contexto máximo usado:** ~40 500 de 49 152.
- Herramientas: `write_file` ×3, `grep_search` ×2. Cero errores de herramienta y cero reescrituras.

## Resultado

| Archivo | Líneas | Contenido |
|---|---|---|
| `index.html` | 370 | cabecera sticky con logo SVG, hero con taza SVG y vapor animado, 14 productos (6 café · 4 té · 4 pastelería) en CLP, horario con «Abierto/Cerrado» en vivo, ubicación con mini-mapa SVG, footer |
| `styles.css` | 709 | paleta crema/espresso/terracota con variables, `[data-theme="dark"]`, serif del sistema para títulos y sans para el cuerpo, tarjetas con hover, 3→2→1 columnas, hamburguesa < 640 px, `prefers-reduced-motion` |
| `app.js` | 173 | tema en localStorage (`grano-sur-theme`) con fallback a `prefers-color-scheme` y try/catch, `aria-pressed`, filtro con contador y estado vacío, menú móvil, estado de apertura según la hora, año dinámico |

Verificado: `node --check app.js` OK; los 9 ids que usa el JS existen; las categorías del filtro coinciden con las tarjetas.

## Por qué funcionó: la comparación

Mismo modelo, mismo pedido y mismo servidor. Lo único que cambia es el harness y el tope:

| Variante | Harness | Tope | Resultado |
|---|---|---|---|
| A (7500) | Pi | `maxTokens` 7500, sin presupuesto | **0 archivos.** Piensa 22k caracteres y se corta antes de escribir |
| A (12288) | Pi | `maxTokens` 12288, sin presupuesto | **0 archivos.** Piensa 37k caracteres en 1 turno y se corta |
| B etapa 1 | Pi, por etapas | 12288 | base de 3 archivos OK; se detuvo (en la corrida con 7500 la etapa 2 también se cortó) |
| **E** | **Qwen Code** | **`--reasoning-budget 6000` + mensaje** | **página completa en 1 pedido** |

**Diagnóstico.** El Qwen3.8 diseña la página entera dentro del razonamiento antes de usar una herramienta. Con un tope por respuesta (`maxTokens` = ctx/4 en el launcher), ese plan se corta antes del primer `write` y no queda nada. Subir el tope no lo arregla: el modelo piensa más. El presupuesto de razonamiento corta **solo el pensamiento** y obliga a actuar. Basta una vez: con el primer archivo escrito, los turnos siguientes piensan menos de 600 caracteres.

**Qwen Code frente a Pi.** Qwen Code manda `max_tokens` igual al contexto libre (no corta por su cuenta), ofrece 29 herramientas y el modelo las usa con naturalidad. Costos propios: una consulta de memoria al inicio y un subagente extractor de memoria al final (~4 min).

## Aplicado después (6-nov-2026)

- `--reasoning-budget` + mensaje en los perfiles `punto-dulce` (6000) y `q38s` (4000; su tope es 7500). Respaldo: `.qwen-data/profiles.json.bak-budget-20261106`.
- Regla «base primero, mejora con edit» en `~/.pi-qwen/agent/AGENTS.md` (bloque del kit de oficio) y en `~/.qwen/QWEN.md`.
- Memoria automática de qcode apagada (`memory.enableManagedAutoMemory/AutoDream: false`).
- El launcher escribe el contexto real en el settings de qcode al lanzar (`_qwen_code_prepare`).
- Menú: agente `qwen-code-web` (`qwen serve`, http://127.0.0.1:4170). Con `edit`, qcode corre en `auto-edit`.
- Incógnito con qwen-code: `QWEN_HOME` temporal en `/run/user` + `--chat-recording false`. Medido: no queda nada en `$HOME` y la carpeta se borra al salir. Con qwen-code-web no está disponible.

Logs completos: `../logs/E/` (`qcode.jsonl`, `api/` con cada request/response) y `../servidor-E.log`.
