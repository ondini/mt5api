@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: MT5 API — Windows Service Installer
::
:: Prerequisites
::   1. NSSM  (Non-Sucking Service Manager)
::      https://nssm.cc/download  →  put nssm.exe on PATH
::      e.g.  copy nssm.exe to C:\Windows\System32\
::
::   2. nginx for Windows
::      https://nginx.org/en/download.html  →  extract to C:\nginx
::
::   3. Python dependencies installed:
::      pip install -r requirements.txt
:: ============================================================

set "SCRIPT_DIR=%~dp0"
set "NGINX_DIR=C:\nginx"
set "WSGI_HOST=127.0.0.1"
set "WSGI_PORT=8000"
set "PUBLIC_PORT=5000"

:: Detect Python — prefer venv
set "PYTHON=python"
if exist "%SCRIPT_DIR%venv\Scripts\python.exe" (
    set "PYTHON=%SCRIPT_DIR%venv\Scripts\python.exe"
)

echo ============================================================
echo  MT5 API — Windows Service Installer
echo ============================================================
echo.

:: ── Check for admin rights ───────────────────────────────────
net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] This script must be run as Administrator.
    pause & exit /b 1
)

:: ── Check for NSSM ───────────────────────────────────────────
where nssm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] nssm.exe not found in PATH.
    echo         Download: https://nssm.cc/download
    echo         Copy nssm.exe to C:\Windows\System32\ and re-run.
    pause & exit /b 1
)

:: ── Create logs directory ────────────────────────────────────
mkdir "%SCRIPT_DIR%logs" 2>nul

:: ── Install Waitress (MT5API) service ────────────────────────
echo [1/3] Installing MT5API (Waitress) service...
nssm install MT5API "%PYTHON%" "%SCRIPT_DIR%wsgi.py"
nssm set MT5API AppDirectory       "%SCRIPT_DIR%"
nssm set MT5API DisplayName        "MetaTrader5 API (Waitress)"
nssm set MT5API Description        "Waitress WSGI server for MT5 Flask API on port %WSGI_PORT%"
nssm set MT5API Start              SERVICE_AUTO_START
nssm set MT5API AppEnvironmentExtra "MT5_WSGI_HOST=%WSGI_HOST%" "MT5_WSGI_PORT=%WSGI_PORT%"
nssm set MT5API AppStdout          "%SCRIPT_DIR%logs\mt5api.log"
nssm set MT5API AppStderr          "%SCRIPT_DIR%logs\mt5api.log"
nssm set MT5API AppRotateFiles     1
nssm set MT5API AppRotateOnline    1
nssm set MT5API AppRotateSeconds   86400
nssm set MT5API AppRotateBytes     10485760

:: ── Install nginx service ────────────────────────────────────
echo [2/3] Installing nginx service...
if not exist "%NGINX_DIR%\nginx.exe" (
    echo [WARNING] nginx not found at %NGINX_DIR%\nginx.exe
    echo           Download: https://nginx.org/en/download.html
    echo           Extract to %NGINX_DIR%  then re-run to install the nginx service.
    goto :start_waitress
)

:: Copy our nginx.conf into the nginx installation
copy /Y "%SCRIPT_DIR%nginx.conf" "%NGINX_DIR%\conf\nginx.conf" >nul
echo           Copied nginx.conf to %NGINX_DIR%\conf\nginx.conf

nssm install MT5API-Nginx "%NGINX_DIR%\nginx.exe" "-p" "%NGINX_DIR%"
nssm set MT5API-Nginx AppDirectory  "%NGINX_DIR%"
nssm set MT5API-Nginx DisplayName   "MetaTrader5 API (nginx)"
nssm set MT5API-Nginx Description   "nginx reverse proxy: port %PUBLIC_PORT% -> Waitress port %WSGI_PORT%"
nssm set MT5API-Nginx Start         SERVICE_AUTO_START

:: ── Start services ───────────────────────────────────────────
:start_waitress
echo [3/3] Starting services...
nssm start MT5API
if exist "%NGINX_DIR%\nginx.exe" nssm start MT5API-Nginx

echo.
echo Done!
echo.
echo  API available at:  http://localhost:%PUBLIC_PORT%/
echo  Swagger UI:        http://localhost:%PUBLIC_PORT%/apidocs/
echo  Health check:      http://localhost:%PUBLIC_PORT%/health
echo.
echo  Service commands:
echo    nssm status MT5API
echo    nssm status MT5API-Nginx
echo    nssm restart MT5API
echo    nssm stop MT5API
echo.
pause
