#!/bin/bash
# Rotate TinyIntent API secret
# Updates environment and configuration files

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Generate new secret
NEW_SECRET=$(openssl rand -hex 32)

echo "🔑 Rotating TinyIntent API secret..."

# Update launchd configuration
LAUNCHD_FILE="$PROJECT_ROOT/launchd/com.tinyintent.tinyrpc.sample.plist"
if [[ -f "$LAUNCHD_FILE" ]]; then
    sed -i '' "s/REPLACE_WITH_ACTUAL_SECRET/$NEW_SECRET/g" "$LAUNCHD_FILE"
    echo "✅ Updated launchd configuration"
fi

# Update environment file if it exists
ENV_FILE="$PROJECT_ROOT/.env"
if [[ -f "$ENV_FILE" ]]; then
    sed -i '' "s/TINYINTENT_SECRET=.*/TINYINTENT_SECRET=$NEW_SECRET/" "$ENV_FILE"
else
    echo "TINYINTENT_SECRET=$NEW_SECRET" > "$ENV_FILE"
fi
echo "✅ Updated .env file"

# Show the new secret
echo ""
echo "🔐 New TinyIntent secret: $NEW_SECRET"
echo ""
echo "⚠️  Make sure to:"
echo "   1. Update your shell environment: export TINYINTENT_SECRET=$NEW_SECRET"
echo "   2. Restart the bridge service if running"
echo "   3. Update any client configurations"