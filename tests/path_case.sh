#!/bin/bash
set -euo pipefail

# Path case consistency check - ensures no tracked file contains capital P in Projects path
echo "=== Path Case Consistency Check ==="

# Get all tracked files
TRACKED_FILES=$(git ls-files)

VIOLATIONS=0

# Check each tracked file for capital P in Projects path
while IFS= read -r file; do
    # Skip binary files
    if ! file "$file" | grep -q "text"; then
        continue
    fi
    
    # Check for /Users/oberfelder/Projects/ (capital P)
    if grep -InE '/Users/oberfelder/Projects/' "$file" 2>/dev/null; then
        echo "VIOLATION: Capital P in Projects path found in $file"
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
    
done <<< "$TRACKED_FILES"

if [[ $VIOLATIONS -gt 0 ]]; then
    echo ""
    echo "❌ PATH CASE CHECK FAILED: Found $VIOLATIONS violation(s)"
    echo ""
    echo "All paths should use lowercase 'projects', not 'Projects'"
    echo "Standard path: /Users/oberfelder/projects/smallintent"
    echo ""
    echo "To fix:"
    echo "  1. Replace all instances of '/Users/oberfelder/Projects/' with '/Users/oberfelder/projects/'"
    echo "  2. Use dynamic project root detection instead of hardcoded paths where possible"
    echo ""
    exit 1
else
    echo "✅ PATH CASE CHECK PASSED: No capital P in Projects paths detected"
fi