#!/usr/bin/env bash
# perplejidad.sh GGUF [KV] — perplejidad sobre texto propio (vault + código), 12 trozos de 2048 tokens. Menor = mejor.
# Sirve para comparar cuantizaciones o tipos de KV del MISMO modelo; entre modelos distintos es solo una pista.
# perplejidad.sh --solo-texto  → solo arma salida/texto.txt.
# Requiere llama-perplexity: cd ~/llama.cpp && cmake --build build --target llama-perplexity -j10
set -e
D="$(cd "$(dirname "$0")" && pwd)"; S="$D/salida"; O="$D/../.."; mkdir -p "$S"
if [ ! -s "$S/texto.txt" ]; then
  { cat "$O/!cerebronardo/Obsedium/Workflow Diario.md" "$O/!cerebronardo/Programacion/Programacion (Indice).md" 2>/dev/null
    find "$O/!cerebronardo/Programacion" -name '*.md' | sort | head -15 | xargs -d '\n' cat
    cat "$D/../lib/llama.sh"
    find "$O/QwenGame/src" -name '*.js' | sort | head -6 | xargs -d '\n' cat; } > "$S/texto.txt" 2>/dev/null
fi
[ "$1" = --solo-texto ] && exit 0
KV="${2:-q8_0}"; T="$(basename "$1" .gguf)-$KV"
~/llama.cpp/build/bin/llama-perplexity -m "$1" -f "$S/texto.txt" -c 2048 --chunks 12 -ngl 99 -fa on -ctk "$KV" -ctv "$KV" > "$S/ppl-$T.log" 2>&1
echo "$T: $(grep 'Final' "$S/ppl-$T.log" | sed 's/.*PPL/PPL/')"
