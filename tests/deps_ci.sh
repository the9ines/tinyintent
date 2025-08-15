#!/bin/bash
set -euo pipefail

echo "=== Dependency Resolution Tests ==="

# Get project root
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "${SMOKE_MODE:-}" == "ci" ]]; then
    echo "Running CI-safe dependency tests..."
    
    # Simulate missing ollama by setting restricted PATH and no OLLAMA_BIN
    echo -n "Test: Resolver with no ollama in PATH... "
    
    RESULT=$(cd "$PROJECT_ROOT" && PATH="/usr/bin:/bin" OLLAMA_BIN="" python3 -c "
import sys
sys.path.insert(0, 'bridge')
from resolve import resolve_ollama_path
path, tried = resolve_ollama_path()
if path is None:
    print('PASS - correctly reports None when ollama not found')
    sys.exit(0)
else:
    print(f'FAIL - expected None but got: {path}')
    sys.exit(1)
" 2>/dev/null)
    
    echo "$RESULT"
    
    # Test with OLLAMA_BIN override
    echo -n "Test: Resolver with OLLAMA_BIN override... "
    
    FAKE_OLLAMA_PATH="/fake/path/to/ollama"
    RESULT=$(cd "$PROJECT_ROOT" && OLLAMA_BIN="$FAKE_OLLAMA_PATH" python3 -c "
import sys
sys.path.insert(0, 'bridge')
from resolve import resolve_ollama_path
path, tried = resolve_ollama_path()
if '$FAKE_OLLAMA_PATH' in tried:
    print('PASS - OLLAMA_BIN was tried first')
    sys.exit(0)
else:
    print(f'FAIL - OLLAMA_BIN not in tried paths: {tried}')
    sys.exit(1)
" 2>/dev/null)
    
    echo "$RESULT"
    
else
    echo "Running local dependency tests..."
    
    # Just run the resolver and print the chosen path (non-fatal)
    echo -n "Local ollama resolution: "
    
    RESOLVER_OUTPUT=$(cd "$PROJECT_ROOT" && python3 -c "
import sys
sys.path.insert(0, 'bridge')
from resolve import resolve_ollama_path
path, tried = resolve_ollama_path()
print(f'Path: {path or \"Not found\"}')
print(f'Tried: {tried}')
" 2>/dev/null || echo "Error running resolver")
    
    echo "$RESOLVER_OUTPUT"
    
    # Test check_ollama_ok function
    echo -n "Ollama availability check: "
    
    CHECK_OUTPUT=$(cd "$PROJECT_ROOT" && python3 -c "
import sys
sys.path.insert(0, 'bridge')
from resolve import resolve_ollama_path, check_ollama_ok
path, tried = resolve_ollama_path()
if path:
    ok, reason = check_ollama_ok(path)
    print(f'OK: {ok}, Reason: {reason}')
else:
    print('No ollama path to check')
" 2>/dev/null || echo "Error checking ollama")
    
    echo "$CHECK_OUTPUT"
fi

echo "=== Dependency Tests Complete ==="