#!/bin/bash
# TinyIntent Authentication Tests
# Tests API authentication and security

set -euo pipefail

echo "🔐 TinyIntent Authentication Tests"
echo "================================="

BASE_URL="http://localhost:8787"
ERRORS=0

# Check if bridge is running
if ! curl -s "$BASE_URL/readyz" >/dev/null 2>&1; then
    echo "❌ Bridge not running at $BASE_URL"
    echo "   Start with: make bridgesrv"
    exit 1
fi

echo "✅ Bridge is running"
echo ""

# Test 1: Unauthenticated request should fail
echo "🧪 Test 1: Unauthenticated requests"
RESPONSE=$(curl -s -w "%{http_code}" -o /dev/null -X POST "$BASE_URL/route" \
    -H "Content-Type: application/json" \
    -d '{"text": "test", "route": "gen"}')

if [[ "$RESPONSE" == "401" ]]; then
    echo "  ✅ Unauthenticated request properly rejected (401)"
else
    echo "  ❌ Expected 401, got $RESPONSE"
    ((ERRORS++))
fi

# Test 2: Wrong secret should fail
echo ""
echo "🧪 Test 2: Invalid secret"
RESPONSE=$(curl -s -w "%{http_code}" -o /dev/null -X POST "$BASE_URL/route" \
    -H "Content-Type: application/json" \
    -H "X-TinyIntent-Secret: invalid-secret" \
    -d '{"text": "test", "route": "gen"}')

if [[ "$RESPONSE" == "401" ]]; then
    echo "  ✅ Invalid secret properly rejected (401)"
else
    echo "  ❌ Expected 401, got $RESPONSE"
    ((ERRORS++))
fi

# Test 3: Valid secret (if available)
echo ""
echo "🧪 Test 3: Valid authentication"
if [[ -n "${TINYINTENT_SECRET:-}" ]]; then
    RESPONSE=$(curl -s -w "%{http_code}" -o /dev/null -X POST "$BASE_URL/route" \
        -H "Content-Type: application/json" \
        -H "X-TinyIntent-Secret: $TINYINTENT_SECRET" \
        -d '{"text": "test", "route": "gen"}')
    
    if [[ "$RESPONSE" == "200" ]]; then
        echo "  ✅ Valid secret accepted (200)"
    else
        echo "  ⚠️  Expected 200, got $RESPONSE (might be expected if models not ready)"
    fi
else
    echo "  ⚠️  TINYINTENT_SECRET not set, skipping valid auth test"
fi

# Test 4: Readiness endpoint (should be public)
echo ""
echo "🧪 Test 4: Public readiness endpoint"
RESPONSE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE_URL/readyz")

if [[ "$RESPONSE" == "200" ]]; then
    echo "  ✅ Readiness endpoint accessible without auth (200)"
else
    echo "  ❌ Expected 200, got $RESPONSE"
    ((ERRORS++))
fi

echo ""

# Summary
if [[ $ERRORS -eq 0 ]]; then
    echo "✅ Authentication tests passed!"
else
    echo "❌ Authentication tests failed with $ERRORS errors."
    exit 1
fi