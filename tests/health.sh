#!/bin/bash
# TinyIntent Health Check Tests
# Validates system components and readiness

set -euo pipefail

echo "🩺 TinyIntent Health Check"
echo "========================="

ERRORS=0

# Check project structure
echo "📁 Project Structure:"
for dir in bridge router data helpers scripts tests; do
    if [[ -d "$dir" ]]; then
        echo "  ✅ $dir/"
    else
        echo "  ❌ $dir/ (missing)"
        ((ERRORS++))
    fi
done

echo ""

# Check key files
echo "📄 Key Files:"
declare -a key_files=(
    "Makefile"
    "models.yaml"
    "requirements.txt"
    "bridge/selfheal.py"
    "router/weights/train_router.py"
)

for file in "${key_files[@]}"; do
    if [[ -f "$file" ]]; then
        echo "  ✅ $file"
    else
        echo "  ❌ $file (missing)"
        ((ERRORS++))
    fi
done

echo ""

# Check dependencies
echo "🔧 Dependencies:"
for cmd in python3 swift make curl; do
    if command -v "$cmd" >/dev/null 2>&1; then
        echo "  ✅ $cmd"
    else
        echo "  ❌ $cmd (missing)"
        ((ERRORS++))
    fi
done

echo ""

# Check Python imports
echo "🐍 Python Modules:"
python3 -c "
import sys
modules = ['json', 'pathlib', 'datetime', 'argparse']
optional = ['requests', 'torch', 'transformers']

for module in modules:
    try:
        __import__(module)
        print(f'  ✅ {module}')
    except ImportError:
        print(f'  ❌ {module} (missing)')
        
for module in optional:
    try:
        __import__(module)
        print(f'  ✅ {module} (optional)')
    except ImportError:
        print(f'  ⚠️  {module} (optional, missing)')
"

echo ""

# Summary
if [[ $ERRORS -eq 0 ]]; then
    echo "✅ Health check passed! TinyIntent scaffolding is ready."
    exit 0
else
    echo "❌ Health check failed with $ERRORS errors."
    echo ""
    echo "💡 To fix issues:"
    echo "   - Run: make setup"
    echo "   - Install missing dependencies"
    echo "   - Check project structure"
    exit 1
fi