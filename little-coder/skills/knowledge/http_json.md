---
name: http-json
type: domain-knowledge
topic: HTTP y JSON (curl, jq)
token_cost: 150
# curl y jq van dos veces a propósito: basta con nombrarlos para llegar al umbral 2.
keywords: [curl, curl, jq, jq, json, api, apis, endpoint, endpoints, https, headers, cors, webhook, wget]
requires_tools: [bash]
user-invocable: false
---
Pedido: `curl -sS --max-time 20 URL` (-sS: sin barra de progreso pero con errores). Código HTTP: `curl -sS -o /tmp/qwen/r.json -w '%{http_code}\n' URL`; un 4xx o 5xx no es éxito.
POST con JSON: `curl -sS -X POST -H 'Content-Type: application/json' -d '{"a":1}' URL`. Con token: `-H "Authorization: Bearer $TOKEN"`; nunca lo imprimas ni lo escribas en un archivo.
CORS (lo que ve el navegador): `curl -sS -i -X OPTIONS -H 'Origin: https://x' -H 'Access-Control-Request-Method: POST' URL` y busca `access-control-allow-origin`.
JSON con jq, no con python: `jq 'keys'` para ver la forma, `jq '.items[] | {id, name}' f.json`, `jq -r '.data[].url'`, `jq length`. Respuesta grande: `| jq . | head -50`.
