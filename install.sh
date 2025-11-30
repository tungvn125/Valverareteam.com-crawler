#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

echo "Installing dependencies for Web Novel Scraper..."
echo ""

# --- Check if Python is installed and is version 3.8 or higher ---
PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "Error: Python 3.8 or higher is not found on your system."
    echo "Please install it from https://www.python.org/downloads/"
    read -p "Press Enter to exit..."
    exit 1
fi

PYTHON_VERSION=$("$PYTHON_CMD" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
IFS='.' read -r -a VERSION_PARTS <<< "$PYTHON_VERSION"
MAJOR=${VERSION_PARTS[0]}
MINOR=${VERSION_PARTS[1]}

if [[ "$MAJOR" -lt 3 ]] || ([[ "$MAJOR" -eq 3 ]] && [[ "$MINOR" -lt 8 ]]); then
    echo "Error: Python version ${PYTHON_VERSION} found. This project requires Python 3.8 or higher."
    echo "Please install a compatible version from https://www.python.org/downloads/"
    read -p "Press Enter to exit..."
    exit 1
fi

echo "Compatible Python version ($PYTHON_CMD $PYTHON_VERSION) found."
echo ""

# --- Create virtual environment ---
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in '$VENV_DIR'..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    echo "Virtual environment created successfully."
else
    echo "Virtual environment '$VENV_DIR' already exists. Skipping creation."
fi
echo ""

# Define path to the virtual environment's Python executable
VENV_PYTHON="$VENV_DIR/bin/python"

# --- Upgrade pip to the latest version in the venv ---
echo "Upgrading pip in the virtual environment..."
"$VENV_PYTHON" -m pip install --upgrade pip
echo ""

# --- Install required Python packages into the venv ---
echo "Installing required Python packages from requirements.txt..."
"$VENV_PYTHON" -m pip install -r requirements.txt
echo ""

# --- Install Playwright browsers ---
echo "Installing Playwright browsers..."
"$VENV_PYTHON" -m playwright install chromium
echo ""

# --- Note about fonts ---
echo "Note: The scraper is now configured to automatically download required fonts (e.g., DejaVuSans) if they are missing."
echo "If you encounter font issues, please ensure you have an active internet connection when running the scraper for the first time."
echo ""

# --- Instructions to run ---
echo "--------------------------------------------------"
echo "Installation complete!"
echo ""
echo "To run the scraper, follow these steps:"
echo "1. Activate the virtual environment: source $VENV_DIR/bin/activate"
echo "2. Run the scraper script:         python scraper.py"
echo "3. When you are finished, deactivate: deactivate"
echo "--------------------------------------------------"
echo ""
read -p "Press Enter to exit..."
exit 0