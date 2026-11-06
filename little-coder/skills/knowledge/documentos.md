---
name: documentos
type: domain-knowledge
topic: Documentos PDF y DOCX
token_cost: 150
# pdf, docx y odt van dos veces a propósito: cada aparición suma 1 y el umbral es 2, así basta con nombrarlos.
keywords: [pdf, pdf, pdfs, pdfs, docx, docx, odt, odt, word, libreoffice, soffice, pdftotext, pdfinfo, documento, informe, convierte, convertir, exporta, exportar]
requires_tools: [bash]
user-invocable: false
---
Leer PDF: `pdfinfo f.pdf` (páginas) y `pdftotext -layout f.pdf -` (un rango: `-f 2 -l 4`). Si sale vacío es escaneado: dilo, no inventes el contenido.
Leer DOCX u ODT: `mkdir -p /tmp/qwen && soffice --headless -env:UserInstallation=file:///tmp/lo-qwen --convert-to txt:Text --outdir /tmp/qwen f.docx` y lee `/tmp/qwen/f.txt`.
Crear DOCX o PDF: escribe HTML simple (h1, p, b, ul, table, img) con `write` y conviértelo:
`soffice --headless -env:UserInstallation=file:///tmp/lo-qwen --convert-to docx:"MS Word 2007 XML" --outdir <dir> f.html`
Para PDF usa `--convert-to pdf` (desde .html o .docx). El `-env` evita que falle callado si LibreOffice está abierto.
Desde Markdown también sirve `pandoc f.md -o f.docx`.
Comprueba con `ls -la <dir>` y `pdftotext <dir>/f.pdf - | head`. No instales python-docx ni otras librerías.
