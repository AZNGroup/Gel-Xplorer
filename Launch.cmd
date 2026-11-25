@echo off
setlocal EnableDelayedExpansion

title Gel Xplorer Launcher

cd /d "%~dp0"

set "APP_NAME=Gel Xplorer"
set "APP_DIR=%LOCALAPPDATA%\Gel Xplorer"
set "VENV_DIR=%APP_DIR%\venv"
set "APP_PYTHON=%VENV_DIR%\Scripts\python.exe"

echo ==================================================
echo                 GEL XPLORER
echo ==================================================
echo.

REM ==================================================
REM CHECK SYSTEM PYTHON
REM ==================================================

where python >nul 2>&1

if errorlevel 1 (
    echo ERROR: Python is not installed or not available in PATH.
    echo.
    echo Gel Xplorer was developed and tested using Python 3.12.
    echo.
    echo Please install Python 3.12 or newer from:
    echo https://www.python.org/downloads/
    echo.
    echo During installation, ensure:
    echo [X] Add Python to PATH
    echo.
    pause
    exit /b 1
)

python -c "import sys; exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1

if errorlevel 1 (
    echo ERROR: Python 3.12 or newer is required.
    echo.
    echo Installed version:
    python --version
    echo.
    echo Gel Xplorer was developed and tested using Python 3.12.
    echo Please install Python 3.12 or a newer compatible version.
    echo.
    pause
    exit /b 1
)

echo Python detected:
python --version
echo.
echo Note: Gel Xplorer was developed and tested using Python 3.12.
echo.

REM ==================================================
REM CHECK REQUIRED FILES
REM ==================================================

if not exist "%~dp0app.py" (
    echo ERROR: app.py not found.
    echo.
    echo Expected location:
    echo %~dp0app.py
    echo.
    pause
    exit /b 1
)

if not exist "%~dp0requirements.txt" (
    echo ERROR: requirements.txt not found.
    echo.
    echo Expected location:
    echo %~dp0requirements.txt
    echo.
    pause
    exit /b 1
)

REM ==================================================
REM CREATE APPLICATION DIRECTORY
REM ==================================================

if not exist "%APP_DIR%" (
    mkdir "%APP_DIR%"
)

REM ==================================================
REM CREATE VIRTUAL ENVIRONMENT
REM ==================================================

if not exist "%APP_PYTHON%" (

    echo Creating virtual environment...
    echo.

    python -m venv "%VENV_DIR%"

    if errorlevel 1 (
        echo.
        echo ERROR: Failed to create virtual environment.
        echo.
        echo Possible causes:
        echo - Corrupted Python installation
        echo - Insufficient permissions
        echo - Antivirus interference
        echo.
        pause
        exit /b 1
    )

    echo Virtual environment created successfully.
    echo.
)

REM ==================================================
REM UPDATE PIP TOOLS
REM ==================================================

echo Updating pip tools...
echo.

"%APP_PYTHON%" -m pip install --upgrade pip setuptools wheel

if errorlevel 1 (
    echo WARNING: Failed to update pip/setuptools/wheel.
    echo Continuing with existing versions...
    echo.
)

REM ==================================================
REM INSTALL DEPENDENCIES
REM ==================================================

echo Installing required packages...
echo.
echo First launch may take several minutes.
echo.

"%APP_PYTHON%" -m pip install --prefer-binary -r "%~dp0requirements.txt"

if errorlevel 1 (
    echo.
    echo ==================================================
    echo DEPENDENCY INSTALLATION FAILED
    echo ==================================================
    echo.
    echo Installed Python:
    "%APP_PYTHON%" --version
    echo.
    echo Common causes:
    echo.
    echo 1. No internet connection
    echo 2. Firewall or proxy restrictions
    echo 3. Antivirus software blocking downloads
    echo 4. Temporary package server issues
    echo 5. Corrupted pip cache
    echo.
    echo Troubleshooting steps:
    echo.
    echo "%APP_PYTHON%" -m pip cache purge
    echo "%APP_PYTHON%" -m pip install -r "%~dp0requirements.txt" -v
    echo.
    pause
    exit /b 1
)

echo.
echo Dependencies installed successfully.
echo.

REM ==================================================
REM START GEL XPLORER
REM ==================================================

echo Launching Gel Xplorer...
echo.

"%APP_PYTHON%" -m streamlit run "%~dp0app.py" ^
--server.address 127.0.0.1 ^
--browser.gatherUsageStats false

if errorlevel 1 (
    echo.
    echo ==================================================
    echo GEL XPLORER FAILED TO START
    echo ==================================================
    echo.
    echo Review the error messages above.
    echo.
    echo If the problem persists:
    echo 1. Delete the virtual environment folder:
    echo    %VENV_DIR%
    echo 2. Relaunch Gel Xplorer
    echo.
    pause
    exit /b 1
)

endlocal
