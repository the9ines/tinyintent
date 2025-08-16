#!/usr/bin/env bash
# Print TinyIntent connection URLs and secret

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

cd "$PROJECT_ROOT"

PLIST_PATH="launchd/com.tinyintent.tinyrpc.plist"

if [[ ! -f "$PLIST_PATH" ]]; then
    echo "Error: Plist not found at $PLIST_PATH" >&2
    echo "Run: bash scripts/bootstrap_fresh.sh" >&2
    exit 1
fi

# Get secret from plist
SECRET=$(/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:TINYINTENT_SECRET" "$PLIST_PATH" 2>/dev/null || echo "")
if [[ -z "$SECRET" ]]; then
    echo "Error: TINYINTENT_SECRET not found in plist" >&2
    echo "Run: bash scripts/bootstrap_fresh.sh" >&2
    exit 1
fi

# Get port from plist or default
PORT=$(/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:TINYINTENT_PORT" "$PLIST_PATH" 2>/dev/null || echo "8787")

# Get network info
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "unknown")
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "")

echo "==========================================="
echo -e "${BLUE}TinyIntent Connection Information${NC}"
echo "==========================================="

echo
echo -e "${BLUE}Secret:${NC}"
echo "$SECRET"

echo
echo -e "${BLUE}URLs:${NC}"
echo "Localhost: http://127.0.0.1:$PORT"
echo "LAN:       http://$LAN_IP:$PORT"
if [[ -n "$TAILSCALE_IP" ]]; then
    echo "Tailscale: http://$TAILSCALE_IP:$PORT"
fi

echo
echo -e "${BLUE}iPhone Shortcut Setup:${NC}"
echo "URL: http://$LAN_IP:$PORT/route"
echo "Header: X-TinyIntent-Secret"
echo "Value: $SECRET"
echo "Body: {\"text\":\"[DICTATED_TEXT]\",\"route\":\"auto\"}"

echo
echo -e "${BLUE}Quick Test:${NC}"
echo "echo \"summarize tinyintent\" | bin/ti -r auto --json"

echo "==========================================="