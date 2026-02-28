@echo off
echo Installing dependencies for Web Novel Scraper...
echo.

:: Check if Python is installed and is version 3.8 or higher
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not found on your system.
    echo Please install Python 3.8 or higher from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Get Python version
for /f "tokens=2" %%i in ('python --version') do set PYTHON_VERSION=%%i
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set MAJOR=%%a
    set MINOR=%%b
)

if %MAJOR% lss 3 (
    echo Error: Python version %PYTHON_VERSION% found. This project requires Python 3.8 or higher.
    echo Please install a compatible version from https://www.python.org/downloads/
    pause
    exit /b 1
)

if %MAJOR% equ 3 if %MINOR% lss 8 (
    echo Error: Python version %PYTHON_VERSION% found. This project requires Python 3.8 or higher.
    echo Please install a compatible version from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Compatible Python version (%PYTHON_VERSION%) found.
echo.

:: Create virtual environment
set VENV_DIR=venv
if not exist "%VENV_DIR%" (
    echo Creating virtual environment in '%VENV_DIR%'...
    python -m venv "%VENV_DIR%"
    echo Virtual environment created successfully.
) else (
    echo Virtual environment '%VENV_DIR%' already exists. Skipping creation.
)
echo.

:: Define path to the virtual environment's Python executable
set VENV_PYTHON=%VENV_DIR%\Scripts\python.exe

:: Upgrade pip to the latest version in the venv
echo Upgrading pip in the virtual environment...
"%VENV_PYTHON%" -m pip install --upgrade pip
echo.

:: Install required Python packages into the venv
echo Installing required Python packages from requirements.txt...
"%VENV_PYTHON%" -m pip install -r requirements.txt
echo.

:: Install Playwright browsers
echo Installing Playwright browsers...
"%VENV_PYTHON%" -m playwright install chromium-headless-shell
echo.

:: Note about fonts
echo Note: The scraper is now configured to automatically download required fonts ^(e.g., DejaVuSans^) if they are missing.
echo If you encounter font issues, please ensure you have an active internet connection when running the scraper for the first time.
echo.

echo --------------------------------------------------
echo Installation complete!
echo.
echo To run the scraper, follow these steps:
echo 1. Activate the virtual environment: venv\Scripts\activate
echo 2. Run the scraper script:         python scraper.py
echo 3. When you are finished, deactivate: deactivate
echo --------------------------------------------------
echo.
pause