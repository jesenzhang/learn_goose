@echo off
REM Pho Workflow Editor - Standalone Startup Script
REM
REM This script starts only the React workflow editor.
REM The Pho API server should be started separately using start_api.bat
REM
REM Usage:
REM     start_editor.bat [PORT] [API_URL]
REM
REM Examples:
REM     start_editor.bat
REM     start_editor.bat 8300
REM     start_editor.bat 9000 http://localhost:9000

setlocal enabledelayedexpansion

REM Default values
set "PORT=%~1"
if "%PORT%"=="" set "PORT=9000"

set "API_URL=%~2"
if "%API_URL%"=="" set "API_URL=http://127.0.0.1:8300"

REM Set paths
set "SCRIPT_DIR=%~dp0"
set "PHO_ROOT=%SCRIPT_DIR%.."
set "REACT_EDITOR_DIR=%PHO_ROOT%\web\react-editor"

echo ========================================
echo  Pho Workflow Editor
echo ========================================
echo.
echo Configuration:
echo   Editor Port: %PORT%
echo   API URL:     %API_URL%
echo.

REM Check if Node.js is installed
echo Checking Node.js installation...
where node >nul 2>&1
if errorlevel 1 (
    echo   ERROR: Node.js not found. Please install Node.js 18+ first.
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version') do set NODE_VERSION=%%i
echo   Found Node.js: %NODE_VERSION%

REM Check if npm dependencies are installed
echo Checking npm dependencies...
if not exist "%REACT_EDITOR_DIR%\node_modules" (
    echo   Installing dependencies...
    call npm install --prefix "%REACT_EDITOR_DIR%"
) else (
    echo   Dependencies already installed
)

REM Start React editor
echo.
echo Starting React workflow editor...
echo.
echo ========================================
echo  Editor is ready!
echo ========================================
echo   React Editor: http://localhost:%PORT%
echo   API URL:      %API_URL%
echo.
echo Press Ctrl+C to stop the editor
echo.

REM Set environment variables for React
set VITE_API_BASE_URL=%API_URL%
for /f "tokens=3 delims=:" %%a in ("%API_URL%") do set VITE_API_PORT=%%a

REM Change to react-editor directory
cd /d "%REACT_EDITOR_DIR%"

REM Start React dev server
npx vite --port %PORT%

endlocal
