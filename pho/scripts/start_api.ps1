# Pho API Server - Standalone Startup Script
#
# This script starts the Pho API server independently.
#
# Usage:
#     .\start_api.ps1 [-Host HOST] [-Port PORT] [-LogLevel LEVEL] [-Reload]
#
# Examples:
#     .\start_api.ps1
#     .\start_api.ps1 -Host "0.0.0.0" -Port 9000
#     .\start_api.ps1 -LogLevel "debug"

param(
    [string]$Host = "127.0.0.1",
    [int]$Port = 8300,
    [string]$LogLevel = "info",
    [switch]$Reload
)

$ErrorActionPreference = "Continue"

# Set paths
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PHO_ROOT = Split-Path -Parent $SCRIPT_DIR
$LOG_FILE = Join-Path $PHO_ROOT "web\logs\api-server.log"

# Create logs directory
$logDir = Split-Path -Parent $LOG_FILE
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Pho API Server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Gray
Write-Host "  Host:      $Host" -ForegroundColor Gray
Write-Host "  Port:      $Port" -ForegroundColor Gray
Write-Host "  Log Level: $LogLevel" -ForegroundColor Gray
Write-Host "  Log File:  $LOG_FILE" -ForegroundColor Gray
Write-Host ""

# Get Python path
function Get-PythonPath {
    # Try conda base environment first
    $condaBase = "D:\miniforge3\python.exe"
    if (Test-Path $condaBase) {
        return $condaBase
    }
    # Fallback to system python
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return $pythonCmd.Source
    }
    return $null
}

$pythonPath = Get-PythonPath
if (-not $pythonPath) {
    Write-Host "ERROR: Python not found. Please install Python 3.8+ first." -ForegroundColor Red
    exit 1
}

Write-Host "Python: $pythonPath" -ForegroundColor Gray
Write-Host ""
Write-Host "Starting API server..." -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

# Build arguments
$arguments = @(
    (Join-Path $SCRIPT_DIR "start_api.py")
    "--host", $Host
    "--port", $Port
    "--log-level", $LogLevel
)

if ($Reload) {
    $arguments += "--reload"
}

# Set environment variable for UTF-8 encoding
$env:PYTHONIOENCODING = "utf-8"

# Start the API server
$processInfo = New-Object System.Diagnostics.ProcessStartInfo
$processInfo.FileName = $pythonPath
$processInfo.Arguments = $arguments -join " "
$processInfo.WorkingDirectory = $PHO_ROOT
$processInfo.UseShellExecute = $false
$processInfo.RedirectStandardOutput = $true
$processInfo.RedirectStandardError = $true

$process = [System.Diagnostics.Process]::Start($processInfo)

# Stream output
$process.WaitForExit()

# Get exit code
$exitCode = $process.ExitCode
if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "API server exited with code: $exitCode" -ForegroundColor Red
    exit $exitCode
}
