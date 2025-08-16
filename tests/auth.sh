#!/bin/bash
set -euo pipefail

PLIST_PATH="launchd/com.tinyintent.tinyrpc.plist"
BASE_URL="http://127.0.0.1:8787"

echo "=== Auth Tests ==="

# Read current secret from plist
CURRENT_SECRET=""
if [[ -f "$PLIST_PATH" ]]; then
    CURRENT_SECRET=$(/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:TINYINTENT_SECRET" "$PLIST_PATH" 2>/dev/null || echo "")
fi

if [[ -z "$CURRENT_SECRET" ]]; then
    echo "SKIP: No secret configured in plist"
    exit 0
fi

echo "Found secret in plist (length: ${#CURRENT_SECRET})"

# Test 1: Mismatch - send wrong secret
echo -n "Test 1 (mismatch): "
WRONG_SECRET="${CURRENT_SECRET}wrong"
RESPONSE=$(curl -s -X POST "$BASE_URL/route" \
    -H "Content-Type: application/json" \
    -H "X-TinyIntent-Secret: $WRONG_SECRET" \
    -d '{"text":"test","route":"local_only"}' || echo '{"error":"connection_failed"}')

if echo "$RESPONSE" | grep -q '"code":"mismatch"'; then
    echo "PASS"
else
    echo "FAIL - Expected mismatch code, got: $RESPONSE"
fi

# Test 2: Missing header
echo -n "Test 2 (missing header): "
RESPONSE=$(curl -s -X POST "$BASE_URL/route" \
    -H "Content-Type: application/json" \
    -d '{"text":"test","route":"local_only"}' || echo '{"error":"connection_failed"}')

if echo "$RESPONSE" | grep -q '"code":"missing_header"' || echo "$RESPONSE" | grep -q '"code":"secret_not_configured"'; then
    echo "PASS"
else
    echo "FAIL - Expected missing_header or secret_not_configured, got: $RESPONSE"
fi

# Test 3: Dev bypass (CI-safe toggle)
echo -n "Test 3 (dev bypass): "

# Store original ALLOW_DEV_LOCAL value
ORIGINAL_DEV_LOCAL=$(/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:ALLOW_DEV_LOCAL" "$PLIST_PATH" 2>/dev/null || echo "0")

# Temporarily set ALLOW_DEV_LOCAL=1
/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:ALLOW_DEV_LOCAL 1" "$PLIST_PATH" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:ALLOW_DEV_LOCAL string 1" "$PLIST_PATH"

# Restart bridge
make bridge-stop >/dev/null 2>&1 || true
make bridge >/dev/null 2>&1
sleep 2

# Test request without header (should pass due to dev bypass)
RESPONSE=$(curl -s -X POST "$BASE_URL/route" \
    -H "Content-Type: application/json" \
    -d '{"text":"test","route":"local_only"}' || echo '{"error":"connection_failed"}')

# Restore original ALLOW_DEV_LOCAL
if [[ "$ORIGINAL_DEV_LOCAL" == "0" ]]; then
    /usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:ALLOW_DEV_LOCAL 0" "$PLIST_PATH" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:ALLOW_DEV_LOCAL string 0" "$PLIST_PATH"
else
    /usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:ALLOW_DEV_LOCAL $ORIGINAL_DEV_LOCAL" "$PLIST_PATH"
fi

# Restart bridge again to apply original setting
make bridge-stop >/dev/null 2>&1 || true
make bridge >/dev/null 2>&1
sleep 2

# Check if response indicates success (not 401)
if echo "$RESPONSE" | grep -q '"error":"unauthorized"'; then
    echo "FAIL - Dev bypass didn't work, got: $RESPONSE"
else
    echo "PASS"
fi

# Test 4: Debug endpoint from localhost
echo -n "Test 4 (debug endpoint): "
DEBUG_RESPONSE=$(curl -s "$BASE_URL/debug/authz" || echo '{"error":"connection_failed"}')

if echo "$DEBUG_RESPONSE" | grep -q '"client_ip"' && echo "$DEBUG_RESPONSE" | grep -q '"has_header"' && echo "$DEBUG_RESPONSE" | grep -q '"would_allow"'; then
    echo "PASS"
else
    echo "FAIL - Expected debug endpoint JSON with required keys, got: $DEBUG_RESPONSE"
fi

# Test 5: Dev bypass prevention with X-Forwarded-For
echo -n "Test 5 (dev bypass X-Forwarded-For prevention): "

# Store original ALLOW_DEV_LOCAL value
ORIGINAL_DEV_LOCAL=$(/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:ALLOW_DEV_LOCAL" "$PLIST_PATH" 2>/dev/null || echo "0")

# Temporarily set ALLOW_DEV_LOCAL=1
/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:ALLOW_DEV_LOCAL 1" "$PLIST_PATH" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:ALLOW_DEV_LOCAL string 1" "$PLIST_PATH"

# Restart bridge
make bridge-stop >/dev/null 2>&1 || true
make bridge >/dev/null 2>&1
sleep 2

# Test request with X-Forwarded-For header (should be rejected even in dev mode)
RESPONSE=$(curl -s -X POST "$BASE_URL/route" \
    -H "Content-Type: application/json" \
    -H "X-Forwarded-For: 1.2.3.4" \
    -d '{"text":"test","route":"local_only"}' || echo '{"error":"connection_failed"}')

# Restore original ALLOW_DEV_LOCAL
if [[ "$ORIGINAL_DEV_LOCAL" == "0" ]]; then
    /usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:ALLOW_DEV_LOCAL 0" "$PLIST_PATH" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:ALLOW_DEV_LOCAL string 0" "$PLIST_PATH"
else
    /usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:ALLOW_DEV_LOCAL $ORIGINAL_DEV_LOCAL" "$PLIST_PATH"
fi

# Restart bridge again
make bridge-stop >/dev/null 2>&1 || true
make bridge >/dev/null 2>&1
sleep 2

# Check if response indicates unauthorized (should be rejected due to X-Forwarded-For)
if echo "$RESPONSE" | grep -q '"error":"unauthorized"'; then
    echo "PASS"
else
    echo "FAIL - X-Forwarded-For bypass prevention failed, got: $RESPONSE"
fi

# Test 6: Valid secret (should work)
echo -n "Test 6 (valid secret): "
RESPONSE=$(curl -s -X POST "$BASE_URL/route" \
    -H "Content-Type: application/json" \
    -H "X-TinyIntent-Secret: $CURRENT_SECRET" \
    -d '{"text":"test","route":"local_only"}' || echo '{"error":"connection_failed"}')

if echo "$RESPONSE" | grep -q '"error":"unauthorized"'; then
    echo "FAIL - Valid secret was rejected, got: $RESPONSE"
else
    echo "PASS"
fi

echo "=== Auth Tests Complete ==="