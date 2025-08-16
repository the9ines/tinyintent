#!/usr/bin/env bash
set -euo pipefail
curl -sS http://127.0.0.1:8787/healthz | python3 -c 'import sys,json; print(json.load(sys.stdin)["status"])' | grep -q ok
echo "health ok"
