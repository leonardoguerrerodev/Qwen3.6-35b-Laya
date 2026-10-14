#!/usr/bin/env bash
# bench-qwen.sh — benchmark de programación agéntica para Qwen local (Claude Code en modo no interactivo)
#
# Uso:
#   ./bench-qwen.sh <ollama|llama> <etiqueta>
#   ej:  ./bench-qwen.sh ollama base-ollama
#        ./bench-qwen.sh llama q4-n30-ub2048
#
# Qué hace (usa la MISMA config que `qwen` / `qwenx`, vía ~/.qwen-local.sh):
#   1. Arranca el motor y mide cuánto tarda en cargar el modelo.
#   2. Crea un proyecto de prueba nuevo (validador de RUT chileno con tests) en <repo>/results/bench-qwen/runs/.
#   3. Etapa 1 (en frío): Qwen debe implementar rut.py hasta que pasen los tests.
#   4. Etapa 2 (en caliente, misma sesión): aparecen tests extra y debe ampliar rut.py.
#   5. Verifica los tests por su cuenta (no se fía de lo que diga el modelo) y que no tocó los tests.
#   6. Mide tiempo total, turnos, VRAM máxima y RAM disponible mínima; añade una fila al CSV.
#
# Variables opcionales:
#   STAGE_TIMEOUT=900   segundos máximos por etapa
#   BENCH_DIR=ruta      dónde guardar corridas y resultados.csv (por defecto <repo>/results/bench-qwen)
#   FORCE=1             seguir aunque haya VRAM ocupada antes de arrancar llama.cpp
#
# Antes de medir con `llama`: sudo systemctl stop ollama (si no, la VRAM sale falseada).
# Cierra apps pesadas: la RAM libre cuenta para el umbral.
#
# Versión: 1.1 (2026-10-14): rutas relativas al repo (este script vive en <repo>/scripts/); antes usaba ~/bench-qwen.
# NOTA: los flags de `claude -p` (--output-format json, --max-turns, --allowedTools) no se han
#       probado en tu máquina todavía; si alguno falla, mira etapaN.err en la carpeta de la corrida.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

ENGINE="${1:-}"
LABEL="${2:-}"
if { [ "$ENGINE" != ollama ] && [ "$ENGINE" != llama ]; } || [ -z "$LABEL" ]; then
  echo "Uso: $0 <ollama|llama> <etiqueta>"
  echo "  ej: $0 ollama base-ollama"
  exit 1
fi
[ -f "$HOME/.qwen-local.sh" ] || { echo "Falta ~/.qwen-local.sh: ejecuta: bash $REPO_DIR/setup/qwen-setup.sh (v5 o superior)"; exit 1; }
# shellcheck disable=SC1091
source "$HOME/.qwen-local.sh"
declare -F _qwen_up >/dev/null || { echo "Tu ~/.qwen-local.sh es antiguo: vuelve a ejecutar: bash $REPO_DIR/setup/qwen-setup.sh (v5 o superior)"; exit 1; }
export -f _qwen_claude

if [ "$ENGINE" = ollama ]; then UP=_qwen_up; DOWN=_qwen_down; else UP=_qwenx_up; DOWN=_qwenx_down; fi

STAGE_TIMEOUT="${STAGE_TIMEOUT:-900}"
ALLOWED="Read,Write,Edit,Bash(python3:*),Bash(ls:*),Bash(cat:*)"
BASE="${BENCH_DIR:-$REPO_DIR/results/bench-qwen}"
RUN="$BASE/runs/$LABEL-$(date +%Y%m%d-%H%M%S)"
CSV="$BASE/resultados.csv"
PROJ="$RUN/proyecto"
mkdir -p "$PROJ" "$RUN/extra"
[ -f "$CSV" ] || echo "fecha,etiqueta,etapa,wall_s,api_s,turnos,error,tests,tests_intactos,vram_max_mb,ram_disp_min_mb,carga_s" > "$CSV"

now()     { date +%s.%N; }
elapsed() { awk -v a="$1" -v b="$(now)" 'BEGIN{printf "%.1f", b-a}'; }
vram_used() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' '; }

# --- Comprobación previa de VRAM (solo llama.cpp) ---------------------------------
if [ "$ENGINE" = llama ] && [ "${FORCE:-0}" != 1 ]; then
  u="$(vram_used)"
  if [ "${u:-0}" -gt 2000 ] 2>/dev/null; then
    echo "Hay ${u} MiB de VRAM en uso (¿Ollama con el modelo cargado?)."
    echo "Libérala con: sudo systemctl stop ollama   (o ejecuta con FORCE=1 para ignorarlo)"
    exit 1
  fi
fi

# --- Proyecto de prueba -------------------------------------------------------------
cat > "$PROJ/CLAUDE.md" <<'EOF'
# Proyecto de prueba
- Python 3, solo biblioteca estándar.
- Tests: `python3 -m unittest -v`.
- Responde en español, breve.
EOF

cat > "$PROJ/test_rut.py" <<'EOF'
import unittest
from rut import limpiar_rut, calcular_dv, validar_rut, formatear_rut


class TestLimpiar(unittest.TestCase):
    def test_quita_puntos_y_guion(self):
        self.assertEqual(limpiar_rut("12.345.678-5"), "123456785")

    def test_k_minuscula_y_espacios(self):
        self.assertEqual(limpiar_rut(" 16666666-k "), "16666666K")

    def test_vacio(self):
        self.assertEqual(limpiar_rut(""), "")


class TestDV(unittest.TestCase):
    def test_casos_normales(self):
        self.assertEqual(calcular_dv(12345678), "5")
        self.assertEqual(calcular_dv(11111111), "1")
        self.assertEqual(calcular_dv(7777777), "6")

    def test_k_y_cero(self):
        self.assertEqual(calcular_dv(16666666), "K")
        self.assertEqual(calcular_dv(6), "K")
        self.assertEqual(calcular_dv(1000013), "0")

    def test_acepta_texto(self):
        self.assertEqual(calcular_dv("12345678"), "5")


class TestValidar(unittest.TestCase):
    def test_validos(self):
        self.assertTrue(validar_rut("12.345.678-5"))
        self.assertTrue(validar_rut("12345678-5"))
        self.assertTrue(validar_rut("18.972.631-7"))
        self.assertTrue(validar_rut("16.666.666-k"))
        self.assertTrue(validar_rut("1-9"))

    def test_invalidos(self):
        self.assertFalse(validar_rut("12.345.678-9"))
        self.assertFalse(validar_rut(""))
        self.assertFalse(validar_rut("abc"))
        self.assertFalse(validar_rut("5"))


class TestFormatear(unittest.TestCase):
    def test_con_puntos_y_guion(self):
        self.assertEqual(formatear_rut("123456785"), "12.345.678-5")
        self.assertEqual(formatear_rut("12345678-5"), "12.345.678-5")

    def test_cuerpo_corto_y_k(self):
        self.assertEqual(formatear_rut("19"), "1-9")
        self.assertEqual(formatear_rut("16666666k"), "16.666.666-K")


if __name__ == "__main__":
    unittest.main()
EOF

# Tests de la etapa 2: se copian al proyecto después de la etapa 1
cat > "$RUN/extra/test_rut_extra.py" <<'EOF'
import unittest
from rut import generar_rut, rut_a_tupla


class TestExtra(unittest.TestCase):
    def test_generar_rut(self):
        self.assertEqual(generar_rut(12345678), "12.345.678-5")
        self.assertEqual(generar_rut(6), "6-K")

    def test_rut_a_tupla(self):
        self.assertEqual(rut_a_tupla("12.345.678-5"), (12345678, "5"))
        self.assertEqual(rut_a_tupla("16.666.666-k"), (16666666, "K"))

    def test_rut_a_tupla_invalido(self):
        with self.assertRaises(ValueError):
            rut_a_tupla("12.345.678-9")


if __name__ == "__main__":
    unittest.main()
EOF

# Lector del JSON de `claude -p` (tolera objeto o lista de eventos)
cat > "$RUN/parse.py" <<'EOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    if isinstance(d, list):
        d = next((x for x in reversed(d) if isinstance(x, dict) and x.get("type") == "result"), {})
    api = round(float(d.get("duration_api_ms", 0)) / 1000, 1)
    print(api, d.get("num_turns", "?"), str(d.get("is_error", "?")).lower())
except Exception:
    print("?", "?", "sin-json")
EOF

PROMPT1='Lee test_rut.py e implementa rut.py (validador de RUT chileno) para que todos los tests pasen. No modifiques test_rut.py ni uses librerías externas. Ejecuta `python3 -m unittest -v` y corrige hasta que pasen. Al terminar responde en máximo 3 líneas qué hiciste.'
PROMPT2='Apareció test_rut_extra.py con funciones nuevas (generar_rut y rut_a_tupla). Impleméntalas en rut.py sin romper lo anterior, ejecuta todos los tests con `python3 -m unittest -v` y responde en 2 líneas.'

# --- Muestreo de VRAM y RAM mientras corre ------------------------------------------
SAMPLER=""
sampler() {
  while :; do
    vram_used >> "$RUN/vram.log"
    free -m | awk '/^Mem:/{print $7}' >> "$RUN/ram_disp.log"
    sleep 2
  done
}
cleanup() {
  [ -n "$SAMPLER" ] && kill "$SAMPLER" 2>/dev/null
  $DOWN
}
trap cleanup EXIT
trap 'exit 130' INT TERM

# --- Arranque del motor ---------------------------------------------------------------
echo "== Motor: $ENGINE | etiqueta: $LABEL"
echo "== Carpeta de la corrida: $RUN"
echo "== Arrancando el motor y cargando el modelo..."
: > "$RUN/vram.log"; : > "$RUN/ram_disp.log"
sampler & SAMPLER=$!
T_LOAD=$(now)
$UP || { echo "No se pudo arrancar el motor"; exit 1; }
if [ "$ENGINE" = ollama ]; then
  # espera real a que el modelo esté cargado (la precarga de _qwen_up es asíncrona)
  curl -s "$QWEN_URL/api/generate" -d "{\"model\":\"$QWEN_MODEL\",\"keep_alive\":\"30m\"}" >/dev/null 2>&1
fi
CARGA="$(elapsed "$T_LOAD")"
echo "== Modelo cargado en ${CARGA}s"

# --- Etapas ------------------------------------------------------------------------------
declare -a RESUMEN=()

run_stage() {   # run_stage <n> <prompt> [flags extra de claude, p. ej. -c]
  local n="$1" prompt="$2"; shift 2
  local out="$RUN/etapa$n.json" err="$RUN/etapa$n.err"
  local v0 r0 h0 h1 t0 wall api turns errf rc nt estado intactos vmax rmin

  v0=$(wc -l < "$RUN/vram.log"); r0=$(wc -l < "$RUN/ram_disp.log")
  h0=$(sha256sum "$PROJ/test_rut.py" | cut -d' ' -f1)
  echo; echo "== Etapa $n en curso (máx. ${STAGE_TIMEOUT}s)..."
  t0=$(now)
  ( cd "$PROJ" && timeout "$STAGE_TIMEOUT" bash -c '_qwen_claude "$@"' _ \
      "$QWEN_URL" "$QWEN_TOKEN" "$QWEN_MODEL" "$@" \
      -p "$prompt" --output-format json --permission-mode acceptEdits \
      --allowedTools "$ALLOWED" --max-turns 30 ) > "$out" 2> "$err"
  rc=$?
  wall="$(elapsed "$t0")"
  read -r api turns errf < <(python3 "$RUN/parse.py" "$out")
  [ "$rc" -eq 124 ] && errf="timeout"

  ( cd "$PROJ" && python3 -m unittest > "$RUN/tests$n.txt" 2>&1 ); rc=$?
  nt=$(grep -E '^Ran [0-9]+ test' "$RUN/tests$n.txt" | awk '{print $2}')
  if [ "$rc" -eq 0 ]; then estado="OK(${nt:-?})"; else estado="FALLAN"; fi
  h1=$(sha256sum "$PROJ/test_rut.py" | cut -d' ' -f1)
  if [ "$h0" = "$h1" ]; then intactos="si"; else intactos="NO"; fi

  vmax=$(tail -n +$((v0 + 1)) "$RUN/vram.log" | sort -n | tail -1)
  rmin=$(tail -n +$((r0 + 1)) "$RUN/ram_disp.log" | sort -n | head -1)
  vmax="${vmax:-?}"; rmin="${rmin:-?}"

  echo "$(date +%F_%T),$LABEL,$n,$wall,$api,$turns,$errf,$estado,$intactos,$vmax,$rmin,$CARGA" >> "$CSV"
  RESUMEN+=("$(printf 'Etapa %s | total %6ss | API %6ss | turnos %-3s | error %-8s | tests %-10s | tests intactos %-3s | VRAM máx %s MiB | RAM disp. mín %s MiB' \
      "$n" "$wall" "$api" "$turns" "$errf" "$estado" "$intactos" "$vmax" "$rmin")")
  echo "   -> ${RESUMEN[-1]}"
}

run_stage 1 "$PROMPT1"
cp "$RUN/extra/test_rut_extra.py" "$PROJ/"
run_stage 2 "$PROMPT2" -c

# --- Resumen ------------------------------------------------------------------------------
[ "$ENGINE" = llama ] && cp /tmp/llama-server.log "$RUN/llama-server.log" 2>/dev/null

echo
echo "================ RESUMEN: $LABEL ($ENGINE) ================"
echo "Carga del modelo: ${CARGA}s"
for l in "${RESUMEN[@]}"; do echo "$l"; done
echo
echo "Umbrales del plan: VRAM <= ~11500 MiB y RAM disponible >= 4096 MiB (la velocidad se mira abajo)."
if [ "$ENGINE" = llama ] && [ -f "$RUN/llama-server.log" ]; then
  echo
  echo "-- Velocidades que registró llama-server (últimas líneas; el formato puede variar) --"
  grep -E 'tokens per second' "$RUN/llama-server.log" | tail -n 6 || true
fi
echo
echo "Resultados acumulados: $CSV"
echo "Detalle de esta corrida: $RUN"
