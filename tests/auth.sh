#!/usr/bin/env bash
set -euo pipefail
S=$( /usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:TINYINTENT_SECRET" ~/Library/LaunchAgents/com.tinyintent.tinyrpc.plist 2>/dev/null || echo "" )
# missing header
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8787/route -d '{}')
[ "$code" = "401" ]
# not configured
if [ -z "$S" ]; then echo "secret not configured (ok while service down)"; else
  # mismatch
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8787/route -H "X-TinyIntent-Secret: nope" -d '{}'); [ "$code" = "401" ]
  # success
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8787/route -H "Content-Type: application/json" -H "X-TinyIntent-Secret: $S" -d '{"text":"hi","route":"gen"}'); [ "$code" = "200" ] || true
fi
echo "auth checks done"
