#!/usr/bin/env bash

# TinyIntent Health Check Tests
# Tests the /healthz and /readyz endpoints

set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TESTS_RUN=0
TESTS_PASSED=0

log_test() {
    echo -e "${YELLOW}[HEALTH]${NC} $1"
    TESTS_RUN=$((TESTS_RUN + 1))
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    exit 1
}

log_skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1"
}

echo "==========================================="
echo -e "${YELLOW}TinyIntent Health Endpoint Tests${NC}"
echo "==========================================="

# Test 1: /healthz endpoint
log_test "Testing /healthz endpoint"

if ! command -v curl >/dev/null; then
    log_skip "curl not available - skipping health tests"
    exit 0
fi

healthz_response=$(curl -s -w "HTTPSTATUS:%{http_code}" http://127.0.0.1:8787/healthz 2>/dev/null || echo "HTTPSTATUS:000")
healthz_body=$(echo "$healthz_response" | sed -E 's/HTTPSTATUS:[0-9]{3}$//')
healthz_status=$(echo "$healthz_response" | grep -o "HTTPSTATUS:[0-9]*" | cut -d: -f2)

if [[ "$healthz_status" != "200" ]]; then
    log_skip "Bridge not running (HTTP $healthz_status) - skipping health tests"
    exit 0
fi

# Check Content-Type and JSON structure
content_type=$(curl -s -I http://127.0.0.1:8787/healthz 2>/dev/null | grep -i "content-type" | grep -i "application/json" || echo "")
if [[ -z "$content_type" ]]; then
    log_fail "/healthz does not return application/json"
fi

if echo "$healthz_body" | jq -e '.status == "ok"' >/dev/null 2>&1; then
    log_pass "/healthz returns valid JSON with status=ok"
else
    log_fail "/healthz does not return valid JSON structure"
fi

# Test 2: /readyz endpoint
log_test "Testing /readyz endpoint"

readyz_response=$(curl -s -w "HTTPSTATUS:%{http_code}" http://127.0.0.1:8787/readyz 2>/dev/null || echo "HTTPSTATUS:000")
readyz_body=$(echo "$readyz_response" | sed -E 's/HTTPSTATUS:[0-9]{3}$//')
readyz_status=$(echo "$readyz_response" | grep -o "HTTPSTATUS:[0-9]*" | cut -d: -f2)

if [[ "$SMOKE_MODE" == "ci" ]]; then
    # In CI mode, accept either 200 or 503 but require proper JSON
    if [[ "$readyz_status" =~ ^(200|503)$ ]] && echo "$readyz_body" | jq -e 'has("ready") and has("checks")' >/dev/null 2>&1; then
        log_pass "/readyz returns valid JSON structure (CI mode: HTTP $readyz_status)"
    else
        log_fail "/readyz does not return valid structure in CI mode"
    fi
else
    # Local mode: check if ready, print reasons if not, but don't fail
    if [[ "$readyz_status" == "200" ]]; then
        log_pass "/readyz reports system ready (HTTP 200)"
    elif [[ "$readyz_status" == "503" ]]; then
        reasons=$(echo "$readyz_body" | jq -r '.reasons[]?' 2>/dev/null || echo "unknown")
        echo -e "${YELLOW}[INFO]${NC} System not ready (HTTP 503): $reasons"
        log_pass "/readyz endpoint functional (not ready is OK locally)"
    else
        log_fail "/readyz unexpected status: $readyz_status"
    fi
fi

# Final report
echo
echo "=========================================="
echo -e "${GREEN}Health tests passed: $TESTS_PASSED/$TESTS_RUN${NC}"
echo "=========================================="

if [[ $TESTS_PASSED -eq $TESTS_RUN ]]; then
    echo -e "${GREEN}✅ Health endpoints working correctly${NC}"
    exit 0
else
    echo -e "${RED}❌ Some health tests failed${NC}"
    exit 1
fi