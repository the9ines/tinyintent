#!/bin/bash
set -euo pipefail

# Secrets guard - prevents live secrets from being committed to repo
# Checks for:
# - 48-128 char hex strings (potential tokens)
# - TINYINTENT_SECRET key name
# - X-TinyIntent-Secret header literals (outside of allowed files)

echo "=== Secrets Guard ==="

# Get all tracked files
TRACKED_FILES=$(git ls-files)

# Allowlist patterns for files that can mention header names (but not values)
ALLOWLIST_PATTERNS=(
    "^launchd/com\.tinyintent\.tinyrpc\.sample\.plist$"
    "^docs/.*\.md$"
    "^tests/.*\.sh$"
    "^README\.md$"
    "^claude\.md$"
)

# Check if file is in allowlist
is_allowed() {
    local file="$1"
    for pattern in "${ALLOWLIST_PATTERNS[@]}"; do
        if echo "$file" | grep -qE "$pattern"; then
            return 0
        fi
    done
    return 1
}

VIOLATIONS=0

# Check each tracked file
while IFS= read -r file; do
    # Skip binary files
    if ! file "$file" | grep -q "text"; then
        continue
    fi
    
    # Check for hex strings that look like tokens (48-128 chars)
    if grep -InE '[a-fA-F0-9]{48,128}' "$file" 2>/dev/null; then
        if ! is_allowed "$file"; then
            echo "VIOLATION: Potential token found in $file"
            VIOLATIONS=$((VIOLATIONS + 1))
        else
            # Even in allowed files, warn about potential values
            if grep -InE '[a-fA-F0-9]{64,128}' "$file" 2>/dev/null; then
                echo "WARNING: Long hex string in allowed file $file (verify it's not a real secret)"
            fi
        fi
    fi
    
    # Check for TINYINTENT_SECRET key name
    if grep -InE 'TINYINTENT_SECRET.*[a-fA-F0-9]{20,}' "$file" 2>/dev/null; then
        if ! is_allowed "$file"; then
            echo "VIOLATION: TINYINTENT_SECRET with value found in $file"
            VIOLATIONS=$((VIOLATIONS + 1))
        fi
    fi
    
    # Check for X-TinyIntent-Secret header with values
    if grep -InE 'X-TinyIntent-Secret.*[a-fA-F0-9]{20,}' "$file" 2>/dev/null; then
        if ! is_allowed "$file"; then
            echo "VIOLATION: X-TinyIntent-Secret header with value found in $file"
            VIOLATIONS=$((VIOLATIONS + 1))
        fi
    fi
    
done <<< "$TRACKED_FILES"

if [[ $VIOLATIONS -gt 0 ]]; then
    echo ""
    echo "❌ SECRETS GUARD FAILED: Found $VIOLATIONS violation(s)"
    echo ""
    echo "To fix:"
    echo "  1. Remove any live secrets from the files above"
    echo "  2. Use CHANGE_ME_SECRET or similar placeholders instead"
    echo "  3. Rotate any secrets that may have been exposed"
    echo "  4. Use 'bash scripts/rotate_secret.sh' to generate new secrets"
    echo ""
    exit 1
else
    echo "✅ SECRETS GUARD PASSED: No live secrets detected"
fi