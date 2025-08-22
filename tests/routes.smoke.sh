#!/bin/bash
# TinyIntent Route Tests
# Smoke tests for bridge routing endpoints

set -euo pipefail

echo "🚀 TinyIntent Route Smoke Tests"
echo "==============================="

BASE_URL="http://localhost:8787"
ERRORS=0

# Check authentication
if [[ -z "${TINYINTENT_SECRET:-}" ]]; then
    echo "❌ TINYINTENT_SECRET not set"
    echo "   Run: source .env or export TINYINTENT_SECRET=your_secret"
    exit 1
fi

# Check if bridge is running
if ! curl -s "$BASE_URL/readyz" >/dev/null 2>&1; then
    echo "❌ Bridge not running at $BASE_URL"
    echo "   Start with: make bridgesrv"
    exit 1
fi

echo "✅ Bridge is running with authentication"
echo ""

# Test 1: Route endpoint with gen
echo "🧪 Test 1: Gen route"
RESPONSE=$(curl -s -X POST "$BASE_URL/route" \
    -H "Content-Type: application/json" \
    -H "X-TinyIntent-Secret: $TINYINTENT_SECRET" \
    -d '{"text": "Write me a haiku about testing", "route": "gen"}')

if echo "$RESPONSE" | jq -e .response >/dev/null 2>&1; then
    echo "  ✅ Gen route returned valid JSON response"
else
    echo "  ⚠️  Gen route response: $RESPONSE"
    echo "      (May be expected if Ollama models not ready)"
fi

# Test 2: Route endpoint with act
echo ""
echo "🧪 Test 2: Act route (preview mode)"
RESPONSE=$(curl -s -X POST "$BASE_URL/route" \
    -H "Content-Type: application/json" \
    -H "X-TinyIntent-Secret: $TINYINTENT_SECRET" \
    -d '{"text": "Close my trading position", "route": "act"}')

if echo "$RESPONSE" | jq -e .preview >/dev/null 2>&1; then
    echo "  ✅ Act route returned preview response"
else
    echo "  ⚠️  Act route response: $RESPONSE"
fi

# Test 3: Invalid route parameter
echo ""
echo "🧪 Test 3: Invalid route parameter"
RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/route_response.json -X POST "$BASE_URL/route" \
    -H "Content-Type: application/json" \
    -H "X-TinyIntent-Secret: $TINYINTENT_SECRET" \
    -d '{"text": "test", "route": "invalid"}')

if [[ "$RESPONSE" == "400" ]]; then
    echo "  ✅ Invalid route properly rejected (400)"
else
    echo "  ❌ Expected 400, got $RESPONSE"
    echo "  Response: $(cat /tmp/route_response.json)"
    ((ERRORS++))
fi

# Test 4: Missing required fields
echo ""
echo "🧪 Test 4: Missing required fields"
RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/route_response.json -X POST "$BASE_URL/route" \
    -H "Content-Type: application/json" \
    -H "X-TinyIntent-Secret: $TINYINTENT_SECRET" \
    -d '{"route": "gen"}')

if [[ "$RESPONSE" == "400" ]]; then
    echo "  ✅ Missing text field properly rejected (400)"
else
    echo "  ❌ Expected 400, got $RESPONSE"
    echo "  Response: $(cat /tmp/route_response.json)"
    ((ERRORS++))
fi

# Test 5: Feedback endpoint
echo ""
echo "🧪 Test 5: Feedback endpoint"
RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/feedback_response.json -X POST "$BASE_URL/feedback" \
    -H "Content-Type: application/json" \
    -H "X-TinyIntent-Secret: $TINYINTENT_SECRET" \
    -d '{"session_id": "test-session", "feedback": "Great response!"}')

if [[ "$RESPONSE" == "200" ]]; then
    echo "  ✅ Feedback endpoint working (200)"
else
    echo "  ⚠️  Feedback endpoint returned $RESPONSE"
    echo "  Response: $(cat /tmp/feedback_response.json)"
fi

# Cleanup
rm -f /tmp/route_response.json /tmp/feedback_response.json

echo ""

# Summary
if [[ $ERRORS -eq 0 ]]; then
    echo "✅ Route smoke tests passed!"
else
    echo "❌ Route smoke tests failed with $ERRORS errors."
    exit 1
fi