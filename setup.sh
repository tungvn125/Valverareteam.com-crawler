#!/bin/bash

# setup.sh - Setup script for Valverareteam.com crawler
# Creates virtual environment, installs dependencies, adds shell alias

set -e  # Exit on error

echo "=== Valverareteam.com Crawler Setup ==="

# Check for Python3
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 is not installed. Please install Python 3.8+."
    exit 1
fi

# Check if uv is available, otherwise use standard python/pip
USE_UV=false
if command uv self version &> /dev/null; then
    USE_UV=true
    echo "Using uv for virtual environment management."
else
    echo "uv not found, using standard python venv and pip."
fi

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    if [ "$USE_UV" = true ]; then
        uv venv
    else
        python3 -m venv .venv
    fi
else
    echo "Virtual environment already exists."
fi

# Activate venv and install requirements
echo "Installing dependencies from requirements.txt..."
source .venv/bin/activate

if [ ! -f "requirements.txt" ]; then
    echo "ERROR: requirements.txt not found."
    exit 1
fi

if [ "$USE_UV" = true ]; then
    uv pip install --upgrade pip
    uv pip install -r requirements.txt
else
    pip install --upgrade pip
    pip install -r requirements.txt
fi

# Install Playwright browsers
echo "Installing Playwright browsers..."
python -m playwright install chromium-headless-shell

# Detect shell and add alias
SHELL_CONFIG=""
if [ -n "$ZSH_VERSION" ]; then
    SHELL_CONFIG="$HOME/.zshrc"
elif [ -n "$BASH_VERSION" ]; then
    SHELL_CONFIG="$HOME/.bashrc"
else
    # Fallback: try to detect from $SHELL environment variable
    case "$SHELL" in
        *zsh) SHELL_CONFIG="$HOME/.zshrc" ;;
        *bash) SHELL_CONFIG="$HOME/.bashrc" ;;
        *) SHELL_CONFIG="" ;;
    esac
fi

if [ -z "$SHELL_CONFIG" ]; then
    echo "WARNING: Could not detect shell (bash/zsh). Skipping alias setup."
    echo "You can manually add alias: vvrt='$(pwd)/.venv/bin/python $(pwd)/scraper.py'"
else
    ALIAS_LINE="alias vvrt='$(pwd)/.venv/bin/python $(pwd)/scraper.py'"

    # Ensure config file exists
    if [ ! -f "$SHELL_CONFIG" ]; then
        echo "Creating $SHELL_CONFIG..."
        touch "$SHELL_CONFIG"
    fi

    # Check if alias already exists
    if grep -q "alias vvrt=" "$SHELL_CONFIG" 2>/dev/null; then
        echo "Alias 'vvrt' already exists in $SHELL_CONFIG"
    else
        echo "Adding alias 'vvrt' to $SHELL_CONFIG"
        echo "" >> "$SHELL_CONFIG"
        echo "# Valverareteam.com crawler alias" >> "$SHELL_CONFIG"
        echo "$ALIAS_LINE" >> "$SHELL_CONFIG"
        echo "Alias added. Please run 'source $SHELL_CONFIG' or restart your shell."
    fi
fi

echo ""
echo "=== Setup Complete ==="
echo "Virtual environment: $(pwd)/.venv"
echo "To activate manually: source $(pwd)/.venv/bin/activate"
echo "To run scraper: vvrt"
echo ""
echo "Note: If alias doesn't work immediately, run: source $SHELL_CONFIG"
echo ""
echo "=== Testing ==="
echo "Test dependencies (pytest, pytest-asyncio) have been installed."
echo "Available test files:"
echo "  - tests/test_scraper.py"
echo "  - tests/test_tao_so_do_cay.py"
echo ""

# Only ask interactively if stdin is a terminal
if [ -t 0 ]; then
    read -p "Run tests now? (Y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
        echo "Running tests..."
        python -m pytest tests/ -v
        echo ""
        echo "Tests completed."
    else
        echo "Skipping tests. You can run them later with: python -m pytest tests/"
    fi
else
    echo "Non-interactive mode detected. Skipping test prompt."
    echo "You can run tests manually with: python -m pytest tests/"
fi