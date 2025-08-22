#!/bin/bash
set -e

echo "🎯 Installing TinyIntent..."

# Check Python version
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
required_version="3.9"

if python3 -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)"; then
    echo "✅ Python $python_version detected"
else
    echo "❌ Python 3.9+ required, found $python_version"
    exit 1
fi

# Install in development mode
echo "📦 Installing TinyIntent package..."
pip3 install -e .

# Verify installation
echo "🧪 Testing installation..."
if command -v tinyintent >/dev/null 2>&1; then
    echo "✅ TinyIntent CLI installed successfully"
    echo ""
    echo "🎉 Installation complete!"
    echo ""
    echo "📋 Quick Start:"
    echo "  tinyintent          # Start TinyIntent server"
    echo "  tinyintent status   # Show system status"
    echo "  tinyintent --help   # Show all options"
    echo ""
    echo "📱 iPhone Shortcut:"
    echo "  URL: http://YOUR_IP:8787/shortcut/route"
    echo "  Header: X-Shortcut-Token: tinyintent-shortcut-token-123"
else
    echo "❌ Installation failed - tinyintent command not found"
    exit 1
fi