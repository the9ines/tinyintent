#!/usr/bin/env bash
# TinyIntent Router Rebuild Kit - complete router rebuild and verification

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
echo -e "${BLUE}TinyIntent Router Rebuild Kit${NC}"
echo "==========================================="

# 1) Check Xcode CLI tools
echo -e "${BLUE}1. Checking Xcode Command Line Tools${NC}"
if ! xcode-select -p >/dev/null 2>&1; then
    echo -e "${RED}❌ Xcode Command Line Tools not found${NC}"
    echo -e "${YELLOW}Install with: xcode-select --install${NC}"
    echo -e "${YELLOW}Then re-run this script${NC}"
    exit 1
else
    XCODE_PATH=$(xcode-select -p)
    echo -e "${GREEN}✅ Xcode CLI tools found at: $XCODE_PATH${NC}"
fi

# 2) Remove stale compiled bundles
echo -e "${BLUE}2. Cleaning compiled models${NC}"
if ls router/*.mlmodelc >/dev/null 2>&1; then
    echo "   Removing compiled models..."
    rm -rf router/*.mlmodelc
    echo -e "${GREEN}✅ Compiled models cleaned${NC}"
else
    echo -e "${GREEN}✅ No compiled models to clean${NC}"
fi

# 3) Run make train
echo -e "${BLUE}3. Training router model${NC}"
if ! make train; then
    echo -e "${RED}❌ Training failed${NC}"
    echo -e "${YELLOW}Debug steps:${NC}"
    echo "  1. Check if Python dependencies are installed"
    echo "  2. Verify router/data/intents.tsv exists"
    echo "  3. Check router/train_intent.py for errors"
    exit 1
fi

# Verify model was created
MODEL_EXISTS=false
for model in "router/TinyIntent.mlmodel" "router/TinyIntent.mlpackage"; do
    if [[ -e "$model" ]]; then
        MODEL_EXISTS=true
        echo -e "${GREEN}✅ Model created: $model${NC}"
        break
    fi
done

if [[ "$MODEL_EXISTS" == "false" ]]; then
    echo -e "${RED}❌ No model file created by training${NC}"
    echo -e "${YELLOW}Expected: router/TinyIntent.mlmodel or router/TinyIntent.mlpackage${NC}"
    exit 1
fi

# 4) Run make build
echo -e "${BLUE}4. Building router binary${NC}"
if ! make build; then
    echo -e "${RED}❌ Build failed${NC}"
    echo -e "${YELLOW}Debug steps:${NC}"
    echo "  1. Check Swift compiler installation"
    echo "  2. Verify router/Package.swift is valid"
    echo "  3. Re-run: xcode-select --install"
    exit 1
fi

if [[ ! -x "router/tinyintent" ]]; then
    echo -e "${RED}❌ Router binary not created or not executable${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Router binary built: router/tinyintent${NC}"

# 5) Verify router with two samples
echo -e "${BLUE}5. Verifying router with sample inputs${NC}"

SAMPLE1="summarize tinyintent in one sentence"
SAMPLE2="restart the cryptobot on vps-1"

# Test sample 1
echo -n "   Sample 1 (general): "
START_TIME=$(date +%s%3N)
if OUTPUT1=$(echo "$SAMPLE1" | router/tinyintent 2>&1); then
    END_TIME=$(date +%s%3N)
    DURATION_MS=$((END_TIME - START_TIME))
    LABEL1=$(echo "$OUTPUT1" | head -n1 | tr -d '\n\r')
    echo -e "${GREEN}PASS${NC} label=$LABEL1 rc=0 time_ms=$DURATION_MS"
else
    rc=$?
    echo -e "${RED}FAIL${NC} rc=$rc"
    echo -e "${RED}Error output: $OUTPUT1${NC}"
    echo -e "${YELLOW}Try: make train && make build${NC}"
    exit 1
fi

# Test sample 2  
echo -n "   Sample 2 (action): "
START_TIME=$(date +%s%3N)
if OUTPUT2=$(echo "$SAMPLE2" | router/tinyintent 2>&1); then
    END_TIME=$(date +%s%3N)
    DURATION_MS=$((END_TIME - START_TIME))
    LABEL2=$(echo "$OUTPUT2" | head -n1 | tr -d '\n\r')
    echo -e "${GREEN}PASS${NC} label=$LABEL2 rc=0 time_ms=$DURATION_MS"
else
    rc=$?
    echo -e "${RED}FAIL${NC} rc=$rc"
    echo -e "${RED}Error output: $OUTPUT2${NC}"
    echo -e "${YELLOW}Try: make train && make build${NC}"
    exit 1
fi

echo "==========================================="
echo -e "${GREEN}OK: router rebuilt and verified${NC}"
echo "==========================================="