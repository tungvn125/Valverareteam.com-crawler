@echo off
echo Installing dependencies for Web Novel Scraper...

:: Check if Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Python is not installed! Please install Python 3.8 or higher from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: crete a virtual environment
echo Creating virtual environment...
python -m venv venv

:: activate the virtual environment
echo Activating virtual environment...
.\venv\Scripts\activate


:: Upgrade pip to the latest version
echo Upgrading pip...
python -m pip install --upgrade pip

:: Install required Python packages
echo Installing required Python packages...
pip install -r requirements.txt

:: Install Playwright browsers
echo Installing Playwright browsers...
playwright install chromium

:: Download DejaVuSans font
echo Please download the DejaVuSans or NotoSerif font manually and place it in the project directory.
echo Dont forget to rename it to "DejaVuSans.ttf" or "NotoSerif.ttf" as required by the scraper.

echo To run the scraper, execute: python scraper.py
pause