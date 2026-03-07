#!/bin/bash
# Stop on error
set -e

echo "🦈 Initializing DataShark Dev Environment..."

# 1. Detect Python Version
# We prefer 3.11, then 3.10, then generic python3 (if it meets version reqs)
if command -v python3.11 &> /dev/null; then
    PY_EXEC="python3.11"
elif command -v python3.10 &> /dev/null; then
    PY_EXEC="python3.10"
else
    echo "⚠️  Modern Python (3.10/3.11) not found in path."
    echo "    Checking default python3 version..."
    PY_EXEC="python3"
    # Note: If this is 3.9, the pip install step will fail again, which is intended.
fi

echo "🔍 Using Python Executable: $PY_EXEC"
$PY_EXEC --version

# 2. Cleanup
echo "🧹 Cleaning up..."
rm -rf build dist *.egg-info .venv
find . -name "__pycache__" -exec rm -rf {} +

# 3. Create venv with SPECIFIC python version
echo "📦 Creating .venv..."
$PY_EXEC -m venv .venv
source .venv/bin/activate

# 4. Install
echo "🛠 Upgrading pip..."
pip install --upgrade pip setuptools wheel

echo "🔗 Installing DataShark (Editable)..."
pip install -e .

# 5. Verify
echo "✅ Verification: Running Smoke Test..."
datashark --help
