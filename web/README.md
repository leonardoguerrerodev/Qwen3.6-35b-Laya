# web — UI local para la LAN de casa

Página web para elegir la combinación del launcher de Qwen (modelo + opciones) y
prender los backends (`llama-server`/`laya`/`kev`/`voz`) desde cualquier
dispositivo conectado a la misma red de casa que Nobara — no solo desde su
terminal local.

## Qué hace (Fase 1)

- Replica el formulario del menú TUI (`menu/qwen-menu.py`), reusando las mismas
  tablas (`menu/qwen_menu/config.py`) y helpers (`menu/qwen_menu/system.py`) —
  nada está duplicado.
- "Lanzar" prende **solo los backends**, en segundo plano (headless): **no**
  invoca a `pi` ni a `claude`. El chat con Pi sigue siendo en la terminal local
  de Nobara, como siempre — esta web solo elige la combinación y prende los
  servicios.
- "Apagar todo" llama al mismo `stop_servers()` que ya usa `qwen-stop`.
- Quedan fuera del formulario las combinaciones que abren una ventana gráfica
  local (Claude en Konsole, Kev GPU, "Ninguno") — esas siguen siendo
  solo-terminal.

## Selector de carpeta

El campo "Carpeta de trabajo" navega el filesystem de **Nobara** (nunca el del
teléfono — no hay forma de que un navegador remoto lea carpetas del servidor
sin esto). Lista subcarpetas reales vía `/api/browse`, sin enjaular a `$HOME`
(mismo criterio de confianza-LAN que el resto de esta fase). Queda guardada en
el estado del menú (`cdir`) y es la carpeta donde corre Pi al adjuntarlo
(fase 2).

## Qué hace (Fase 2): adjuntar pi remotamente

Botón "→ abrir Pi" en el launcher → `/pi.html`: una terminal real (xterm.js,
vendorizado en `web/vendor/`, sin CDN) conectada por WebSocket a un pty que
corre `pi` en Nobara, contra el backend que ya prendió la Fase 1.

**Requiere un token** (a diferencia de la Fase 1): esto SÍ da una shell real
(las tools de pi, en modo edición, pueden ejecutar bash). `qwen-web` genera un
token nuevo al azar cada vez que arranca y lo imprime en la terminal — hay que
copiarlo a mano en el campo de la página web. Sin token no se abre ningún
proceso. Una sola sesión de Pi adjuntada a la vez.

Necesita el paquete `websockets` (venv perezoso en `$WEB_VENV`, se crea solo al
primer `qwen-web`); si no se puede preparar, esta parte queda deshabilitada y
el resto de la web sigue funcionando igual.

## Qué hace (Fase 3): escuchar la voz en la web

Cuadro de texto + botón "Hablar" en el launcher. `web_server.py` reenvía el
texto a `voz_server.py` (`127.0.0.1:$VOZ_PORT/hablar`, sin cambiar su bind: sigue
invisible fuera de esta máquina) y devuelve el PCM crudo al navegador; el JS
cliente le antepone una cabecera WAV mínima (usando el `X-Sample-Rate`
recibido) y lo reproduce con `Audio`/`Blob`, sin librerías nuevas.

Disparo manual únicamente — "Pi habla solo al terminar de responder" sigue
pendiente (Fase 2 del plan original de voz: qué evento de la Extension API de
Pi marca "respuesta terminada").

## Qué hace (Fase 5): Claude / Kev GPU / «Ninguno»

El formulario ya incluye el modelo "Ninguno" y las opciones Claude/Kev GPU
(iguales a las del menú TUI). A diferencia de todo lo demás en esta web, esto
**no se ve en el navegador**: abre una ventana de terminal en la pantalla
física de Nobora (`qwen-web` hereda el `$DISPLAY` de la sesión de escritorio
desde la que se arrancó). Kev/laya quedan en segundo plano hasta
`qwen-stop`/"Apagar todo" (variante headless de `_qwen_claude_split`, sin el
"Pulsa Enter para detener" de la TUI — acá no hay nadie leyendo ese stdin).

## Uso

```bash
qwen-web
# UI web de Qwen: http://<ip-lan-de-nobara>:8780/   (Ctrl+C para apagar)
# web: token para adjuntar pi: <token>
```

Desde cualquier otro dispositivo de la misma red de casa, abrir esa URL en el
navegador. Para adjuntar Pi, pegar el token impreso arriba en `/pi.html`.

## ⚠️ Sin autenticación (salvo adjuntar Pi)

Este es el primer servicio del repo que escucha en `0.0.0.0` en vez de
`127.0.0.1` — cualquier dispositivo de tu red de casa puede abrir la página y
prender/apagar los backends sin pedir nada. Es una decisión deliberada (red de
confianza, cero fricción); no lo expongas más allá de tu LAN (sin
port-forwarding, sin VPN que la extienda a terceros, etc.). La excepción es
adjuntar Pi (arriba): eso sí exige el token, porque da acceso a una shell real.

## Variables de entorno (`lib/config.sh`)

| Variable | Default | Qué hace |
|---|---|---|
| `WEB_PORT` | `8780` | Puerto HTTP del launcher |
| `WEB_WS_PORT` | `8781` | Puerto WebSocket para adjuntar Pi |
| `WEB_PI_TOKEN` | (al azar, por sesión) | Token para adjuntar Pi; fijalo si querés uno estable |
| `WEB_DIR` | `$QWEN_ROOT/web` | Carpeta de este subsistema |
| `WEB_VENV` | `$WEB_DIR/.venv` o `$QWEN_DATA/web-venv` | Venv con `websockets` |

## Independiente del ciclo de vida de Qwen

A diferencia de `laya`/`voz` (que son sub-servicios que arrancan *con* Qwen),
`web` es quien **dispara** el arranque de Qwen — se levanta manualmente, aparte,
y no se apaga solo cuando Qwen se apaga. Adjuntar Pi tampoco apaga los backends
al cerrar la terminal: siguen vivos hasta `qwen-stop`/"Apagar todo".

## Fases futuras (planificadas, no implementadas)

Ver el plan completo en el historial de la sesión que lo diseñó. Queda
pendiente: disparo automático de la voz al terminar la respuesta de Pi
(depende de la incógnita de la Extension API, ver arriba). La reutilización
de un backend ya precalentado (antes "Fase 4") y las combinaciones Claude/Kev
GPU (antes "Fase 5") ya están implementadas — ver `lib/llama.sh`
(`_qwen_free_port`) y las secciones de arriba.
