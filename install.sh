#!/bin/bash

echo "Installing dependencies for Web Novel Scraper..."

# --- Check if Python is installed and is version 3.8 or higher ---
PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "Error: Python 3.8 or higher is not installed! Please install it from https://www.python.org/downloads/"
    read -p "Press Enter to exit..."
    exit 1
fi

PYTHON_VERSION=$("$PYTHON_CMD" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
IFS='.' read -r -a VERSION_PARTS <<< "$PYTHON_VERSION"
MAJOR=${VERSION_PARTS[0]}
MINOR=${VERSION_PARTS[1]}

if [[ "$MAJOR" -lt 3 ]] || ([[ "$MAJOR" -eq 3 ]] && [[ "$MINOR" -lt 8 ]]); then
    echo "Error: Python version ${PYTHON_VERSION} found. Python 3.8 or higher is required! Please install it from https://www.python.org/downloads/"
    read -p "Press Enter to exit..."
    exit 1
fi

echo "Python ($PYTHON_CMD $PYTHON_VERSION) found."

# --- Upgrade pip to the latest version ---
echo "Upgrading pip..."
"$PYTHON_CMD" -m pip install --upgrade pip || { echo "Failed to upgrade pip. Exiting."; read -p "Press Enter to exit..." ; exit 1; }

# --- Install required Python packages ---
echo "Installing required Python packages from requirements.txt..."
"$PYTHON_CMD" -m pip install -r requirements.txt || { echo "Failed to install Python packages. Exiting."; read -p "Press Enter to exit..." ; exit 1; }

# --- Install Playwright browsers ---
echo "Installing Playwright browsers..."
"$PYTHON_CMD" -m playwright install || { echo "Failed to install Playwright browsers. Exiting."; read -p "Press Enter to exit..." ; exit 1; }

# --- Note about fonts ---
echo ""
echo "Note: The scraper is configured to automatically download required fonts (DejaVuSans/NotoSerif) if they are missing during PDF generation."
echo "If you encounter font issues, please ensure you have an active internet connection when running the scraper."
echo ""

# --- Instructions to run ---
echo "Installation complete!"
echo "To run the scraper, execute: $PYTHON_CMD scraper.py"
read -p "Press Enter to exit..."
exit 0
