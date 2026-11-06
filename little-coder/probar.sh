#!/usr/bin/env bash
# probar.sh — ¿little-coder funciona sobre el Pi de node_modules? Correr después de cambiar la versión de Pi
# (package.json → npm install --ignore-scripts). No usa la GPU: un servidor falso responde un guion fijo
# (ls · rm · read · edit con `edits` en texto con saltos crudos · fin) y se revisa qué hizo cada extensión.
set -u
D="$(cd "$(dirname "$0")" && pwd)"; T="$(mktemp -d)"; trap 'kill $FP 2>/dev/null; rm -rf "$T"' EXIT
mkdir -p "$T/home" "$T/agent" "$T/w" "$T/cap"; printf 'uno\ndos\n' > "$T/w/a.txt"
echo '{"enableInstallTelemetry": false, "quietStartup": true}' > "$T/agent/settings.json"
python3 -I - "$T" <<'PY' & FP=$!
import http.server, json, os, sys
T = sys.argv[1]; n = [0]
a = os.path.join(T, "w", "a.txt")
guion = [("bash", {"command": "ls"}), ("bash", {"command": "rm -f a.txt"}), ("read", {"path": a}),
         ("edit", {"path": a, "edits": '[{"oldText": "uno\ndos", "newText": "UNO\nDOS"}]'})]
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *x): pass
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
    def do_POST(self):
        b = self.rfile.read(int(self.headers["Content-Length"])); i = n[0]; n[0] += 1
        open(os.path.join(T, "cap", f"req{i}.json"), "wb").write(b)
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        if i < len(guion):
            t, arg = guion[i]
            d = {"role": "assistant", "tool_calls": [{"index": 0, "id": f"c{i}", "type": "function",
                 "function": {"name": t, "arguments": json.dumps(arg)}}]}; fr = "tool_calls"
        else: d = {"role": "assistant", "content": "listo"}; fr = "stop"
        for delta, f in ((d, None), ({}, fr)):
            c = {"id": "x", "object": "chat.completion.chunk", "created": 0, "model": "m",
                 "choices": [{"index": 0, "delta": delta, "finish_reason": f}]}
            if f: c["usage"] = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
            self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
open(os.path.join(T, "puerto"), "w").write(str(s.server_address[1])); s.serve_forever()
PY
for _ in $(seq 50); do [ -s "$T/puerto" ] && break; sleep 0.1; done
cat > "$T/models.json" <<J
{"providers": {"llamacpp": {"api": "openai-completions", "baseUrl": "http://127.0.0.1:$(cat "$T/puerto")/v1", "apiKey": "LLAMACPP_API_KEY",
 "models": [{"id": "m", "name": "m", "reasoning": false, "input": ["text"], "contextWindow": 32000, "maxTokens": 4000,
 "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}}}
J
( cd "$T/w" && HOME="$T/home" PI_CODING_AGENT_DIR="$T/agent" PI_OFFLINE=1 LITTLE_CODER_MODELS_FILE="$T/models.json" \
  LLAMACPP_API_KEY=local LITTLE_CODER_NO_CTX_PROBE=1 LITTLE_CODER_EXTENSIONS_DIR= \
  timeout 120 "$D/bin/little-coder.mjs" --no-session -p --mode json --model llamacpp/m hola </dev/null >"$T/out.jsonl" 2>"$T/err.txt" )
rc=$?
python3 -I - "$T" "$rc" "$(node -p "require('$D/node_modules/@earendil-works/pi-coding-agent/package.json').version")" <<'PY'
import json, os, sys
T, rc, ver = sys.argv[1], int(sys.argv[2]), sys.argv[3]
reqs = sorted(os.listdir(f"{T}/cap"), key=lambda f: int(f[3:-5]))
ult = json.load(open(f"{T}/cap/{reqs[-1]}")) if reqs else {"messages": [], "tools": []}
res = [m["content"] if isinstance(m["content"], str) else "".join(p.get("text", "") for p in m["content"])
       for m in ult["messages"] if m.get("role") == "tool"]
err = open(f"{T}/err.txt").read().strip()
ok = [("terminó sin error (rc 0)", rc == 0),
      ("stderr vacío", not err),
      ("5 pedidos al modelo (4 herramientas + cierre)", len(reqs) == 5),
      ("26 herramientas (las de little-coder)", len(ult.get("tools", [])) == 26),
      ("permission-gate bloqueó «rm»", len(res) > 1 and "is not in SAFE_PREFIXES" in res[1]),
      ("a.txt sigue existiendo", os.path.exists(f"{T}/w/a.txt")),
      ("edit-repair: el edit con saltos crudos se aplicó", open(f"{T}/w/a.txt").read() == "UNO\nDOS\n" if os.path.exists(f"{T}/w/a.txt") else False)]
print(f"little-coder sobre Pi {ver}")
for t, v in ok: print(("  OK    " if v else "  FALLA ") + t)
if err: print("stderr:", err[:800])
if not all(v for _, v in ok):
    for i, r in enumerate(res): print(f"  herramienta {i}: {r[:200]!r}")
sys.exit(0 if all(v for _, v in ok) else 1)
PY
