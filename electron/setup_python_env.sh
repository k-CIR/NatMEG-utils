#!/bin/bash
# Setup Python virtual environment with all dependencies

set -e

VENV_DIR="resources/python_env"

echo "Creating Python virtual environment..."

# Create virtual environment
python3 -m venv "$VENV_DIR"

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Upgrade pip
pip install --upgrade pip uv

# Install dependencies from requirements.txt
echo "Installing Python dependencies..."
uv pip install -r ../requirements.txt

echo "Python environment setup complete: $VENV_DIR"
echo ""
echo "To activate this environment manually, run:"
echo "  source $VENV_DIR/bin/activate"
