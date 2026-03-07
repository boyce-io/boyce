#!/bin/bash
# DataShark MCP Installer
# One-command setup for DataShark framework

set -e

echo "============================================================"
echo "DataShark MCP v0.3.0 Installer"
echo "============================================================"
echo ""

# Detect Python
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "❌ Error: Python 3 not found"
    exit 1
fi

echo "✅ Python found: $($PYTHON --version)"
echo ""

# Get project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

echo "📦 Installing DataShark MCP..."
cd "$PROJECT_ROOT"

# Build wheel
echo "  Building wheel..."
$PYTHON -m pip install --upgrade build wheel
$PYTHON -m build --wheel

# Install
echo "  Installing package..."
$PYTHON -m pip install dist/datashark_mcp-*.whl

echo ""
echo "✅ Installation complete!"
echo ""

echo ""
echo "============================================================"
echo "✅ DataShark v0.3.0 installed successfully!"
echo ""
echo "Note:"
echo "  This installer only installs the Python package wheel."
echo "  It does not manage instances or start an MCP server in this repo layout."
echo "============================================================"
