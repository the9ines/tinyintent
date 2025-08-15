#!/bin/bash
set -euo pipefail

PLIST_PATH="launchd/com.tinyintent.tinyrpc.plist"

echo "=== TinyIntent Doctor ==="
echo

# Check if plist exists
if [[ ! -f "$PLIST_PATH" ]]; then
    echo "Error: Plist not found at $PLIST_PATH"
    echo "Copy from sample: cp launchd/com.tinyintent.tinyrpc.sample.plist $PLIST_PATH"
    exit 1
fi

# 1. Launchd PATH from plist
echo "1. Launchd PATH:"
PLIST_PATH_VAL=$(/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:PATH" "$PLIST_PATH" 2>/dev/null || echo "not_set")
echo "   $PLIST_PATH_VAL"

# 2. OLLAMA_BIN from plist (if any)
echo
echo "2. OLLAMA_BIN from plist:"
PLIST_OLLAMA_BIN=$(/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:OLLAMA_BIN" "$PLIST_PATH" 2>/dev/null || echo "not_set")
echo "   $PLIST_OLLAMA_BIN"

# 3. Resolver results (call Python resolver)
echo
echo "3. Resolver results:"
cd "$(dirname "$0")/.."
RESOLVER_RESULT=$(python3 -c "
import sys
sys.path.insert(0, 'bridge')
from resolve import resolve_ollama_path
path, tried = resolve_ollama_path()
print(f'Resolved path: {path or \"None\"}')
print(f'Tried paths: {tried}')
" 2>/dev/null || echo "Error running resolver")
echo "   $RESOLVER_RESULT"

# 4. Ollama version using resolved path
echo
echo "4. Ollama version check:"
OLLAMA_PATH=$(python3 -c "
import sys
sys.path.insert(0, 'bridge')
from resolve import resolve_ollama_path
path, tried = resolve_ollama_path()
print(path or '')
" 2>/dev/null || echo "")

if [[ -n "$OLLAMA_PATH" ]] && [[ -x "$OLLAMA_PATH" ]]; then
    VERSION_OUTPUT=$("$OLLAMA_PATH" --version 2>&1 || echo "Failed to get version")
    echo "   Using: $OLLAMA_PATH"
    echo "   Version: $VERSION_OUTPUT"
else
    echo "   Ollama not found or not executable"
fi

# 5. Ollama list (non-fatal if fails)
echo
echo "5. Available models (first 20):"
if [[ -n "$OLLAMA_PATH" ]] && [[ -x "$OLLAMA_PATH" ]]; then
    MODEL_LIST=$("$OLLAMA_PATH" list 2>/dev/null | head -n 20 || echo "Failed to list models (service may be down)")
    echo "$MODEL_LIST" | sed 's/^/   /'
else
    echo "   Cannot check models - ollama not available"
fi

# Actionable hints
echo
echo "=== ACTIONABLE HINTS ==="
echo

if [[ "$PLIST_OLLAMA_BIN" == "not_set" ]] && [[ -z "$OLLAMA_PATH" ]]; then
    echo "ISSUE: Ollama not found"
    echo
    echo "Fix 1 - Set OLLAMA_BIN in plist:"
    echo "   /usr/libexec/PlistBuddy -c \"Add :EnvironmentVariables:OLLAMA_BIN string /opt/homebrew/bin/ollama\" $PLIST_PATH"
    echo
    echo "Fix 2 - Extend PATH in plist (if ollama is in non-standard location):"
    echo "   /usr/libexec/PlistBuddy -c \"Set :EnvironmentVariables:PATH /opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin\" $PLIST_PATH"
    echo
elif [[ "$PLIST_OLLAMA_BIN" != "not_set" ]] && [[ ! -x "$PLIST_OLLAMA_BIN" ]]; then
    echo "ISSUE: OLLAMA_BIN is set but path is invalid: $PLIST_OLLAMA_BIN"
    echo
    echo "Fix - Update OLLAMA_BIN to correct path:"
    echo "   /usr/libexec/PlistBuddy -c \"Set :EnvironmentVariables:OLLAMA_BIN /opt/homebrew/bin/ollama\" $PLIST_PATH"
    echo
else
    echo "✓ Ollama resolution looks good"
    echo
fi

echo "After making changes, restart the bridge:"
echo "   make bridge-stop && make bridge && make bridge-logs"