#!/usr/bin/env bash
# TinyIntent Router Doctor - diagnose router binary and Core ML model

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "==========================================="
echo -e "${BLUE}TinyIntent Router Doctor${NC}"
echo "==========================================="

# Check 1: Router binary executable
echo -e "${BLUE}1. Router Binary${NC}"
ROUTER_BIN="router/tinyintent"
if [[ -x "$ROUTER_BIN" ]]; then
    echo -e "   ${GREEN}✅ $ROUTER_BIN is executable${NC}"
else
    echo -e "   ${RED}❌ $ROUTER_BIN not found or not executable${NC}"
    echo "   Run: make build"
fi

# Check 2: Core ML model files
echo -e "${BLUE}2. Core ML Model Files${NC}"
MODEL_FOUND=false
for model in "router/TinyIntent.mlmodel" "router/TinyIntent.mlpackage"; do
    if [[ -e "$model" ]]; then
        echo -e "   ${GREEN}✅ $model exists${NC}"
        MODEL_FOUND=true
    else
        echo -e "   ${YELLOW}⚠️  $model not found${NC}"
    fi
done

if [[ "$MODEL_FOUND" == "false" ]]; then
    echo -e "   ${RED}❌ No Core ML model found${NC}"
    echo "   Run: make train"
fi

# Check 3: Clean compiled models
echo -e "${BLUE}3. Cleaning Compiled Models${NC}"
COMPILED_MODELS=$(find router -name "*.mlmodelc" 2>/dev/null || true)
if [[ -n "$COMPILED_MODELS" ]]; then
    echo "   Removing compiled models:"
    echo "$COMPILED_MODELS" | while read -r model; do
        echo "     Removing $model"
        rm -rf "$model"
    done
    echo -e "   ${GREEN}✅ Compiled models cleaned${NC}"
else
    echo -e "   ${GREEN}✅ No compiled models to clean${NC}"
fi

# Check 4: Test router with sample inputs
echo -e "${BLUE}4. Router Classification Tests${NC}"

if [[ ! -x "$ROUTER_BIN" ]]; then
    echo -e "   ${YELLOW}⚠️  Skipping tests - router binary not executable${NC}"
    echo "   Run: make build"
    exit 0
fi

# Sample 1: General text (should be gen or act)
echo -n "   Sample 1: "
SAMPLE1="summarize tinyintent in one sentence"
start_time=$(date +%s%3N)
if output=$(echo "$SAMPLE1" | "$ROUTER_BIN" 2>&1); then
    end_time=$(date +%s%3N)
    time_ms=$((end_time - start_time))
    label=$(echo "$output" | head -1 | tr -d '\n')
    echo -e "label=${label} rc=0 time_ms=${time_ms}"
else
    rc=$?
    end_time=$(date +%s%3N)
    time_ms=$((end_time - start_time))
    echo -e "label=ERROR rc=${rc} time_ms=${time_ms}"
    echo -e "   ${RED}❌ Router failed on sample 1${NC}"
    echo "   Suggestion: run 'make train', then 'make build'"
fi

# Sample 2: Action text
echo -n "   Sample 2: "
SAMPLE2="restart the cryptobot on vps-1"
start_time=$(date +%s%3N)
if output=$(echo "$SAMPLE2" | "$ROUTER_BIN" 2>&1); then
    end_time=$(date +%s%3N)
    time_ms=$((end_time - start_time))
    label=$(echo "$output" | head -1 | tr -d '\n')
    echo -e "label=${label} rc=0 time_ms=${time_ms}"
else
    rc=$?
    end_time=$(date +%s%3N)
    time_ms=$((end_time - start_time))
    echo -e "label=ERROR rc=${rc} time_ms=${time_ms}"
    echo -e "   ${RED}❌ Router failed on sample 2${NC}"
    echo "   Suggestion: run 'make train', then 'make build'"
fi

echo "==========================================="
echo -e "${BLUE}Router diagnosis complete${NC}"
echo "==========================================="