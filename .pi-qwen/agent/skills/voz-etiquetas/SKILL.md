---
name: voz-etiquetas
description: Escribe las respuestas habladas con etiquetas de audio no verbal entre corchetes ([sigh], [laughing], [pause], [whisper]...) para que la voz Fish Audio S2 Pro las interprete como suspiros, risas, pausas o susurros. Usar cuando el usuario pida responder con voz expresiva, con emociones, con etiquetas de audio, "habla con sentimiento", "modo voz", "audio tags", "expressive voice" o "/skill:voz-etiquetas". No usar al escribir código, archivos, comandos ni salidas técnicas.
---

# Voz con etiquetas (Fish Audio S2 Pro)

Tu respuesta se convierte en audio con S2 Pro. Las etiquetas entre corchetes no se leen:
se interpretan como sonidos o como cambios de tono en el punto exacto donde las pones.

## Procedimiento

1. Escribe la respuesta en español neutro, en frases cortas y habladas. Sin markdown: nada de
   `#`, `**`, listas con guiones, tablas ni emojis (la voz los lee o los ignora mal).
2. Elige **de 1 a 3 etiquetas** según el tono real de lo que dices. Si el contenido es neutro,
   usa solo pausas o ninguna etiqueta.
3. Pon cada etiqueta **justo antes** de la palabra o frase que afecta, o sola donde ocurre el
   sonido: `[sigh] Bueno, lo reviso.` · `Listo. [laughing] Por fin.`
4. Revisa antes de responder (bucle obligatorio):
   - ¿Todas las etiquetas están en la tabla de abajo, en inglés y minúsculas? Si no, cámbiala por la más cercana de la tabla.
   - ¿Hay más de 3, o dos seguidas iguales? Quita hasta dejar como máximo 3.
   - ¿Alguna quedó dentro de código, un comando, una ruta o un archivo? Sácala.
   - ¿Queda algo de markdown? Pásalo a texto hablado.
   Si corregiste algo, vuelve a revisar desde el principio.

## Etiquetas (usa solo estas)

| Para… | Etiqueta |
| --- | --- |
| Pausa | `[pause]` · `[short pause]` |
| Respiración | `[inhale]` · `[exhale]` · `[sigh]` · `[panting]` |
| Risa | `[laughing]` · `[chuckle]` · `[chuckling]` · `[laughing tone]` |
| Volumen y tono | `[whisper]` · `[low voice]` · `[volume up]` · `[volume down]` · `[emphasis]` |
| Emoción | `[excited]` · `[delight]` · `[sad]` · `[surprised]` · `[shocked]` · `[angry]` |
| Otros sonidos | `[moaning]` · `[tsk]` · `[clearing throat]` |

## Ejemplos

- Buena noticia: `[excited] ¡Funcionó a la primera! [laughing] No lo esperaba.`
- Algo pesado: `[sigh] Hay tres errores más. [short pause] Vamos por partes.`
- Algo confidencial: `Te cuento algo. [whisper] El token sigue en el chat.`
- Respuesta neutra: `El archivo pesa cinco megas. [pause] ¿Lo descargo?`

## Gotchas

- Si la tarea implica herramientas (`write`, `edit`, `bash`), los archivos y comandos van
  **sin etiquetas**; solo lleva etiquetas el texto final que le dices al usuario.
- Usa las etiquetas siempre, sea cual sea el motor de voz: con S2 Pro se convierten en sonidos;
  con Piper o Kokoro el servidor de voz las quita antes de leer, así que no se pronuncian.
- No inventes etiquetas en español (`[suspiro]`, `[risa]`): S2 Pro está entrenado con las de la tabla.
- Los números y siglas suenan mejor escritos como se dicen: "cuatro coma dos", no "4,2".
