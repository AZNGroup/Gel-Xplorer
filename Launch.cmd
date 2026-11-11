@echo off
setlocal

cd /d "%~dp0"

set "APP_PYTHON=%LOCALAPPDATA%\GelSIT\venv\Scripts\python.exe"

REM Check for Python 3.12+ and create virtual environment if needed
if not exist "%APP_PYTHON%" (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
    if errorlevel 1 goto python_required

    echo Creating GelSIT virtual environment...
    py -3 -m venv "%LOCALAPPDATA%\GelSIT\venv"
    if errorlevel 1 goto failed
)

REM Verify Python version inside the virtual environment
"%APP_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if errorlevel 1 goto python_required

REM Upgrade pip in the virtual environment
echo Checking pip...
"%APP_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto failed

REM Always ensure required packages are installed/updated
echo Checking GelSIT dependencies...
"%APP_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto failed

REM Launch GelSIT
echo Starting GelSIT...
"%APP_PYTHON%" -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
if errorlevel 1 goto failed

exit /b 0

:python_required
echo.
echo Python 3.12 or newer is required.
echo Please install Python 3.12+ from https://www.python.org/downloads/
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
