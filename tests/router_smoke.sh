#!/usr/bin/env bash
# TinyIntent Router Smoke Tests - non-flaky router validation

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "==========================================="
echo -e "${YELLOW}TinyIntent Router Smoke Tests${NC}"
echo "==========================================="

ROUTER_BIN="router/tinyintent"

# Check if model file exists
MODEL_EXISTS=false
for model in "router/TinyIntent.mlmodel" "router/TinyIntent.mlpackage"; do
    if [[ -e "$model" ]]; then
        MODEL_EXISTS=true
        break
    fi
done

if [[ "$MODEL_EXISTS" == "false" ]]; then
    echo -e "${YELLOW}SKIP: No Core ML model found${NC}"
    echo "Run 'make train' to create model files"
    exit 0
fi

if [[ ! -x "$ROUTER_BIN" ]]; then
    echo -e "${YELLOW}SKIP: Router binary not executable${NC}"
    echo "Run 'make build' to create router binary"
    exit 0
fi

# Test 1: General text
echo -n "Test 1 (general text): "
SAMPLE1="summarize tinyintent in one sentence"
if echo "$SAMPLE1" | "$ROUTER_BIN" >/dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC} (rc=0)"
    TESTS_PASSED=$((${TESTS_PASSED:-0} + 1))
else
    rc=$?
    echo -e "${RED}FAIL${NC} (rc=$rc)"
    echo -e "${RED}Router failed on sample 1${NC}"
    exit 1
fi

# Test 2: Action text
echo -n "Test 2 (action text): "
SAMPLE2="restart the cryptobot on vps-1"
if echo "$SAMPLE2" | "$ROUTER_BIN" >/dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC} (rc=0)"
    TESTS_PASSED=$((${TESTS_PASSED:-0} + 1))
else
    rc=$?
    echo -e "${RED}FAIL${NC} (rc=$rc)"
    echo -e "${RED}Router failed on sample 2${NC}"
    exit 1
fi

echo
echo -e "${GREEN}PASS: router rc==0 for 2 samples${NC}"
echo "==========================================="