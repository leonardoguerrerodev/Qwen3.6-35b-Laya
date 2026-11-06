---
name: presentaciones
type: domain-knowledge
topic: Presentaciones PPTX (pandoc)
token_cost: 150
# ppt, pptx, powerpoint y diapositivas van dos veces a propósito: basta con nombrarlos para llegar al umbral 2. «una presentación» es frase (vale 2); «la presentación de…» no, porque calza con «la presentación del menú».
keywords: [ppt, ppt, pptx, pptx, powerpoint, powerpoint, diapositivas, diapositivas, diapositiva, slides, pandoc, odp, una presentacion, una presentación, presentacion, presentación]
requires_tools: [bash]
user-invocable: false
---
Escribe Markdown y conviértelo: `pandoc f.md -o f.pptx`. Si `pandoc` no existe (código 127), dilo y pide instalarlo; no lo cambies por python-pptx sin avisar.
Formato: arriba `---` / `title: Título` / `---` (portada); cada diapositiva empieza con `## Título`; dentro, viñetas (`- `), tablas Markdown, imágenes `![](img.png)`. Notas del orador: `::: notes` … `:::`. Pocas líneas por diapositiva: lo que no cabe se sale de la página.
Plantilla propia (colores, fuentes): `--reference-doc plantilla.pptx`.
Comprueba: `soffice --headless -env:UserInstallation=file:///tmp/lo-qwen --convert-to pdf --outdir /tmp/qwen f.pptx` y `pdfinfo /tmp/qwen/f.pdf` (páginas = diapositivas, portada incluida).
