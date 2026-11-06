---
name: svg-png
type: domain-knowledge
topic: SVG a PNG o PDF (rsvg-convert)
token_cost: 130
# svg y rsvg-convert van dos veces a propósito: basta con nombrarlos para llegar al umbral 2.
keywords: [svg, svg, svgs, svgs, rsvg-convert, rsvg-convert, png, figura, figuras, diagrama, diagramas, inkscape]
requires_tools: [bash]
user-invocable: false
---
SVG a PNG: `rsvg-convert -w 1200 -o salida.png entrada.svg` (-w o -h fijan el tamaño; `-b white` quita la transparencia). SVG a PDF: `rsvg-convert -f pdf -o salida.pdf entrada.svg`.
Varias: `for f in *.svg; do rsvg-convert -w 1200 -o "${f%.svg}.png" "$f"; done`.
Comprueba con `file salida.png` (muestra el tamaño) o `pdfinfo salida.pdf`. Si `rsvg-convert` no existe (código 127), dilo y pide instalar librsvg2-tools; no lo cambies por otra herramienta sin avisar.
