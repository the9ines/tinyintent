#!/bin/bash
set -euo pipefail

# Generate a 24-char alnum secret
NEW_SECRET=$(openssl rand -base64 32 | tr -d '+/=' | head -c 24)

PLIST_PATH="launchd/com.tinyintent.tinyrpc.plist"

# Check if plist exists
if [[ ! -f "$PLIST_PATH" ]]; then
    echo "Error: $PLIST_PATH not found" >&2
    exit 1
fi

# Set the new secret in the plist
/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:TINYINTENT_SECRET $NEW_SECRET" "$PLIST_PATH" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:TINYINTENT_SECRET string $NEW_SECRET" "$PLIST_PATH"

echo "New secret: $NEW_SECRET"

# Restart the bridge
echo "Restarting bridge..."
make bridge-stop 2>/dev/null || true
make bridge
make bridge-logs &
LOGS_PID=$!

# Wait a moment for the bridge to start
sleep 2

# Kill the background logs process
kill $LOGS_PID 2>/dev/null || true

# Print ready-to-copy curl example
echo ""
echo "Ready-to-copy curl test:"
echo "curl -sS -X POST http://127.0.0.1:8787/route \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -H \"X-TinyIntent-Secret: $NEW_SECRET\" \\"
echo "  -d '{\"text\":\"test message\",\"route\":\"local_only\"}'"