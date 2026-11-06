# banco/ — medir modelos en la 3060

| Herramienta | Qué mide | Uso |
|---|---|---|
| `prueba_corta.py` | Calidad + razonamiento + velocidad: 6 tareas verificables (aritmética, trampa, fecha, acertijo, código con casos ocultos, instrucciones de forma), razonamiento activado, con el comando y perfil activo del menú | `python3 banco/prueba_corta.py [base heretic q38] [-n rondas]` |
| `bench.sh` | tok/s, aceptación MTP, VRAM y si aguanta con el **contexto lleno** | `banco/bench.sh TAG GGUF CTX KV UB [DRAFT]` |
| `perplejidad.sh` | Perplejidad sobre texto propio (vault + código). Compara cuantizaciones o KV del mismo modelo | `banco/perplejidad.sh GGUF [KV]` |

- Cerrar Qwen antes (`qwen-stop`): todas usan la GPU entera; la prueba usa el puerto 8077.
- `salida/` (logs, respuestas completas, texto de perplejidad) no se versiona; `resultados/` sí.
- `perplejidad.sh` necesita `llama-perplexity`: `cd ~/llama.cpp && cmake --build build --target llama-perplexity -j10`.
- Con temperatura > 0 una ronda es ruidosa: para decidir, `-n 3`.
