---
name: rea-artefactos
description: Recetas exactas de `rea` para inspeccionar sin ejecutar un ensamblado .NET (.dll/.exe), un binario Go o Rust (dependencias y versión del compilador), recursos PE (iconos, versión) o un paquete/carpeta de tipo desconocido. Usar solo cuando la skill `rea` te mandó aquí. No usar para apps JS/Electron ni para leer el código de binarios nativos C/C++.
---

# REA — artefactos (.NET, Go, Rust, PE, paquetes)

Reglas de salida y tope de llamadas: las de la skill `rea`. Aquí solo van las recetas. Siempre `--format json 2>/dev/null > rea-out/NN-x.json` y luego `jq`.

## .NET (`.dll` / `.exe` administrado)

**1. Identidad:** `rea inspect-managed-artifact '<RUTA>' --format json 2>/dev/null > rea-out/01-id.json`
```
jq '.normalized_result | {flags_cli:.pe.cli.flags, version_runtime:.pe.cli.runtime_version, clasificacion:.classification.status, familia:.classification.runtime_family, impl:.classification.implementation, arch:.classification.managed_architecture, bytes:.artifact.byte_length}' rea-out/01-id.json
```
`il-library` en flags = biblioteca; `ready_to_run_signature: true` = viene precompilada (R2R) y el IL sigue presente.

**2. Un tipo concreto** (exige el nombre **completo**, con espacio de nombres):
`rea inspect-managed-members '<RUTA>' --type Espacio.De.Nombres.Tipo --format json 2>/dev/null > rea-out/02-tipo.json`
| Quiero… | Comando |
|---|---|
| Cuántos métodos y strings | `jq -c '.normalized_result \| {tipos:(.types\|length), metodos:(.methods\|length)}' rea-out/02-tipo.json` |
| Nombres de métodos | `jq -r '.normalized_result.methods[] \| [.token,.name,.signature.parameter_count,.signature.return_type]\|@tsv' rea-out/02-tipo.json \| head -50` |
| Campos | `jq -r '.normalized_result.fields[].name' rea-out/02-tipo.json \| head -50` |
| Strings literales que cargan sus métodos | `jq -r '.normalized_result.user_strings.literals[].value' rea-out/02-tipo.json \| head -50` |
| A quién llama (aristas) | `jq -c '.normalized_result.call_edges[0:20][]' rea-out/02-tipo.json \| cut -c1-200` |

**¿No sabes el nombre del tipo?** Busca candidatos: `strings -n 5 '<RUTA>' \| grep -i '<palabra>' \| sort -u \| head -30`. Eso da nombres sueltos; el espacio de nombres lo ves en la documentación XML vecina si existe (`grep -o 'name="T:[A-Za-z0-9_.]*' <archivo>.xml \| cut -d: -f2 \| head -30`). Si `types` sale con largo 0, el nombre no existe: **no inventes**, prueba otro o repórtalo `[D]`.

**3. Dependencias nativas (P/Invoke):** `rea inspect-managed-native-boundaries '<RUTA>' --format json 2>/dev/null > rea-out/03-nat.json` y mira con `jq '.normalized_result' rea-out/03-nat.json \| head -60`.

## Go y Rust

```
rea inspect-go-binary '<RUTA>' --format json 2>/dev/null > rea-out/01-go.json
jq -r '.normalized_result.build_info.go_version' rea-out/01-go.json
jq -r '.normalized_result.build_info.module_text' rea-out/01-go.json | head -40      # path, mod y dep (módulos)
```
```
rea inspect-rust-binary '<RUTA>' --format json 2>/dev/null > rea-out/01-rs.json
jq '.normalized_result' rea-out/01-rs.json | head -50
```
Si el de Go dice que no hay build info, prueba el de Rust (y al revés). Ninguno de los dos presente = `[D]` ("no es Go ni Rust, o viene sin metadatos"). **Ausencia de metadatos no prueba que no sea Go/Rust.**

## Recursos PE (versión, iconos)

`rea inspect-pe-resources '<RUTA>' --format json 2>/dev/null > rea-out/01-pe.json` y luego `jq '.normalized_result' rea-out/01-pe.json | head -60`.

## Paquete o carpeta desconocida

`rea inspect-artifact '<RUTA>' --format json 2>/dev/null > rea-out/01-art.json` y luego `jq '.normalized_result' rea-out/01-art.json | head -60`. Fíate de los "next probes" que traiga, pero solo si caen en los comandos permitidos de la skill `rea`.

## Gotchas

- `inspect-managed-members` **sin** `--type` devuelve todo vacío: no es un error, es que falta el tipo.
- Un tipo grande (cientos de métodos) pesa varios MB: por eso siempre a archivo y `head`.
- En Go, `(devel)` en la línea `mod` es la versión del **módulo** (compilado sin etiqueta), no del compilador. La versión del compilador es solo `go_version`. Y `-X:nodwarf5` es un flag del compilador: cópialo, no expliques para qué sirve.
- Nombres de métodos tipo `get_X` / `set_X` son propiedades; `.ctor` es el constructor.
- No hay motor para leer el código de máquina de binarios nativos: si el archivo no es Go/Rust/.NET, responde `[D]`.
