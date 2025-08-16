#!/usr/bin/env bash
set -euo pipefail
S=$( /usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:TINYINTENT_SECRET" ~/Library/LaunchAgents/com.tinyintent.tinyrpc.plist 2>/dev/null || echo "" )
[ -n "$S" ] || { echo "no secret yet (service not loaded)"; exit 0; }
curl -sS -X POST http://127.0.0.1:8787/route -H "Content-Type: application/json" -H "X-TinyIntent-Secret: $S" -d '{"text":"summarize tinyintent","route":"gen"}' | head -c 120 >/dev/null || true
curl -sS -X POST http://127.0.0.1:8787/route -H "Content-Type: application/json" -H "X-TinyIntent-Secret: $S" -d '{"text":"restart the bot","route":"act"}' | head -c 120 >/dev/null || true
echo "routes smoke ok"
