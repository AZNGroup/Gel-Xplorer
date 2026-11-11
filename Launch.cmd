@echo off
setlocal

REM Change to the folder containing this script
cd /d "%~dp0"

set "APP_DIR=%LOCALAPPDATA%\GelSIT"
set "APP_PYTHON=%APP_DIR%\venv\Scripts\python.exe"

REM Check that Python 3.12+ is installed
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if errorlevel 1 goto python_required

REM Create application folder if needed
if not exist "%APP_DIR%" (
    mkdir "%APP_DIR%"
)

REM Create virtual environment if needed
if not exist "%APP_PYTHON%" (
    echo Creating GelSIT virtual environment...
    py -3 -m venv "%APP_DIR%\venv"
    if errorlevel 1 goto failed
)

REM Verify Python version in virtual environment
"%APP_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if errorlevel 1 goto python_required

REM Check required files exist
if not exist "%~dp0requirements.txt" (
    echo.
    echo ERROR: requirements.txt not found.
    echo Expected location:
    echo %~dp0requirements.txt
    echo.
    goto failed
)

if not exist "%~dp0app.py" (
    echo.
    echo ERROR: app.py not found.
    echo.
    goto failed
)

REM Upgrade pip
echo Checking pip...
"%APP_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto failed

REM Install/update dependencies
echo.
echo First launch may take several minutes while GelSIT installs dependencies...
echo Checking GelSIT dependencies...
"%APP_PYTHON%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto failed

REM Launch GelSIT
echo.
echo Starting GelSIT...
"%APP_PYTHON%" -m streamlit run "%~dp0app.py" --server.address 127.0.0.1 --browser.gatherUsageStats false

if errorlevel 1 goto failed

exit /b 0

:python_required
echo.
echo Python 3.12 or newer is required.
echo Download Python from:
echo https://www.python.org/downloads/
echo.
pause
exit /b 1

:failed
echo.
echo GelSIT could not start.
echo Review the error messages above and try again.
echo.
pause
exit /b 1
