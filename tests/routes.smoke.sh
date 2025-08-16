#!/usr/bin/env bash

# TinyIntent M0 Routes Smoke Tests
# Tests minimal bridge functionality: gen, act, auto routes

set -euo pipefail

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
    echo -e "${YELLOW}[TEST]${NC} $1"
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

# Check if bridge is running
BASE_URL="http://127.0.0.1:8787"
if ! curl -s "$BASE_URL/healthz" >/dev/null 2>&1; then
    log_skip "Bridge not running - start with: bash scripts/bootstrap_fresh.sh"
    exit 0
fi

# Get secret from plist
PLIST_PATH="$PROJECT_ROOT/launchd/com.tinyintent.tinyrpc.plist"
if [[ ! -f "$PLIST_PATH" ]]; then
    log_skip "Plist not found - run: bash scripts/bootstrap_fresh.sh"
    exit 0
fi

SECRET=$(/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:TINYINTENT_SECRET" "$PLIST_PATH" 2>/dev/null || echo "")
if [[ -z "$SECRET" ]]; then
    log_skip "No secret in plist - run: bash scripts/bootstrap_fresh.sh"
    exit 0
fi

echo "==========================================="
echo -e "${YELLOW}TinyIntent M0 Routes Smoke Tests${NC}"
echo "==========================================="

# Test 1: Gen route
log_test "Gen route with local LLM"
RESPONSE=$(curl -s -X POST "$BASE_URL/route" \
    -H "Content-Type: application/json" \
    -H "X-TinyIntent-Secret: $SECRET" \
    -d '{"text":"explain REST APIs briefly","route":"gen"}' 2>/dev/null || echo '{"error":"connection_failed"}')

if echo "$RESPONSE" | jq -e '.text and .model and .latency_ms' >/dev/null 2>&1; then
    log_pass "Gen route returns text response with model info"
elif echo "$RESPONSE" | jq -e '.error == "missing_dependency"' >/dev/null 2>&1; then
    log_skip "Gen route skipped - Ollama not available"
else
    echo "Response: $RESPONSE"
    log_fail "Gen route did not return expected JSON structure"
fi

# Test 2: Act route (preview only)
log_test "Act route returns preview only"
RESPONSE=$(curl -s -X POST "$BASE_URL/route" \
    -H "Content-Type: application/json" \
    -H "X-TinyIntent-Secret: $SECRET" \
    -d '{"text":"restart the service","route":"act"}' 2>/dev/null || echo '{"error":"connection_failed"}')

if echo "$RESPONSE" | jq -e '.action == "preview" and .confirm_required == true and .summary' >/dev/null 2>&1; then
    log_pass "Act route returns preview with confirmation required"
else
    echo "Response: $RESPONSE"
    log_fail "Act route did not return expected preview structure"
fi

# Test 3: Auto route with gen-like text
log_test "Auto route classifies gen-like text"
RESPONSE=$(curl -s -X POST "$BASE_URL/route" \
    -H "Content-Type: application/json" \
    -H "X-TinyIntent-Secret: $SECRET" \
    -d '{"text":"summarize machine learning concepts","route":"auto"}' 2>/dev/null || echo '{"error":"connection_failed"}')

# Should route to gen and return text response
if echo "$RESPONSE" | jq -e '.text and .model' >/dev/null 2>&1; then
    log_pass "Auto route correctly classified and executed gen response"
elif echo "$RESPONSE" | jq -e '.error == "missing_dependency"' >/dev/null 2>&1; then
    log_skip "Auto->gen route skipped - Ollama not available"
else
    echo "Response: $RESPONSE"
    log_fail "Auto route with gen-like text failed"
fi

# Test 4: Auto route with act-like text (using heuristic fallback)
log_test "Auto route classifies act-like text (heuristic fallback)"
RESPONSE=$(curl -s -X POST "$BASE_URL/route" \
    -H "Content-Type: application/json" \
    -H "X-TinyIntent-Secret: $SECRET" \
    -d '{"text":"restart the application server","route":"auto"}' 2>/dev/null || echo '{"error":"connection_failed"}')

# Should route to act and return preview
if echo "$RESPONSE" | jq -e '.action == "preview" and .confirm_required == true' >/dev/null 2>&1; then
    log_pass "Auto route correctly classified act-like text using heuristic"
else
    echo "Response: $RESPONSE"
    log_fail "Auto route with act-like text failed"
fi

# Test 5: Invalid route
log_test "Invalid route returns error"
RESPONSE=$(curl -s -w "HTTPSTATUS:%{http_code}" -X POST "$BASE_URL/route" \
    -H "Content-Type: application/json" \
    -H "X-TinyIntent-Secret: $SECRET" \
    -d '{"text":"test","route":"invalid"}' 2>/dev/null || echo "HTTPSTATUS:000")

STATUS=$(echo "$RESPONSE" | grep -o "HTTPSTATUS:[0-9]*" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed -E 's/HTTPSTATUS:[0-9]{3}$//')

if [[ "$STATUS" == "400" ]] && echo "$BODY" | jq -e '.error' >/dev/null 2>&1; then
    log_pass "Invalid route correctly returns 400 error"
else
    echo "Status: $STATUS, Body: $BODY"
    log_fail "Invalid route handling failed"
fi

# Test 6: Missing text
log_test "Missing text returns error"
RESPONSE=$(curl -s -w "HTTPSTATUS:%{http_code}" -X POST "$BASE_URL/route" \
    -H "Content-Type: application/json" \
    -H "X-TinyIntent-Secret: $SECRET" \
    -d '{"route":"gen"}' 2>/dev/null || echo "HTTPSTATUS:000")

STATUS=$(echo "$RESPONSE" | grep -o "HTTPSTATUS:[0-9]*" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed -E 's/HTTPSTATUS:[0-9]{3}$//')

if [[ "$STATUS" == "400" ]] && echo "$BODY" | jq -e '.error' >/dev/null 2>&1; then
    log_pass "Missing text correctly returns 400 error"
else
    echo "Status: $STATUS, Body: $BODY"
    log_fail "Missing text validation failed"
fi

# Final report
echo
echo "=========================================="
echo -e "${GREEN}Routes tests passed: $TESTS_PASSED/$TESTS_RUN${NC}"
echo "=========================================="

if [[ $TESTS_PASSED -eq $TESTS_RUN ]]; then
    echo -e "${GREEN}✅ All routes working correctly${NC}"
    exit 0
else
    echo -e "${RED}❌ Some route tests failed${NC}"
    exit 1
fi