#!/usr/bin/env bash

# TinyIntent No-Cloud Guard Test
# Ensures that M9 cloudless refactor is complete and no cloud functionality remains

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
    echo -e "${YELLOW}[GUARD]${NC} $1"
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

echo "==========================================="
echo -e "${YELLOW}TinyIntent M9 Cloudless Guard Tests${NC}"
echo "==========================================="

# Test 1: No Claude CLI references in neuro_agent
log_test "No Claude CLI references in neuro_agent"
if grep -qi "claude" "$PROJECT_ROOT/agent/neuro_agent"; then
    log_fail "Found Claude references in neuro_agent: $(grep -n -i claude "$PROJECT_ROOT/agent/neuro_agent")"
else
    log_pass "No Claude CLI references found in neuro_agent"
fi

# Test 2: No send_claude route in neuro_agent
log_test "No send_claude route in neuro_agent"
if grep -q "send_claude" "$PROJECT_ROOT/agent/neuro_agent"; then
    log_fail "Found send_claude route in neuro_agent: $(grep -n send_claude "$PROJECT_ROOT/agent/neuro_agent")"
else
    log_pass "No send_claude route found in neuro_agent"
fi

# Test 3: No plan_then_claude route in neuro_agent
log_test "No plan_then_claude route in neuro_agent"
if grep -q "plan_then_claude" "$PROJECT_ROOT/agent/neuro_agent"; then
    log_fail "Found plan_then_claude route in neuro_agent: $(grep -n plan_then_claude "$PROJECT_ROOT/agent/neuro_agent")"
else
    log_pass "No plan_then_claude route found in neuro_agent"
fi

# Test 4: Only local routes accepted by neuro_agent
log_test "Only local routes accepted by neuro_agent"
if grep -q "Valid routes:" "$PROJECT_ROOT/agent/neuro_agent"; then
    valid_routes_line=$(grep "Valid routes:" "$PROJECT_ROOT/agent/neuro_agent")
    if [[ "$valid_routes_line" =~ "send_claude" ]] || [[ "$valid_routes_line" =~ "plan_then_claude" ]]; then
        log_fail "Cloud routes still in valid routes list: $valid_routes_line"
    elif [[ "$valid_routes_line" =~ "local_only" ]] && [[ "$valid_routes_line" =~ "plan_then_local" ]]; then
        log_pass "Only local routes in valid routes list"
    else
        log_fail "Unexpected valid routes format: $valid_routes_line"
    fi
else
    log_fail "No valid routes documentation found in neuro_agent"
fi

# Test 5: Bridge has backward compatibility mapping
log_test "Bridge has backward compatibility mapping"
if grep -q "LEGACY_ROUTE_MAP" "$PROJECT_ROOT/bridge/tinyrpc.py" && \
   grep -q "send_claude.*local_only" "$PROJECT_ROOT/bridge/tinyrpc.py" && \
   grep -q "plan_then_claude.*plan_then_local" "$PROJECT_ROOT/bridge/tinyrpc.py"; then
    log_pass "Bridge has backward compatibility mapping for legacy routes"
else
    log_fail "Bridge missing backward compatibility mapping"
fi

# Test 6: Bridge only accepts local routes in LABELS
log_test "Bridge only accepts local routes in LABELS"
if grep -q "LABELS.*=" "$PROJECT_ROOT/bridge/tinyrpc.py"; then
    labels_line=$(grep "LABELS.*=" "$PROJECT_ROOT/bridge/tinyrpc.py" | head -1)
    if [[ "$labels_line" =~ "send_claude" ]] || [[ "$labels_line" =~ "plan_then_claude" ]]; then
        log_fail "Cloud routes still in LABELS: $labels_line"
    elif [[ "$labels_line" =~ "local_only" ]] && [[ "$labels_line" =~ "plan_then_local" ]]; then
        log_pass "Only local routes in LABELS"
    else
        log_fail "Unexpected LABELS format: $labels_line"
    fi
else
    log_fail "No LABELS definition found in bridge"
fi

# Test 7: Bridge logs show local_only privacy mode
log_test "Bridge logs show local_only privacy mode"
if grep -q "privacy=local_only" "$PROJECT_ROOT/bridge/tinyrpc.py"; then
    log_pass "Bridge logs show local_only privacy mode"
else
    log_fail "Bridge does not log local_only privacy mode"
fi

# Test 8: No cloud references in help text
log_test "No cloud references in help text"
cloud_terms=("cloud" "Claude" "send_claude" "plan_then_claude")
found_terms=()

for term in "${cloud_terms[@]}"; do
    if "$PROJECT_ROOT/agent/neuro_agent" --help | grep -qi "$term"; then
        found_terms+=("$term")
    fi
done

if [[ ${#found_terms[@]} -eq 0 ]]; then
    log_pass "No cloud references in help text"
else
    log_fail "Found cloud references in help text: ${found_terms[*]}"
fi

# Test 9: No CLAUDE_CLI_MODEL environment variable
log_test "No CLAUDE_CLI_MODEL environment variable"
if grep -q "CLAUDE_CLI_MODEL" "$PROJECT_ROOT/agent/neuro_agent"; then
    log_fail "Found CLAUDE_CLI_MODEL environment variable: $(grep -n CLAUDE_CLI_MODEL "$PROJECT_ROOT/agent/neuro_agent")"
else
    log_pass "No CLAUDE_CLI_MODEL environment variable found"
fi

# Test 10: Functional test - agent rejects cloud routes
log_test "Agent rejects unknown/cloud routes"
test_log="/tmp/tinyintent-nocloud-test.log"

# Test with legacy send_claude route (should fail)
if echo "test cloud rejection" | ROUTE="send_claude" "$PROJECT_ROOT/agent/neuro_agent" --dry-run 2>"$test_log" >/dev/null; then
    log_fail "Agent accepted send_claude route (should reject)"
else
    if grep -q "Error: Unknown route" "$test_log" && grep -q "Valid routes: local_only, plan_then_local" "$test_log"; then
        log_pass "Agent correctly rejects cloud routes with proper error message"
    else
        log_fail "Agent error message incorrect for cloud routes: $(cat "$test_log")"
    fi
fi

# Test 11: Functional test - only local execution modes work
log_test "Only local execution modes work"
json_log="/tmp/tinyintent-local-test.json"

# Test local_only route
echo "local test" | ROUTE="local_only" "$PROJECT_ROOT/agent/neuro_agent" --dry-run --json >"$json_log" 2>"$test_log"
if jq -e '.privacy_mode == "local_only"' "$json_log" >/dev/null; then
    log_pass "local_only route uses local_only privacy mode"
else
    log_fail "local_only route privacy mode incorrect: $(jq -r '.privacy_mode' "$json_log")"
fi

# Test plan_then_local route
echo "planning test" | ROUTE="plan_then_local" "$PROJECT_ROOT/agent/neuro_agent" --dry-run --json >"$json_log" 2>"$test_log"
if jq -e 'select(.phase == "refine_local") | .privacy_mode == "local_only"' "$json_log" >/dev/null && \
   jq -e 'select(.phase == "local_final") | .privacy_mode == "local_only"' "$json_log" >/dev/null; then
    log_pass "plan_then_local route uses local_only privacy mode for both phases"
else
    log_fail "plan_then_local route privacy modes incorrect: $(cat "$json_log")"
fi

# Test 12: No network calls in dry run mode
log_test "No network dependency checks or calls"
if echo "network isolation test" | ROUTE="local_only" "$PROJECT_ROOT/agent/neuro_agent" --dry-run 2>"$test_log" >/dev/null; then
    if grep -qi "claude" "$test_log" || grep -qi "authentication" "$test_log" || grep -i "connection" "$test_log"; then
        log_fail "Found network/cloud references in dry run: $(grep -i -E "(claude|auth|connection)" "$test_log")"
    else
        log_pass "No network dependencies in dry run mode"
    fi
else
    log_fail "Dry run failed unexpectedly: $(cat "$test_log")"
fi

# Cleanup
rm -f "$test_log" "$json_log"

# Final report
echo
echo "=========================================="
echo -e "${GREEN}Guard tests passed: $TESTS_PASSED/$TESTS_RUN${NC}"
echo "=========================================="

if [[ $TESTS_PASSED -eq $TESTS_RUN ]]; then
    echo -e "${GREEN}✅ M9 Cloudless refactor complete - no cloud functionality detected${NC}"
    exit 0
else
    echo -e "${RED}❌ M9 Cloudless refactor incomplete - cloud functionality still present${NC}"
    exit 1
fi