@echo off
REM Pho API Server - Standalone Startup Script
REM
REM This script starts the Pho API server independently.
REM
REM Usage:
REM     start_api.bat [HOST] [PORT] [LOG_LEVEL]
REM
REM Examples:
REM     start_api.bat
REM     start_api.bat 0.0.0.0 9000
REM     start_api.bat 127.0.0.1 8300 debug

setlocal enabledelayedexpansion

REM Default values
set "HOST=%~1"
if "%HOST%"=="" set "HOST=127.0.0.1"

set "PORT=%~2"
if "%PORT%"=="" set "PORT=8300"

set "LOG_LEVEL=%~3"
if "%LOG_LEVEL%"=="" set "LOG_LEVEL=info"

REM Set paths
set "SCRIPT_DIR=%~dp0"
set "PHO_ROOT=%SCRIPT_DIR%.."
set "LOG_FILE=%PHO_ROOT%\web\logs\api-server.log"

REM Create logs directory
if not exist "%PHO_ROOT%\web\logs" (
    mkdir "%PHO_ROOT%\web\logs"
)

echo ========================================
echo  Pho API Server
echo ========================================
echo.
echo Configuration:
echo   Host:      %HOST%
echo   Port:      %PORT%
echo   Log Level: %LOG_LEVEL%
echo   Log File:  %LOG_FILE%
echo.

REM Get Python path
set "PYTHON_PATH=D:\miniforge3\python.exe"
if not exist "%PYTHON_PATH%" (
    set "PYTHON_PATH=python"
)

echo Python: %PYTHON_PATH%
echo.
echo Starting API server...
echo Press Ctrl+C to stop
echo.

REM Set environment variable for UTF-8 encoding
set PYTHONIOENCODING=utf-8

REM Start the API server
"%PYTHON_PATH%" "%SCRIPT_DIR%start_api.py" --host %HOST% --port %PORT% --log-level %LOG_LEVEL%

endlocal
