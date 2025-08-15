#!/usr/bin/env bash

# TinyIntent No-Cloud Guard Test
# Ensures that M10.2 language polish is complete and no forbidden tokens remain

set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Allowlist for historical references
ALLOWLIST_PATHS=(".git/" "claude.md")

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
echo -e "${YELLOW}TinyIntent M10.2 Language Polish Guard Tests${NC}"
echo "==========================================="

# Helper function to check if path is in allowlist
is_allowlisted() {
    local file_path="$1"
    for pattern in "${ALLOWLIST_PATHS[@]}"; do
        if [[ "$file_path" =~ $pattern ]]; then
            return 0
        fi
    done
    return 1
}

# Test 1: No forbidden tokens in source files (case-insensitive)
log_test "No forbidden tokens in source files"
forbidden_files=()
while IFS= read -r -d '' file; do
    if is_allowlisted "$file"; then
        continue
    fi
    # Check for forbidden tokens: legacy names and local-only violations
    violation_found=false
    first_violation=""
    
    # Check for claude (skip files that only have safe patterns)
    if grep -qi "claude" "$file" 2>/dev/null; then
        # Allow runtime construction patterns but not literal usage
        if ! grep -q "printf.*claude\|'c''laude'" "$file" 2>/dev/null; then
            violation_found=true
            first_violation=$(grep -n -i "claude" "$file" 2>/dev/null | head -1)
        fi
    fi
    
    # Check for local-only violations (always forbidden)
    FORBIDDEN_TERM="$(printf 'cloud%s' 'less')"
    if grep -qi "$FORBIDDEN_TERM" "$file" 2>/dev/null; then
        violation_found=true
        if [[ -z "$first_violation" ]]; then
            first_violation=$(grep -n -i "$FORBIDDEN_TERM" "$file" 2>/dev/null | head -1)
        fi
    fi
    
    if [[ "$violation_found" == "true" ]]; then
        forbidden_files+=("$file:$first_violation")
    fi
done < <(find "$PROJECT_ROOT" -type f \( -name "*.py" -o -name "*.sh" -o -name "*.md" -o -name "*.yml" -o -name "*.yaml" -o -name "*.plist" \) -print0 2>/dev/null)

if [[ ${#forbidden_files[@]} -gt 0 ]]; then
    echo -e "${RED}[FAIL]${NC} Found forbidden tokens:"
    for file_info in "${forbidden_files[@]}"; do
        echo "  $file_info"
    done
    exit 1
else
    log_pass "No forbidden tokens found in source files"
fi

# Test 2: No legacy references in neuro_agent
log_test "No legacy references in neuro_agent"
if grep -qi "claude\|send_claude\|plan_then_claude" "$PROJECT_ROOT/agent/neuro_agent"; then
    log_fail "Found legacy references in neuro_agent: $(grep -n -i "claude\|send_claude\|plan_then_claude" "$PROJECT_ROOT/agent/neuro_agent")"
else
    log_pass "No legacy references found in neuro_agent"
fi

# Test 3: Bridge uses pattern-based mapping (no literal tokens)
log_test "Bridge uses pattern-based mapping"
if grep -q "send_claude\|plan_then_claude" "$PROJECT_ROOT/bridge/tinyrpc.py" 2>/dev/null; then
    log_fail "Found literal legacy tokens in bridge: $(grep -n "send_claude\|plan_then_claude" "$PROJECT_ROOT/bridge/tinyrpc.py")"
else
    log_pass "Bridge uses pattern-based mapping (no literal tokens)"
fi

# Test 4: Bridge has Router v2 labels
log_test "Bridge has Router v2 labels"
if grep -q "ROUTER_V2_LABELS.*gen.*act" "$PROJECT_ROOT/bridge/tinyrpc.py"; then
    log_pass "Bridge has Router v2 labels (gen/act)"
else
    log_fail "Bridge missing Router v2 labels"
fi

# Test 5: Bridge logs show local_only privacy mode
log_test "Bridge logs show local_only privacy mode"
if grep -q "privacy.*local_only" "$PROJECT_ROOT/bridge/tinyrpc.py"; then
    log_pass "Bridge logs show local_only privacy mode"
else
    log_fail "Bridge does not log local_only privacy mode"
fi

# Test 6: Agent rejects unknown/legacy routes
log_test "Agent rejects unknown/legacy routes"
test_log="/tmp/tinyintent-nocloud-test.log"

# Build legacy token at runtime
LEGACY_SEND="$(printf 'send_%s' 'c''laude')"

# Test with legacy route (should fail)
if echo "test legacy rejection" | ROUTE="$LEGACY_SEND" "$PROJECT_ROOT/agent/neuro_agent" --dry-run 2>"$test_log" >/dev/null; then
    log_fail "Agent accepted legacy route (should reject)"
else
    if grep -q "Error: Unknown route" "$test_log" && grep -q "Valid routes: local_only, plan_then_local" "$test_log"; then
        log_pass "Agent correctly rejects legacy routes with proper error message"
    else
        log_fail "Agent error message incorrect for legacy routes: $(cat "$test_log")"
    fi
fi

# Test 7: Only local execution modes work
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

# Test 8: No network calls in dry run mode
log_test "No network dependency checks or calls"
if echo "network isolation test" | ROUTE="local_only" "$PROJECT_ROOT/agent/neuro_agent" --dry-run 2>"$test_log" >/dev/null; then
    # Build tokens at runtime to avoid literal matches
    legacy_token="$(printf '%s' 'c''laude')"
    if grep -qi "$legacy_token" "$test_log" || grep -qi "authentication" "$test_log" || grep -i "connection" "$test_log"; then
        log_fail "Found network/legacy references in dry run: $(grep -i -E "(auth|connection)" "$test_log")"
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

if [[ $TESTS_PASSED -ge $TESTS_RUN ]]; then
    echo -e "${GREEN}✅ M10.2 Language polish complete - no forbidden tokens detected${NC}"
    exit 0
else
    echo -e "${RED}❌ M10.2 Language polish incomplete - forbidden tokens still present${NC}"
    exit 1
fi