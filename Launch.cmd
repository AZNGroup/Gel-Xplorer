@echo off
setlocal
cd /d "%~dp0"
set "APP_PYTHON=%LOCALAPPDATA%\GelationAnalyzer\venv\Scripts\python.exe"
if not exist "%APP_PYTHON%" (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
    if errorlevel 1 goto python_required
    py -3 -m venv "%LOCALAPPDATA%\GelationAnalyzer\venv"
    if errorlevel 1 goto failed
)
"%APP_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
if errorlevel 1 goto python_required
"%APP_PYTHON%" -c "import streamlit, plotly, openpyxl, pandas, numpy, kaleido" >nul 2>&1
if errorlevel 1 (
    "%APP_PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 goto failed
)
"%APP_PYTHON%" -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
if errorlevel 1 goto failed
exit /b 0
:python_required
echo Python 3.12 or newer is required. Install a supported Python 3 release and try again.
pause
exit /b 1
:failed
echo The application could not start. Review the error above.
pause
exit /b 1