#!/usr/bin/env bash
# TinyIntent Router Clean - remove compiled models and temporary artifacts

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "Cleaning router artifacts..."

# Remove compiled Core ML models
if ls router/*.mlmodelc >/dev/null 2>&1; then
    echo "Removing compiled models: router/*.mlmodelc"
    rm -rf router/*.mlmodelc
else
    echo "No compiled models found"
fi

# Clean other temporary artifacts but preserve source models
if [[ -d "router/.build" ]]; then
    echo "Cleaning Swift build artifacts"
    rm -rf router/.build
fi

if ls router/__pycache__ >/dev/null 2>&1; then
    echo "Cleaning Python cache"
    rm -rf router/__pycache__
fi

if ls router/*.pyc >/dev/null 2>&1; then
    echo "Cleaning Python bytecode"
    rm -f router/*.pyc
fi

echo -e "${GREEN}✅ Router artifacts cleaned${NC}"
echo -e "${YELLOW}Note: Preserved .mlmodel/.mlpackage source files${NC}"