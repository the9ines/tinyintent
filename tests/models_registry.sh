#!/usr/bin/env bash
set -euo pipefail
S=$( /usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:TINYINTENT_SECRET" ~/Library/LaunchAgents/com.tinyintent.tinyrpc.plist 2>/dev/null || echo "" )
[ -n "$S" ] || { echo "no secret yet (service not loaded)"; exit 0; }
orig="models.yaml.bak.$(date +%s)"
cp models.yaml "$orig"
cat > models.yaml <<'YAML'
roles:
  small:  test-small:1b
  medium: test-medium:7b
  large:  test-large:13b
YAML
curl -sS -X POST http://127.0.0.1:8787/admin/reload-models -H "X-TinyIntent-Secret: $S" | grep -q '"effective_roles"'
mv "$orig" models.yaml
echo "models registry hot-reload ok"
