#!/bin/bash
# Pho API Server - Standalone Startup Script
#
# This script starts the Pho API server independently.
#
# Usage:
#     ./start_api.sh [HOST] [PORT] [LOG_LEVEL]
#
# Examples:
#     ./start_api.sh
#     ./start_api.sh 0.0.0.0 9000
#     ./start_api.sh 127.0.0.1 8300 debug

set -e

# Default values
HOST="${1:-127.0.0.1}"
PORT="${2:-8300}"
LOG_LEVEL="${3:-info}"

# Set paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PHO_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PHO_ROOT/web/logs/api-server.log"

# Create logs directory
mkdir -p "$PHO_ROOT/web/logs"

echo "========================================"
echo " Pho API Server"
echo "========================================"
echo ""
echo "Configuration:"
echo "  Host:      $HOST"
echo "  Port:      $PORT"
echo "  Log Level: $LOG_LEVEL"
echo "  Log File:  $LOG_FILE"
echo ""

# Get Python path
PYTHON_PATH="${CONDA_EXE:+$(dirname "$CONDA_EXE")/python}"
if [ -z "$PYTHON_PATH" ] || [ ! -f "$PYTHON_PATH" ]; then
    PYTHON_PATH="python"
fi

echo "Python: $PYTHON_PATH"
echo ""
echo "Starting API server..."
echo "Press Ctrl+C to stop"
echo ""

# Set environment variable for UTF-8 encoding
export PYTHONIOENCODING=utf-8

# Start the API server
"$PYTHON_PATH" "$SCRIPT_DIR/start_api.py" --host "$HOST" --port "$PORT" --log-level "$LOG_LEVEL"
