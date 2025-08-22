#!/bin/bash
# Export TinyIntent episode data for analysis
# Creates timestamped archives of learning data

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_ROOT/data"
EXPORT_DIR="$PROJECT_ROOT/exports"

# Create exports directory
mkdir -p "$EXPORT_DIR"

# Generate timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
EXPORT_FILE="$EXPORT_DIR/episodes_$TIMESTAMP.tar.gz"

echo "📦 Exporting TinyIntent episode data..."
echo "Export file: $EXPORT_FILE"

# Check if episode data exists
if [[ ! -d "$DATA_DIR/episodes" ]]; then
    echo "❌ No episode data found at $DATA_DIR/episodes"
    exit 1
fi

# Count episodes
NDJSON_COUNT=0
if [[ -f "$DATA_DIR/episodes/events.ndjson" ]]; then
    NDJSON_COUNT=$(wc -l < "$DATA_DIR/episodes/events.ndjson")
fi

echo ""
echo "📊 Episode summary:"
echo "   NDJSON events: $NDJSON_COUNT"

if [[ -f "$DATA_DIR/episodes/events.db" ]]; then
    echo "   SQLite DB:     $(ls -lh "$DATA_DIR/episodes/events.db" | awk '{print $5}')"
fi

# Create archive
cd "$PROJECT_ROOT"
tar -czf "$EXPORT_FILE" \
    --exclude="*.log" \
    --exclude="__pycache__" \
    data/episodes/

echo ""
echo "✅ Export complete!"
echo "   File: $EXPORT_FILE"
echo "   Size: $(ls -lh "$EXPORT_FILE" | awk '{print $5}')"

# Cleanup old exports (keep last 10)
cd "$EXPORT_DIR"
ls -t episodes_*.tar.gz 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null || true

echo "🧹 Cleaned up old exports (kept most recent 10)"