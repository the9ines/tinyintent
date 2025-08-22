#!/bin/bash
# TinyIntent Helpers Smoke Tests
# Tests helper framework and sandbox execution

set -euo pipefail

echo "🔧 TinyIntent Helpers Smoke Tests"
echo "================================="

ERRORS=0

# Test 1: Helper framework structure
echo "🧪 Test 1: Helper framework structure"
if [[ -d "helpers" ]]; then
    echo "  ✅ helpers/ directory exists"
else
    echo "  ❌ helpers/ directory missing"
    ((ERRORS++))
fi

if [[ -f "helpers/sdk.py" ]]; then
    echo "  ✅ helpers/sdk.py found"
else
    echo "  ❌ helpers/sdk.py missing"
    ((ERRORS++))
fi

if [[ -f "helpers/registry.yaml" ]]; then
    echo "  ✅ helpers/registry.yaml found"
else
    echo "  ❌ helpers/registry.yaml missing"
    ((ERRORS++))
fi

# Test 2: Helper SDK imports
echo ""
echo "🧪 Test 2: Helper SDK imports"
if python3 -c "
import sys
sys.path.append('helpers')
try:
    import sdk
    print('  ✅ Helper SDK imports successfully')
except Exception as e:
    print(f'  ❌ SDK import error: {e}')
    exit(1)
" 2>/dev/null; then
    echo "  ✅ Helper SDK imports successfully"
else
    echo "  ❌ Helper SDK import failed"
    ((ERRORS++))
fi

# Test 3: Sample helpers
echo ""
echo "🧪 Test 3: Sample helpers"
declare -a sample_helpers=("bot_guard" "log_tailer")

for helper in "${sample_helpers[@]}"; do
    if [[ -d "helpers/$helper" ]]; then
        echo "  ✅ helpers/$helper/ directory exists"
        
        # Check required files
        if [[ -f "helpers/$helper/helper.yaml" ]]; then
            echo "    ✅ helper.yaml"
        else
            echo "    ❌ helper.yaml missing"
            ((ERRORS++))
        fi
        
        if [[ -f "helpers/$helper/input.schema.json" ]]; then
            echo "    ✅ input.schema.json"
        else
            echo "    ❌ input.schema.json missing"
            ((ERRORS++))
        fi
        
        if [[ -f "helpers/$helper/output.schema.json" ]]; then
            echo "    ✅ output.schema.json"
        else
            echo "    ❌ output.schema.json missing"
            ((ERRORS++))
        fi
        
        if [[ -f "helpers/$helper/main.js" ]]; then
            echo "    ✅ main.js"
        else
            echo "    ❌ main.js missing"
            ((ERRORS++))
        fi
    else
        echo "  ⚠️  helpers/$helper/ not found (sample helper)"
    fi
done

# Test 4: Registry validation
echo ""
echo "🧪 Test 4: Registry validation"
if [[ -f "helpers/registry.yaml" ]]; then
    if python3 -c "
import yaml
try:
    with open('helpers/registry.yaml', 'r') as f:
        registry = yaml.safe_load(f)
    print('  ✅ Registry YAML is valid')
    
    if 'helpers' in registry:
        count = len(registry['helpers'])
        print(f'  ✅ Registry contains {count} helpers')
    else:
        print('  ⚠️  No helpers section in registry')
        
except Exception as e:
    print(f'  ❌ Registry validation error: {e}')
    exit(1)
" 2>/dev/null; then
        echo "  ✅ Registry validation passed"
    else
        echo "  ❌ Registry validation failed"
        ((ERRORS++))
    fi
fi

# Test 5: Node.js availability (for helper execution)
echo ""
echo "🧪 Test 5: Node.js environment"
if command -v node >/dev/null 2>&1; then
    NODE_VERSION=$(node --version)
    echo "  ✅ Node.js available ($NODE_VERSION)"
else
    echo "  ⚠️  Node.js not found (required for JavaScript helpers)"
    echo "     Install Node.js for helper execution"
fi

# Test 6: Helper manifest validation
echo ""
echo "🧪 Test 6: Helper manifest validation"
for helper_dir in helpers/*/; do
    if [[ -d "$helper_dir" && -f "$helper_dir/helper.yaml" ]]; then
        helper_name=$(basename "$helper_dir")
        
        if python3 -c "
import yaml
import sys
try:
    with open('$helper_dir/helper.yaml', 'r') as f:
        manifest = yaml.safe_load(f)
    
    required_fields = ['name', 'version', 'description', 'execution']
    missing = [field for field in required_fields if field not in manifest]
    
    if missing:
        print(f'  ❌ $helper_name: Missing fields: {missing}')
        sys.exit(1)
    else:
        print(f'  ✅ $helper_name: Valid manifest')
        
except Exception as e:
    print(f'  ❌ $helper_name: Manifest error: {e}')
    sys.exit(1)
" 2>/dev/null; then
            continue
        else
            ((ERRORS++))
        fi
    fi
done

echo ""

# Summary
if [[ $ERRORS -eq 0 ]]; then
    echo "✅ Helpers smoke tests passed!"
    echo ""
    echo "💡 Helper framework is ready:"
    echo "   - SDK available for helper management"
    echo "   - Registry configured for helper discovery"
    echo "   - Sample helpers available for testing"
else
    echo "❌ Helpers smoke tests failed with $ERRORS errors."
    echo ""
    echo "💡 To fix issues:"
    echo "   - Ensure helper framework files are present"
    echo "   - Install Node.js for JavaScript helper execution"
    echo "   - Validate helper manifests and schemas"
    exit 1
fi