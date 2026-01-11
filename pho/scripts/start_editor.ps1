# Pho Workflow Editor - Standalone Startup Script
#
# This script starts only the React workflow editor.
# The Pho API server should be started separately using start_api.ps1
#
# Usage:
#     .\start_editor.ps1 [-Port PORT] [-ApiUrl API_URL]
#
# Examples:
#     .\start_editor.ps1
#     .\start_editor.ps1 -Port 8300
#     .\start_editor.ps1 -Port 9000 -ApiUrl "http://localhost:9000"

param(
    [int]$Port = 9000,
    [string]$ApiUrl = "http://127.0.0.1:8300"
)

$ErrorActionPreference = "Continue"

# Set paths
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PHO_ROOT = Split-Path -Parent $SCRIPT_DIR
$REACT_EDITOR_DIR = Join-Path $PHO_ROOT "web\react-editor"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Pho Workflow Editor" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Gray
Write-Host "  Editor Port: $Port" -ForegroundColor Gray
Write-Host "  API URL:     $ApiUrl" -ForegroundColor Gray
Write-Host ""

# Check if Node.js is installed
Write-Host "Checking Node.js installation..." -ForegroundColor Yellow
try {
    $nodeVersion = node --version
    Write-Host "  Found Node.js: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Node.js not found. Please install Node.js 18+ first." -ForegroundColor Red
    exit 1
}

# Check if npm dependencies are installed
Write-Host "Checking npm dependencies..." -ForegroundColor Yellow
if (-not (Test-Path (Join-Path $REACT_EDITOR_DIR "node_modules"))) {
    Write-Host "  Installing dependencies..." -ForegroundColor Yellow
    Push-Location $REACT_EDITOR_DIR
    npm install
    Pop-Location
} else {
    Write-Host "  Dependencies already installed" -ForegroundColor Green
}

# Check if API server is running
Write-Host "Checking API server availability..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$ApiUrl/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-Host "  API server is running at $ApiUrl" -ForegroundColor Green
    }
} catch {
    Write-Host "  WARNING: API server is not available at $ApiUrl" -ForegroundColor Yellow
    Write-Host "  Start API server first: .\start_api.ps1" -ForegroundColor Yellow
    Write-Host ""
    $response = Read-Host "Continue anyway? (y/N)"
    if ($response -ne "y" -and $response -ne "Y") {
        Write-Host "  Aborted." -ForegroundColor Red
        exit 1
    }
}

# Start React editor
Write-Host ""
Write-Host "Starting React workflow editor..." -ForegroundColor Yellow
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Editor is ready!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  React Editor: http://localhost:$Port" -ForegroundColor Cyan
Write-Host "  API URL:      $ApiUrl" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop the editor" -ForegroundColor Yellow
Write-Host ""

# Set environment variables for React
$env:VITE_API_BASE_URL = $ApiUrl
$env:VITE_API_PORT = ($ApiUrl -split ':')[-1]

# Start React dev server
Push-Location $REACT_EDITOR_DIR
try {
    # Run Vite directly with port parameter
    npx vite --port $Port
} finally {
    Pop-Location
}
