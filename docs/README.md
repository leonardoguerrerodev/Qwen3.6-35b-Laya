# Qwen3.6-35B-A3B local — Pi, llama.cpp, Laya y Kev

Entorno para ejecutar **Qwen3.6-35B-A3B en local** desde la terminal, usando [Pi](https://pi.dev/docs/latest/quickstart) como agente de programación y `llama.cpp` como servidor de inferencia. Incluye un menú TUI, perfiles de herramientas, selección de variantes GGUF y servicios opcionales de clasificación con Laya/Kev.

> **Importante:** este repositorio contiene scripts y configuración; no incluye los pesos GGUF ni compila `llama.cpp` por ti. Las funciones de Laya/Kev son experimentales y no deben tratarse como una barrera de seguridad.

## Qué incluye

- **Menú TUI (`qwen`)** para escoger modelo, permisos de herramientas y opciones de ejecución.
- **Pi + `llama-server`**, comunicados mediante la API compatible con OpenAI en `127.0.0.1:8001` por defecto.
- **Perfiles de Pi:** solo lectura o edición con `write`, `edit` y `bash`.
- **Variantes GGUF:** modelo base Q4_K_XL, variante Heretic Q4_K_M y alternativa ligera IQ3_XXS.
- **Visión opcional**, si se dispone del archivo `mmproj` compatible.
- **Ollama opcional** como backend alternativo.
- **Laya**, un clasificador local de prompts; puede usar su propio modelo o Kev como backend.
- **Integración opcional con Claude Code** mediante comandos y un hook de sesión para Laya/Kev.
- **Separación de configuración:** Pi usa `~/.pi-qwen/agent`, sin modificar `~/.pi/agent`. Esa carpeta y los skills globales (`~/.agents`) viven dentro del repo (`.pi-qwen/`, `.agents/`); en `~/` solo hay symlinks hacia ellos.
- **Privacidad por defecto:** el `.gitignore` es una lista blanca; credenciales, sesiones de Pi y configuración regenerable no se versionan (ver [Qué se versiona y qué no](#qué-se-versiona-y-qué-no)).

## Requisitos

Antes de instalar, prepara estos componentes:

- Linux con Bash y Python 3.
- `curl`.
- `git` (opcional; `--check` lo usa para avisar de archivos privados trackeados).
- [Pi](https://pi.dev/docs/latest/quickstart) instalado y disponible como `pi` en el `PATH`.
- `llama.cpp` compilado con un `llama-server` ejecutable. La ruta predeterminada es `~/llama.cpp/build/bin/llama-server`.
- Los modelos GGUF que vayas a usar dentro de `~/models` (ruta predeterminada).

Ollama y Claude Code son opcionales. Las opciones de Kev también son opcionales, pero requieren que su código y entorno virtual estén preparados; el instalador de este repo **no instala Kev**.

La memoria necesaria depende de la cuantización, la longitud de contexto, el reparto CPU/GPU y las aplicaciones abiertas. El tamaño del GGUF por sí solo no garantiza que el modelo vaya a caber en la memoria disponible.

## Instalación

Si todavía no has descargado el repositorio:

```bash
git clone https://github.com/leonardoguerrerodev/Qwen3.6-35b-Laya.git
cd Qwen3.6-35b-Laya
```

Ejecuta el instalador desde la raíz del repositorio:

```bash
./setup/qwen-setup.sh
source ~/.bashrc
qwen
```

El instalador deja el entorno listo y se puede repetir sin riesgo (es idempotente). En concreto:

- crea tres symlinks en `~/` que apuntan al repo: `~/.qwen-local.sh` → `qwen-local.sh`, `~/.pi-qwen` → `.pi-qwen/` y `~/.agents` → `.agents/` (configuración de Pi y skills globales; `~/.pi/agent` no se toca);
- si alguno de esos destinos ya existe como archivo o directorio **real**, lo mueve a `<ruta>.bak-<fecha>` antes de enlazar (no migra su contenido al repo); un symlink previo que apunte a otro lugar se reemplaza y su destino anterior queda en el log;
- crea `.pi-qwen/agent/` y `.agents/skills/` dentro del repo si faltan (un clon nuevo no los trae completos);
- deja el `auth.json` de Pi en permisos `600` si existe;
- genera/actualiza `models.json`, `settings.json` y `AGENTS.md` de Pi (a través del symlink, es decir, dentro del repo) y registra si cambiaron;
- añade a `~/.bashrc` una única línea para cargar los comandos;
- prepara el entorno virtual de Laya, salvo que se use `--no-laya`;
- comprueba las dependencias de Kev y muestra un aviso si falta su entorno, pero **no lo instala**.

Al terminar imprime una **lista de acciones** con su estado (`CREADO`, `ACTUALIZADO`, `SIN_CAMBIOS`, `RESPALDADO`, `ELIMINADO`, `AVISO`) y guarda toda la salida en `~/.cache/qwenx/setup-<fecha>-<pid>.log` (se conservan los 10 últimos; `QWEN_SETUP_LOG_DIR` cambia la carpeta).

Opciones del instalador:

```bash
./setup/qwen-setup.sh --check      # comprobar symlinks, sintaxis, estado de git y de Pi (no modifica nada)
./setup/qwen-setup.sh --no-laya    # instalar sin preparar el entorno virtual de Laya
./setup/qwen-setup.sh --uninstall  # retirar los tres symlinks y la línea de ~/.bashrc
```

`--uninstall` solo quita los symlinks que apuntan a este repo. No borra el repositorio: `.pi-qwen/` y `.agents/` siguen en él con todo su contenido, y los backups `.bak-<fecha>` tampoco se tocan.

### Archivos de modelo

Guarda los GGUF dentro de `~/models` o define `QWEN_MODELS_DIR`.

| Variante | Patrón de nombre que reconoce el lanzador | Uso previsto |
|---|---|---|
| Base | `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf` o `*Q4_K_XL*.gguf` | Uso general, prioriza calidad |
| Heretic | `*heretic*Q4_K_M*.gguf` | Variante Heretic/abliterada |
| IQ3 | `*IQ3_XXS*.gguf` | Alternativa más pequeña, con posible pérdida de calidad |
| Proyección de visión | `mmproj-*F16*.gguf` | Necesaria para activar la opción Visión |

El programa usa **un modelo a la vez**. IQ3 no está configurado como modelo borrador para decodificación especulativa.

## Qué se versiona y qué no

El `.gitignore` de `.pi-qwen/` y `.agents/` es una **lista blanca**: todo se ignora salvo lo que se declara expresamente. Así, lo que Pi genere más adelante queda fuera del repo por defecto.

| Ruta | ¿Se versiona? | Motivo |
|---|---|---|
| `.pi-qwen/agent/keybindings.json`, `extensions/`, `skills/`, `prompts/`, `themes/` | Sí | Configuración propia |
| `.agents/skills/` | Sí | Skills globales |
| `.pi-qwen/agent/auth.json` | No | Credenciales |
| `.pi-qwen/agent/sessions/` | No | Conversaciones completas y rutas locales |
| `.pi-qwen/agent/models.json`, `settings.json` | No | Los genera `lib/pi.sh` y se reescriben en cada arranque (contexto, compactación) |
| `.pi-qwen/agent/AGENTS.md` | No | Lo genera `lib/pi.sh` y contiene la ruta absoluta de tu HOME |
| `.pi-qwen/agent/bin/`, `npm/`, `models-store.json` | No | Binarios y cachés regenerables |

También se ignoran `*.log`, los GGUF y otros pesos, `.env*`, los backups (`*.bak*`, `*.zip`) y la metadata de escritorio (`.directory`).

No uses `git add -f` sobre rutas ignoradas. `./setup/qwen-setup.sh --check` avisa si hay archivos trackeados que el `.gitignore` ignora.

## Uso diario

### Comandos principales

| Comando | Resultado |
|---|---|
| `qwen` | Abre el menú con el modelo base |
| `qwen -p "resume este repo"` | Ejecuta Pi directamente con el modelo base |
| `qwen-edit -p "arregla este bug"` | Lanza el perfil de edición |
| `qwenh` | Abre el menú con Heretic preseleccionado |
| `qwenh-edit` | Heretic con el perfil de edición |
| `qwen-lite` | Abre el menú con IQ3 preseleccionado |
| `qwen-vision` | Abre el menú con Visión preseleccionada |
| `qwen-incognito` | Abre el menú sin guardar la sesión de Pi |
| `qwen-ollama` | Abre el menú para usar Ollama como backend alternativo |
| `qwen-claude` | Abre el menú en modo Claude/Kev, sin cargar el modelo Qwen grande |
| `qwen-status` | Comprueba rutas, modelos, puertos, Pi, Laya y Kev |
| `qwen-mem` | Muestra el uso de memoria de `llama-server` y del sistema |
| `qwen-stop` | Intenta detener `llama-server` en el puerto configurado y procesos que coincidan con los patrones de Laya/Kev |

Las variantes `qwenh-*` también incluyen `qwenh-incognito`, `qwenh-edit-incognito`, `qwenh-vision` y `qwenh-vision-incognito`.

Si un comando se ejecuta sin argumentos, abre el menú. Si le pasas argumentos, lanza Pi directamente con el preset correspondiente. Los comandos de visión necesitan un `mmproj` válido.

### Perfiles de herramientas

- **Solo lectura:** `read`, `grep`, `find`, `ls`.
- **Edición:** añade `write`, `edit` y `bash`.

> **Seguridad:** el perfil Edición permite modificar archivos y ejecutar comandos mediante `bash`. Úsalo únicamente en proyectos y directorios de confianza, y revisa las acciones antes de ejecutarlas. No equivale a un sandbox.

### Teclas del menú TUI

| Tecla | Acción |
|---|---|
| `↑` / `↓` o `k` / `j` | Mover el foco |
| `Espacio` | Seleccionar el elemento enfocado |
| `Enter` | Lanzar o confirmar la edición del campo activo |
| `1`–`3` | Elegir una variante de modelo |
| `e` | Activar/desactivar Edición |
| `v` | Activar/desactivar Visión |
| `i` | Activar/desactivar Incógnito |
| `o` | Usar Ollama |
| `s` | Activar/desactivar Laya |
| `y` | Elegir Kev como backend de Laya |
| `g` | Usar Kev en GPU en el modo compatible |
| `h` | Activar la opción Claude |
| `a` | Editar argumentos de Pi o el directorio de Claude, según el campo activo |
| `m` / `c` | Ver memoria / estado |
| `l` | Ejecutar Laya/Kev de forma independiente |
| `x` | Detener los servidores administrados por el menú |
| `r` | Actualizar el estado de modelos y puertos |
| `q` / `Esc` | Salir |

Las combinaciones incompatibles se ajustan automáticamente: por ejemplo, Claude y Kev GPU usan el modo sin modelo Qwen grande, porque compiten por recursos de GPU.

## Laya y Kev: estado real de la integración

Laya ofrece un servicio local en `127.0.0.1:8765` con dos endpoints:

- `GET /health`: informa de que el servicio está preparado.
- `POST /classify`: clasifica un texto por complejidad y devuelve puntuaciones relacionadas con solicitudes destructivas e intentos de *prompt injection*.

El backend predeterminado es Laya. La configuración permite seleccionar Kev (`LAYA_BACKEND=kev` o desde el menú). Con Qwen en ejecución, el backend Kev predeterminado usa `jaredpalmer/kev-0.8b`; para el modo Claude/Kev se configura `jaredpalmer/kev-4b`, con posibilidad de usar CPU o GPU según el comando y la disponibilidad.

**Limitación clave:** Pi todavía no consulta automáticamente el servicio de Laya. Cuando se ejecuta `qwen` o `qwenh`, Laya puede arrancar en paralelo, pero eso no significa que esté analizando ni bloqueando los prompts de Pi. La integración mediante hook está preparada para el flujo de Claude Code que usan los comandos `claude-kev*`.

Los umbrales y los datos de evaluación de Laya son experimentales. No uses sus puntuaciones como garantía de seguridad ni como sustituto de la revisión humana.

### Comandos Claude Code + Kev

Estos comandos requieren que Claude Code esté instalado y que el entorno de Kev esté preparado:

```bash
claude-kev          # Kev-4B; intenta CUDA y recurre a CPU si hace falta
claude-kev-cpu      # Kev-4B en CPU
claude-kev-08b      # Kev-0.8B, prioriza rapidez
```

Para el modo interactivo que permite escoger carpeta y opciones desde el menú, usa `qwen-claude`. El terminal nuevo usa `konsole` por defecto; la variable `QWEN_TERMINAL` permite indicar otro emulador compatible. El menú y los comandos dependen de que la orden `claude` esté disponible en el `PATH`.

### Preparar Kev (opcional)

El instalador de este repositorio no crea el entorno virtual de Kev. Si el código de Kev está presente en `kev/kev-repo`, prepara su entorno desde esa carpeta:

```bash
cd kev/kev-repo
uv sync --extra serve
```

Se requiere `uv` y, la primera vez que se use un modelo, puede ser necesaria una descarga. Comprueba el estado final con `qwen-status`.

## Ollama como alternativa

Ollama es una ruta de ejecución separada: no utiliza el GGUF seleccionado en el menú, sino el modelo configurado en `QWEN_OLLAMA_MODEL` (por defecto `qwen3.6:35b`) a través del endpoint local de Ollama. El servicio debe estar instalado, con el modelo descargado y respondiendo en la dirección indicada por `QWEN_OLLAMA_URL`.

## Configuración habitual

Todas estas variables son opcionales. Define una variable antes de lanzar el comando para sobrescribir el valor por defecto en esa ejecución.

| Variable | Predeterminado | Para qué sirve |
|---|---|---|
| `QWEN_LLAMA_BIN` | `~/llama.cpp/build/bin/llama-server` | Ruta de `llama-server` |
| `QWEN_MODELS_DIR` | `~/models` | Directorio de los GGUF |
| `QWEN_PORT` | `8001` | Puerto local de `llama-server` |
| `QWENX_CTX` | `120000` | Contexto solicitado a `llama-server` |
| `QWENX_NCMOE` | `28` | Valor de `--n-cpu-moe` |
| `QWENX_BATCH` / `QWENX_UB` | `2048` / `512` | Tamaño de batch y microbatch |
| `QWENX_CRAM` | `2048` | Valor de `-cram` |
| `QWENX_NOTHINK` | `0` | Con `1`, desactiva el modo thinking |
| `QWEN_PI_DIR` | `~/.pi-qwen/agent` | Directorio de configuración de Pi (por defecto resuelve, vía symlink, a `.pi-qwen/agent` del repo) |
| `QWEN_PI_TOOLS_RO` | `read,grep,find,ls` | Herramientas del perfil de solo lectura |
| `QWEN_PI_TOOLS_EDIT` | `read,write,edit,bash,grep,find,ls` | Herramientas del perfil de edición |
| `QWEN_PI_NO_SESSION` | `0` | Con `1`, Pi no guarda la sesión |
| `QWEN_SETUP_LOG_DIR` | `~/.cache/qwenx` | Carpeta donde `qwen-setup.sh` guarda su log |
| `QWEN_OLLAMA_URL` | `http://127.0.0.1:11434` | Dirección de Ollama |
| `QWEN_OLLAMA_MODEL` | `qwen3.6:35b` | Modelo que usa el backend Ollama |
| `QWEN_LAYA` | `1` | Con `0`, evita arrancar Laya junto con Qwen |
| `LAYA_BACKEND` | Configuración de `laya/config.json` | Backend de clasificación: `laya` o `kev` |
| `LAYA_PORT` | `8765` | Puerto del servicio Laya |
| `KEV_PORT` | `8009` | Puerto del servicio Kev |
| `KEV_LOG` | `~/.cache/qwenx/kev.log` | Archivo de salida del servidor Kev |

Para ver el resto de variables y sus valores por defecto, consulta [`lib/config.sh`](lib/config.sh). No cambies los parámetros de contexto, batch ni reparto CPU/GPU sin comprobar el efecto en la RAM, VRAM y estabilidad de tu equipo.

## Logs y privacidad

- La salida de `llama-server` se redirige y no se guarda como log persistente por defecto.
- El flujo de Ollama no crea logs persistentes desde estos scripts.
- Laya no guarda cada petición en un archivo y los scripts actuales descartan su salida al arrancarlo.
- **Kev sí tiene un archivo de log predeterminado:** `~/.cache/qwenx/kev.log`, configurable mediante `KEV_LOG`.
- Los servicios se enlazan a `127.0.0.1` por defecto; evita exponerlos a la red sin añadir autenticación y controles adecuados.
- **Pi guarda sesiones** (conversaciones completas y rutas locales) en `.pi-qwen/agent/sessions/`: dentro del repo, pero ignoradas por git. `qwen-incognito` o `QWEN_PI_NO_SESSION=1` evitan guardarlas.
- Las credenciales de Pi (`auth.json`) también viven en `.pi-qwen/agent/` y git las ignora; el instalador las deja en permisos `600`.
- El instalador guarda su propio log en `~/.cache/qwenx/setup-<fecha>-<pid>.log` (se conservan los 10 últimos).

## Estructura del repositorio

```text
qwen-local.sh           Punto de entrada y comandos del shell
lib/
  config.sh             Rutas, puertos y valores por defecto
  llama.sh              Ciclo de vida de llama.cpp y backend Ollama
  pi.sh                 Configuración y lanzamiento de Pi
  laya.sh               Ciclo de vida de Laya y Kev
  claude.sh             Integración de sesión con Claude Code
menu/
  qwen-menu.py          Entrada del menú TUI
  qwen_menu/            Módulos del menú
setup/
  qwen-setup.sh         Instalador / comprobación / desinstalación
laya/                   Servicio, configuración, hooks y pruebas de Laya
kev/kev-repo/           Código y entorno de Kev (opcional)
docs/                   Documentación del proyecto
scripts/                Scripts auxiliares
results/                Resultados y mediciones guardadas
.pi-qwen/agent/         Configuración de Pi (symlink ~/.pi-qwen); solo se versionan keybindings.json, extensions/, skills/, prompts/ y themes/
.agents/skills/         Skills globales de Pi (symlink ~/.agents)
```

## Solución de problemas

| Síntoma | Qué comprobar |
|---|---|
| El menú dice que no encuentra un modelo | Ejecuta `ls ~/models/*.gguf` y comprueba que el nombre coincide con los patrones de la tabla. Si usas otra carpeta, define `QWEN_MODELS_DIR`. |
| No encuentra `llama-server` | Comprueba `QWEN_LLAMA_BIN` y que el archivo existe y tiene permiso de ejecución. |
| El puerto `8001` está ocupado | Comprueba qué proceso lo usa o elige otro puerto con `QWEN_PORT`. |
| No encuentra el comando `pi` | Instala Pi o asegúrate de que su ejecutable esté en el `PATH`. |
| Visión no arranca | Añade un `mmproj-*F16*.gguf` compatible a la carpeta de modelos. |
| Laya no arranca | Ejecuta `./setup/qwen-setup.sh --check`; confirma que existe su venv y revisa `LAYA_PORT`. Qwen puede seguir funcionando sin Laya. |
| Las opciones Kev/Claude fallan | Comprueba que existe `kev/kev-repo/.venv/bin/python`, que el puerto `8009` está libre y que `claude`/el terminal están disponibles. |
| La memoria no se libera después de usar Qwen | Usa `qwen-stop` o la tecla `x` en el menú y vuelve a comprobar con `qwen-status`. Ten en cuenta que `qwen-stop` usa patrones de `pkill` para Laya/Kev; revisa que no tengas otra instancia de esos servicios que quieras mantener. |
| Pi usa una configuración inesperada | Revisa `QWEN_PI_DIR` y ejecuta `./setup/qwen-setup.sh --check`, que muestra el directorio real al que apunta. Esta configuración se separa deliberadamente de `~/.pi/agent`. |
| `--check` marca un symlink como **ROTO** | Apunta al repo y este no está accesible (por ejemplo, un disco externo desmontado). Monta el disco o vuelve a ejecutar el instalador desde el repo. |
| Ya tenía un `~/.pi-qwen` o `~/.agents` real | El instalador lo mueve a `<ruta>.bak-<fecha>` y enlaza al repo, pero **no migra** su contenido. Copia a mano lo que quieras conservar a `.pi-qwen/agent/` o `.agents/skills/`. |
| `--check` avisa de archivos trackeados que el `.gitignore` ignora | Sácalos del índice sin borrarlos del disco con `git rm --cached <ruta>`. |
| Quiero ver qué hizo el instalador | Revisa el log más reciente de `~/.cache/qwenx/setup-*.log` o la lista de acciones que imprime al final. |
| El menú se ve mal | Usa una terminal UTF-8 con soporte de colores; el ancho recomendado es de al menos unas 72 columnas. |

## Estado y limitaciones conocidas

- No se incluyen los pesos del modelo ni una compilación de `llama.cpp`.
- Kev no se instala automáticamente con `qwen-setup.sh`.
- Laya no está integrada como paso automático del flujo de prompts de Pi; que el servidor esté encendido no significa que esté interviniendo.
- Los resultados de clasificación de Laya/Kev, sus umbrales y el filtrado de prompts necesitan validación con pruebas representativas antes de usarse para tomar decisiones de seguridad.
- El comportamiento y el rendimiento dependen de la versión de `llama.cpp`, la cuantización elegida y los recursos de cada equipo.
- `.pi-qwen/` y `.agents/` viven en el repo: si este está en un disco externo, los symlinks de `~/` no funcionan mientras el disco no esté montado.
- Un clon nuevo solo trae lo versionado de Pi (`keybindings.json`, `extensions/`, `skills/`); `models.json`, `settings.json` y `AGENTS.md` los genera el instalador, y las credenciales y sesiones se crean localmente y no se suben.

## Diagnóstico rápido

Después de instalar o actualizar:

```bash
./setup/qwen-setup.sh --check
qwen-status
```

Para probar una sesión sencilla con el modelo base:

```bash
qwen -p "Resume la estructura de este repositorio"
```

Si falla el arranque por un error del template o del modo thinking, prueba como diagnóstico temporal:

```bash
QWENX_NOTHINK=1 qwen
```

Esto desactiva thinking para esa ejecución; no lo conviertas en un ajuste permanente sin comparar resultados.

---

**Proyecto comunitario y experimental.** Revisa los scripts antes de ejecutarlos y valida cada cambio en tu máquina antes de depender de él.
