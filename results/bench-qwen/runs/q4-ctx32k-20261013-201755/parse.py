import json, sys
try:
    d = json.load(open(sys.argv[1]))
    if isinstance(d, list):
        d = next((x for x in reversed(d) if isinstance(x, dict) and x.get("type") == "result"), {})
    api = round(float(d.get("duration_api_ms", 0)) / 1000, 1)
    print(api, d.get("num_turns", "?"), str(d.get("is_error", "?")).lower())
except Exception:
    print("?", "?", "sin-json")
