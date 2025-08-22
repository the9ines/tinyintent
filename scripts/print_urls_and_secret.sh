#!/bin/bash
# Print TinyIntent URLs and current secret
# Useful for development and debugging

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🌉 TinyIntent Bridge Information"
echo "==============================="

# Check if bridge is running
if curl -s http://localhost:8787/readyz >/dev/null 2>&1; then
    echo "Status: ✅ Bridge is running"
else
    echo "Status: ❌ Bridge is not running"
fi

echo ""
echo "📡 Bridge URLs:"
echo "   Health:     http://localhost:8787/readyz"
echo "   Route:      http://localhost:8787/route"
echo "   Feedback:   http://localhost:8787/feedback"
echo "   Admin:      http://localhost:8787/admin/reload-helpers"

echo ""
echo "🔐 Authentication:"
if [[ -n "${TINYINTENT_SECRET:-}" ]]; then
    echo "   Secret:     $TINYINTENT_SECRET"
    echo "   Header:     X-TinyIntent-Secret: $TINYINTENT_SECRET"
else
    echo "   ⚠️  TINYINTENT_SECRET not set in environment"
    
    # Check .env file
    ENV_FILE="$PROJECT_ROOT/.env"
    if [[ -f "$ENV_FILE" ]] && grep -q "TINYINTENT_SECRET" "$ENV_FILE"; then
        SECRET=$(grep "TINYINTENT_SECRET" "$ENV_FILE" | cut -d'=' -f2)
        echo "   Found in .env: $SECRET"
        echo "   Run: source .env"
    fi
fi

echo ""
echo "🧪 Test the bridge:"
echo "   curl -H \"X-TinyIntent-Secret: \$TINYINTENT_SECRET\" \\"
echo "        -X POST http://localhost:8787/route \\"
echo "        -H \"Content-Type: application/json\" \\"
echo "        -d '{\"text\": \"Hello world\", \"route\": \"gen\"}'"