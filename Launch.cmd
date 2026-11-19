@echo off
setlocal

cd /d "%~dp0"

set APP_DIR=%LOCALAPPDATA%\GelSIT
set APP_PYTHON=%APP_DIR%\venv\Scripts\python.exe

echo Checking Python...

python -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1

if errorlevel 1 (
    echo.
    echo Python 3.10 or newer is required.
    echo Download from:
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist "%APP_DIR%" mkdir "%APP_DIR%"

if not exist "%APP_PYTHON%" (
    echo.
    echo Creating GelSIT virtual environment...
    python -m venv "%APP_DIR%\venv"
)

if not exist "%~dp0requirements.txt" (
    echo.
    echo ERROR: requirements.txt not found.
    pause
    exit /b 1
)

if not exist "%~dp0app.py" (
    echo.
    echo ERROR: app.py not found.
    pause
    exit /b 1
)

echo.
echo Checking pip...
"%APP_PYTHON%" -m pip install --upgrade pip

echo.
echo First launch may take several minutes while GelSIT installs dependencies...
"%APP_PYTHON%" -m pip install -r "%~dp0requirements.txt"

echo.
echo Starting GelSIT...
"%APP_PYTHON%" -m streamlit run "%~dp0app.py" --server.address 127.0.0.1 --browser.gatherUsageStats false

pause
echo GelSIT could not start.
echo Review the error messages above and try again.
echo.
pause
exit /b 1
