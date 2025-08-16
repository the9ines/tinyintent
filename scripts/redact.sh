#!/usr/bin/env bash
set -euo pipefail
in="data/episodes/events.ndjson"
out="data/episodes/events.redacted.ndjson"
[ -f "$in" ] || { echo "no $in"; exit 1; }
python3 - "$in" "$out" <<'PY'
import sys,json
i,o = sys.argv[1], sys.argv[2]
with open(i,"r",encoding="utf-8") as f, open(o,"w",encoding="utf-8") as g:
    for line in f:
        try:
            ev=json.loads(line)
            ev["text"] = "<redacted>"
            if ev.get("preview_json"):
                ev["preview_json"]="<redacted>"
            g.write(json.dumps(ev,ensure_ascii=False)+"\n")
        except Exception:
            pass
print(o)
PY
