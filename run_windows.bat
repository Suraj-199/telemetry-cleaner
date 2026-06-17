@echo off
echo ========================================================
echo Starting Telemetry Analytics Platform
echo ========================================================

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to PATH!
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check the box "Add Python to PATH" during installation.
    pause
    exit /b
)

:: Check if virtual environment exists, create if it doesn't
if not exist ".venv" (
    echo [INFO] First time setup: Creating virtual environment...
    python -m venv .venv
    echo [INFO] Installing required dependencies (this may take a minute)...
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    echo [INFO] Virtual environment found. Activating...
    call .venv\Scripts\activate.bat
)

:: Run the Streamlit app
echo [INFO] Launching the application...
echo You can keep this window open while using the app.
streamlit run src/app.py

pause
