#!/bin/bash
set -euo pipefail

echo "=== Bind/Port Configuration Tests ==="

PLIST_PATH="launchd/com.tinyintent.tinyrpc.plist"

# Test 1: Verify healthz endpoint shows bind configuration
echo -n "Test 1 (healthz shows bind config): "

if command -v curl >/dev/null && pgrep -f tinyrpc.py >/dev/null; then
    HEALTH_RESPONSE=$(curl -s http://127.0.0.1:8787/healthz || echo '{"error":"connection_failed"}')
    
    if echo "$HEALTH_RESPONSE" | grep -q '"bind_host"' && echo "$HEALTH_RESPONSE" | grep -q '"bind_port"'; then
        echo "PASS"
    else
        echo "FAIL - Expected bind_host and bind_port in healthz response, got: $HEALTH_RESPONSE"
    fi
else
    echo "SKIP - Bridge not running or curl not available"
fi

# Test 2: Verify environment variables are being read correctly
echo -n "Test 2 (env vars check): "

# Get current values from plist
PLIST_BIND=$(/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:TINYINTENT_BIND" "$PLIST_PATH" 2>/dev/null || echo "127.0.0.1")
PLIST_PORT=$(/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:TINYINTENT_PORT" "$PLIST_PATH" 2>/dev/null || echo "8787")

if command -v curl >/dev/null && pgrep -f tinyrpc.py >/dev/null; then
    HEALTH_RESPONSE=$(curl -s http://127.0.0.1:8787/healthz 2>/dev/null || echo '{"error":"connection_failed"}')
    
    if echo "$HEALTH_RESPONSE" | grep -q "\"bind_host\":\"$PLIST_BIND\"" && echo "$HEALTH_RESPONSE" | grep -q "\"bind_port\":$PLIST_PORT"; then
        echo "PASS"
    else
        echo "FAIL - Expected bind_host=$PLIST_BIND and bind_port=$PLIST_PORT, got: $HEALTH_RESPONSE"
    fi
else
    echo "SKIP - Bridge not running or curl not available"
fi

# Test 3: Verify startup logging format
echo -n "Test 3 (startup logging): "

if [[ -f "bridge/logs/stderr.log" ]]; then
    # Check for the new startup log format
    if grep -q "listening host=.* port=" bridge/logs/stderr.log; then
        echo "PASS"
    else
        echo "FAIL - Expected startup log format not found in stderr.log"
    fi
else
    echo "SKIP - No stderr.log found"
fi

echo "=== Bind/Port Tests Complete ==="