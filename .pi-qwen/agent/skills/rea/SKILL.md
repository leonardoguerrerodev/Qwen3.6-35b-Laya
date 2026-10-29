---
name: rea
description: >-
  Protocolo para analizar con el CLI `rea` (ingeniería inversa estática) un artefacto que el usuario nombra con su ruta: app JavaScript/Electron, sitio o bundle web, ensamblado .NET, binario Go o Rust, recursos PE. Usar cuando el mensaje pida "analiza con rea", "/rea", "qué hace este binario/dll/app/asar", "qué dependencias trae" o "ingeniería inversa de <ruta>". No usar para leer código fuente que ya tienes en el repo, ni para ejecutar el artefacto, ni para decompilar binarios nativos (no hay motor instalado).
---

# REA — protocolo

Eres el **recolector de evidencia**. Reúnes hechos y los etiquetas; **no concluyes por tu cuenta**. Claude audita tu `hallazgos.md`.
Solo analizas la ruta que el usuario te dio. Sin ruta, pídela y detente.

## Las 5 reglas (no las razones, aplícalas)

1. **Nunca imprimas el JSON completo.** Pesa de 100 KB a 15 MB y revienta tu contexto. Siempre:
   ```
   mkdir -p rea-out
   rea <comando> <ruta> --format json 2>/dev/null > rea-out/NN-nombre.json
   ```
   (`NN` = 01, 02… ; `2>/dev/null` quita el ruido de progreso). Luego lo miras **solo** con `jq ... | head -40`. Jamás `read` ni `cat` sobre `rea-out/`.
2. **Una llamada a `rea` por vez, y después apuntas.** Tras cada llamada, añade 1–3 líneas a `hallazgos.md` antes de la siguiente.
3. **Tope: 8 llamadas a `rea` por tarea.** Si llegas a 8, o si 3 seguidas no añaden un hecho nuevo: deja de consultar y reporta.
4. **Solo estos comandos** (no ejecutan el blanco): `analyze-javascript-application`, `inspect-artifact`, `inspect-managed-artifact`, `inspect-managed-members`, `inspect-go-binary`, `inspect-rust-binary`, `inspect-pe-resources`. **Prohibidos**: todo lo que empiece con `capture-`, `observe-`, `instrument-`, `debug-`, `start-`, `install-`, `push-`, `setup`, y cualquier `adb`. Ejecutan el programa o tocan dispositivos.
5. **Etiqueta cada línea de `hallazgos.md`** con esta prueba, sin pensarlo más:
   - `[O]` si el valor lo **copiaste tal cual** de la salida (un número, un nombre, una versión). Escríbelo entre comillas invertidas.
   - `[I]` si **agregaste una palabra tuya** (oficial, probablemente, desarrollo, para reducir tamaño…). Una línea `[I]` siempre cita el `[O]` en que se apoya.
   - `[D]` si no se pudo saber (motor ausente, cobertura parcial, límite).
   Análisis estático **nunca** prueba lo que pasa al ejecutar: no escribas "hace X cuando corre", escribe "contiene código que X" `[O]`.
   No expliques el *porqué* de un valor (por qué un flag, por qué una versión) si la salida no lo dice: eso es adivinar.

## Ruteo (mira el tipo y sigue la fila; no improvises)

| El blanco es… | Skill | Primer comando |
|---|---|---|
| Carpeta o `.asar` con JS / HTML (app Electron, sitio, PWA) | `rea-js` | `analyze-javascript-application` |
| `.dll` / `.exe` de .NET | `rea-artefactos` | `inspect-managed-artifact` |
| Binario ELF/PE (¿Go? ¿Rust?) | `rea-artefactos` | `inspect-go-binary`, luego `inspect-rust-binary` |
| Paquete / carpeta mixta sin saber qué es | `rea-artefactos` | `inspect-artifact` |
| Binario nativo C/C++ para leer su código | — | **No se puede** (falta Ghidra). Responde `[D]` y dilo. |

Carga la skill de la fila con `read` antes de seguir. Si no sabes el tipo: `file <ruta>` y vuelve a la tabla.

## Salida final

Cuando termines (o llegues al tope), responde **exactamente** esto (sin tablas, sin resumen extra) y detente:

```
REA LISTO
Blanco: <ruta> · Llamadas a rea: <n>/8 (cuenta los comandos que empiezan con `rea `) · Archivo: hallazgos.md
Observado: <2-4 puntos [O] más importantes>
Desconocido: <lo que no se pudo saber [D]>
```

Si algo falló dos veces seguidas con el mismo error: `REA BLOQUEADO` + la línea de error clave + qué probaste.

## Gotchas

- Rutas **relativas** para `rea-out/` y `hallazgos.md` (las absolutas largas se te corrompen). El blanco sí va con la ruta que dio el usuario, copiada tal cual y entre comillas simples si tiene `!` o espacios.
- Primera llamada sobre carpetas grandes: puede tardar. Es normal hasta 5 min; no la repitas.
- `analysis_profile: null` y `coverage: partial` son lo normal en estático: anótalo como `[D]` una sola vez, no lo repitas.
