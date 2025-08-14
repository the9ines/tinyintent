#!/usr/bin/env bash

# TinyIntent Routes Smoke Tests
# Tests M4 enhancements: JSON logging, exec assertions, error handling

set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENT="$PROJECT_ROOT/agent/neuro_agent"
TEST_LOG="/tmp/tinyintent-test.log"
JSON_LOG="/tmp/tinyintent-json.log"

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

# Ensure agent is executable
if [[ ! -x "$AGENT" ]]; then
    log_fail "neuro_agent not found or not executable at $AGENT"
fi

# Test 1: Help flag works
log_test "Help flag functionality"
if "$AGENT" --help | grep -q "TinyIntent Neuro Agent"; then
    log_pass "Help flag displays usage information"
else
    log_fail "Help flag does not work correctly"
fi

# Test 2: JSON mode with local_only route (dry run)
log_test "JSON mode with local_only route (dry run)"
echo "local summarization please" | ROUTE="local_only" "$AGENT" --dry-run --json > "$JSON_LOG" 2> "$TEST_LOG"

# Check for JSON structure and exec assertion
if jq -e '.route == "local_only" and .dry_run == true and .privacy_mode == "local_only" and .source == "neuro_agent"' "$JSON_LOG" >/dev/null && grep -q "exec: ollama run" "$TEST_LOG"; then
    log_pass "JSON structure and exec assertion valid for local_only route"
else
    log_fail "JSON structure or exec assertion invalid for local_only route. JSON: $(cat "$JSON_LOG") Stderr: $(cat "$TEST_LOG")"
fi

# Test 3: JSON mode with send_claude route (dry run)
log_test "JSON mode with send_claude route (dry run)"
echo "research quantum cryptography with citations" | ROUTE="send_claude" "$AGENT" --dry-run --json > "$JSON_LOG" 2> "$TEST_LOG"

# Check for JSON structure and exec assertion
if jq -e '.route == "send_claude" and .dry_run == true and .privacy_mode == "cloud" and .source == "neuro_agent"' "$JSON_LOG" >/dev/null && grep -q "exec: claude --permission-mode" "$TEST_LOG"; then
    log_pass "JSON structure and exec assertion valid for send_claude route"
else
    log_fail "JSON structure or exec assertion invalid for send_claude route. JSON: $(cat "$JSON_LOG") Stderr: $(cat "$TEST_LOG")"
fi

# Test 4: JSON mode with plan_then_claude route (dry run)
log_test "JSON mode with plan_then_claude route (dry run)"
echo "brainstorm steps then ask Claude to draft proposal" | ROUTE="plan_then_claude" "$AGENT" --dry-run --json > "$JSON_LOG" 2> "$TEST_LOG"

# Check all plan_then_claude requirements
line_count=$(wc -l < "$JSON_LOG")
if [[ $line_count -eq 2 ]] && \
   jq -e 'select(.phase == "refine_local") | .route == "plan_then_claude" and .privacy_mode == "local_only"' "$JSON_LOG" >/dev/null && \
   jq -e 'select(.phase == "cloud_final") | .route == "plan_then_claude" and .privacy_mode == "cloud"' "$JSON_LOG" >/dev/null && \
   grep -q "exec: ollama run" "$TEST_LOG" && grep -q "exec: claude --permission-mode" "$TEST_LOG"; then
    log_pass "All plan_then_claude requirements valid (2 phases, correct structure, both exec assertions)"
else
    log_fail "plan_then_claude validation failed. Lines: $line_count, JSON: $(cat "$JSON_LOG"), Stderr: $(cat "$TEST_LOG")"
fi

# Test 5: Required JSON fields validation
log_test "Required JSON fields validation"
echo "test validation" | ROUTE="local_only" "$AGENT" --dry-run --json > "$JSON_LOG" 2> "$TEST_LOG"

required_fields=("timestamp" "route" "model_name" "model_size" "tokens_in" "tokens_out" "duration_ms" "privacy_mode" "reclassified" "source" "dry_run")

missing_fields=()
for field in "${required_fields[@]}"; do
    if ! jq -e "has(\"$field\")" "$JSON_LOG" >/dev/null; then
        missing_fields+=("$field")
    fi
done

if [[ ${#missing_fields[@]} -eq 0 ]]; then
    log_pass "All required JSON fields present (${#required_fields[@]} fields)"
else
    log_fail "Missing JSON fields: ${missing_fields[*]}. Content: $(cat "$JSON_LOG")"
fi

# Test 6: Human-readable stderr output format
log_test "Human-readable stderr format"
echo "test stderr format" | ROUTE="local_only" "$AGENT" --dry-run 2> "$TEST_LOG" >/dev/null

if grep -q "route=local_only.*model=.*tokens_in=.*tokens_out=.*latency_ms=.*privacy=" "$TEST_LOG"; then
    log_pass "Human-readable stderr format matches expected pattern"
else
    log_fail "Human-readable stderr format incorrect. Content: $(cat "$TEST_LOG")"
fi

# Test 7: Quiet mode suppresses non-essential output
log_test "Quiet mode functionality"
echo "test quiet mode" | ROUTE="local_only" "$AGENT" --dry-run --quiet 2> "$TEST_LOG" >/dev/null

# In quiet mode with dry run, should have minimal stderr output
if [[ $(wc -l < "$TEST_LOG") -le 2 ]]; then
    log_pass "Quiet mode reduces stderr output"
else
    log_fail "Quiet mode not working correctly. Stderr has too many lines: $(cat "$TEST_LOG")"
fi

# Test 8: Error handling for unknown route
log_test "Error handling for unknown route"
if echo "test" | ROUTE="invalid_route" "$AGENT" --dry-run 2> "$TEST_LOG" >/dev/null; then
    log_fail "Agent should have failed with unknown route"
else
    if grep -q "Error: Unknown route" "$TEST_LOG" && grep -q "Valid routes:" "$TEST_LOG"; then
        log_pass "Unknown route error handled correctly with actionable message"
    else
        log_fail "Unknown route error message incorrect. Stderr: $(cat "$TEST_LOG")"
    fi
fi

# Test 9: Reclassified flag behavior
log_test "Reclassified flag when using ROUTE env var"
echo "test reclassification" | ROUTE="send_claude" "$AGENT" --dry-run --json > "$JSON_LOG" 2> "$TEST_LOG"

if jq -e '.reclassified == true' "$JSON_LOG" >/dev/null; then
    log_pass "Reclassified flag set to true when using ROUTE env var"
else
    log_fail "Reclassified flag should be true when ROUTE env var is used. Content: $(cat "$JSON_LOG")"
fi

# Test 10: Model size extraction
log_test "Model size extraction from model names"
echo "test model size" | ROUTE="local_only" OLLAMA_MODEL="qwen2.5:32b-instruct-q4_K_M" "$AGENT" --dry-run --json > "$JSON_LOG" 2> "$TEST_LOG"

if jq -e '.model_size == "32B"' "$JSON_LOG" >/dev/null; then
    log_pass "Model size correctly extracted as 32B"
else
    log_fail "Model size extraction failed. Expected 32B, got: $(jq -r '.model_size' "$JSON_LOG")"
fi

# Test 11: LOCAL_MODEL_PREF=8b forces 8B model
log_test "LOCAL_MODEL_PREF=8b forces 8B model"
echo "test 8b preference" | LOCAL_MODEL_PREF=8b ROUTE="local_only" "$AGENT" --dry-run --json > "$JSON_LOG" 2> "$TEST_LOG"

if jq -e '.model_name == "llama3.1:8b-instruct-q5_K_M" and .model_size == "8B" and .selection_reason == "env:LOCAL_MODEL_PREF=8b"' "$JSON_LOG" >/dev/null && grep -q "model_size=8B.*reason=env:LOCAL_MODEL_PREF=8b" "$TEST_LOG"; then
    log_pass "8B model preference enforced correctly"
else
    log_fail "8B model preference failed. JSON: $(cat "$JSON_LOG") Stderr: $(cat "$TEST_LOG")"
fi

# Test 12: LOCAL_MODEL_PREF=32b forces 32B model
log_test "LOCAL_MODEL_PREF=32b forces 32B model"
echo "test 32b preference" | LOCAL_MODEL_PREF=32b ROUTE="local_only" "$AGENT" --dry-run --json > "$JSON_LOG" 2> "$TEST_LOG"

if jq -e '.model_name == "qwen2.5:32b-instruct-q4_K_M" and .model_size == "32B" and .selection_reason == "env:LOCAL_MODEL_PREF=32b"' "$JSON_LOG" >/dev/null && grep -q "model_size=32B.*reason=env:LOCAL_MODEL_PREF=32b" "$TEST_LOG"; then
    log_pass "32B model preference enforced correctly"
else
    log_fail "32B model preference failed. JSON: $(cat "$JSON_LOG") Stderr: $(cat "$TEST_LOG")"
fi

# Test 13: LOCAL_MODEL_PREF=70b forces 70B model
log_test "LOCAL_MODEL_PREF=70b forces 70B model"
echo "test 70b preference" | LOCAL_MODEL_PREF=70b ROUTE="local_only" "$AGENT" --dry-run --json > "$JSON_LOG" 2> "$TEST_LOG"

if jq -e '.model_name == "llama3.1:70b-instruct-q4_K_M" and .model_size == "70B" and .selection_reason == "env:LOCAL_MODEL_PREF=70b"' "$JSON_LOG" >/dev/null && grep -q "model_size=70B.*reason=env:LOCAL_MODEL_PREF=70b" "$TEST_LOG"; then
    log_pass "70B model preference enforced correctly"
else
    log_fail "70B model preference failed. JSON: $(cat "$JSON_LOG") Stderr: $(cat "$TEST_LOG")"
fi

# Test 14: Keyword detection bumps to 70B
log_test "Keyword detection bumps to 70B model"
echo "Please prove this mathematical theorem using formal logic" | ROUTE="local_only" "$AGENT" --dry-run --json > "$JSON_LOG" 2> "$TEST_LOG"

if jq -e '.model_name == "llama3.1:70b-instruct-q4_K_M" and .model_size == "70B" and (.selection_reason | test("keyword:"))' "$JSON_LOG" >/dev/null && grep -q "model_size=70B.*reason=keyword:" "$TEST_LOG"; then
    log_pass "Keyword detection correctly selects 70B model"
else
    log_fail "Keyword detection failed. JSON: $(cat "$JSON_LOG") Stderr: $(cat "$TEST_LOG")"
fi

# Test 15: Plan_then_claude uses model selector for local phase
log_test "Plan_then_claude uses model selector for local phase"
echo "short prompt for planning" | LOCAL_MODEL_PREF=8b ROUTE="plan_then_claude" "$AGENT" --dry-run --json > "$JSON_LOG" 2> "$TEST_LOG"

# Should produce two JSON lines with 8B for refine_local phase
if jq -e 'select(.phase == "refine_local") | .model_name == "llama3.1:8b-instruct-q5_K_M" and .model_size == "8B" and .selection_reason == "env:LOCAL_MODEL_PREF=8b"' "$JSON_LOG" >/dev/null && grep -q "model=llama3.1:8b-instruct-q5_K_M.*model_size=8B.*reason=env:LOCAL_MODEL_PREF=8b" "$TEST_LOG"; then
    log_pass "Plan_then_claude correctly uses model selector for local phase"
else
    log_fail "Plan_then_claude model selector failed. JSON: $(cat "$JSON_LOG") Stderr: $(cat "$TEST_LOG")"
fi

# Cleanup
rm -f "$TEST_LOG" "$JSON_LOG"

# Final report
echo
echo "=========================================="
echo -e "${GREEN}Tests passed: $TESTS_PASSED/$TESTS_RUN${NC}"
echo "=========================================="

if [[ $TESTS_PASSED -eq $TESTS_RUN ]]; then
    echo -e "${GREEN}All tests passed! 🎉${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed! ❌${NC}"
    exit 1
fi