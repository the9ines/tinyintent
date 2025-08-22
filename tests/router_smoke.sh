#!/bin/bash
# TinyIntent Router Smoke Tests
# Tests router training and inference capabilities

set -euo pipefail

echo "🧠 TinyIntent Router Smoke Tests"
echo "================================"

ERRORS=0

# Test 1: Training data exists
echo "🧪 Test 1: Training data availability"
if [[ -f "router/data/intents_bootstrap.tsv" ]]; then
    LINES=$(wc -l < "router/data/intents_bootstrap.tsv")
    echo "  ✅ Bootstrap training data found ($LINES lines)"
elif [[ -f "router/data/intents.tsv" ]]; then
    LINES=$(wc -l < "router/data/intents.tsv")
    echo "  ✅ Training data found ($LINES lines)"
else
    echo "  ❌ No training data found"
    echo "     Expected: router/data/intents_bootstrap.tsv or router/data/intents.tsv"
    ((ERRORS++))
fi

# Test 2: Python training pipeline
echo ""
echo "🧪 Test 2: Python training pipeline"
if [[ -f "router/weights/train_router.py" ]]; then
    echo "  ✅ Python training script found"
    
    # Test imports
    if python3 -c "
import sys
sys.path.append('router/weights')
try:
    import train_router
    print('  ✅ Training script imports successfully')
except Exception as e:
    print(f'  ❌ Import error: {e}')
    exit(1)
" 2>/dev/null; then
        echo "  ✅ Training script imports successfully"
    else
        echo "  ❌ Training script import failed"
        ((ERRORS++))
    fi
else
    echo "  ❌ Python training script not found at router/weights/train_router.py"
    ((ERRORS++))
fi

# Test 3: Swift training script (legacy)
echo ""
echo "🧪 Test 3: Swift training script (legacy)"
if [[ -f "router/train_router.swift" ]]; then
    echo "  ✅ Swift training script found"
    
    # Check Swift availability
    if command -v swift >/dev/null 2>&1; then
        echo "  ✅ Swift compiler available"
    else
        echo "  ❌ Swift compiler not found"
        ((ERRORS++))
    fi
else
    echo "  ⚠️  Swift training script not found (expected for Python-first approach)"
fi

# Test 4: Model directory structure
echo ""
echo "🧪 Test 4: Model directory structure"
if [[ -d "router/weights" ]]; then
    echo "  ✅ router/weights/ directory exists"
else
    echo "  ❌ router/weights/ directory missing"
    ((ERRORS++))
fi

if [[ -d "router/train" ]]; then
    echo "  ✅ router/train/ directory exists"
else
    echo "  ⚠️  router/train/ directory missing"
fi

# Test 5: Check for trained models
echo ""
echo "🧪 Test 5: Trained models"
if [[ -f "router/SmallIntent.mlmodel" ]]; then
    SIZE=$(ls -lh "router/SmallIntent.mlmodel" | awk '{print $5}')
    echo "  ✅ SmallIntent.mlmodel found ($SIZE)"
else
    echo "  ⚠️  SmallIntent.mlmodel not found (run 'make router-train' to create)"
fi

if [[ -f "router/weights/trained_model/pytorch_model.bin" ]]; then
    echo "  ✅ PyTorch trained model found"
elif [[ -d "router/weights/trained_model" ]]; then
    echo "  ⚠️  Trained model directory exists but no PyTorch model"
else
    echo "  ⚠️  No trained PyTorch model found"
fi

# Test 6: Training dependencies
echo ""
echo "🧪 Test 6: Training dependencies"
python3 -c "
required = ['torch', 'transformers', 'sklearn', 'pandas', 'numpy']
optional = ['onnx', 'onnxruntime', 'coremltools']

import sys
errors = 0

for module in required:
    try:
        __import__(module)
        print(f'  ✅ {module}')
    except ImportError:
        print(f'  ❌ {module} (required)')
        errors += 1

for module in optional:
    try:
        __import__(module)
        print(f'  ✅ {module} (optional)')
    except ImportError:
        print(f'  ⚠️  {module} (optional, missing)')

if errors > 0:
    print(f'\\n❌ {errors} required dependencies missing')
    print('   Run: pip install -r requirements.txt')
    sys.exit(1)
"

if [[ $? -ne 0 ]]; then
    ((ERRORS++))
fi

echo ""

# Summary
if [[ $ERRORS -eq 0 ]]; then
    echo "✅ Router smoke tests passed!"
    echo ""
    echo "💡 Next steps:"
    echo "   - Run 'make router-train' to train the model"
    echo "   - Run 'make router-eval' to evaluate performance"
else
    echo "❌ Router smoke tests failed with $ERRORS errors."
    echo ""
    echo "💡 To fix issues:"
    echo "   - Install dependencies: pip install -r requirements.txt"
    echo "   - Create training data: router/data/intents_bootstrap.tsv"
    echo "   - Run setup: make setup"
    exit 1
fi