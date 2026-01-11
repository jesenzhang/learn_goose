#!/bin/bash
# Pho Workflow Editor - Standalone Startup Script
#
# This script starts only the React workflow editor.
# The Pho API server should be started separately using start_api.sh
#
# Usage:
#     ./start_editor.sh [PORT] [API_URL]
#
# Examples:
#     ./start_editor.sh
#     ./start_editor.sh 8300
#     ./start_editor.sh 9000 http://localhost:9000

set -e

# Default values
PORT="${1:-9000}"
API_URL="${2:-http://127.0.0.1:8300}"

# Set paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PHO_ROOT="$(dirname "$SCRIPT_DIR")"
REACT_EDITOR_DIR="$PHO_ROOT/web/react-editor"

echo "========================================"
echo " Pho Workflow Editor"
echo "========================================"
echo ""
echo "Configuration:"
echo "  Editor Port: $PORT"
echo "  API URL:     $API_URL"
echo ""

# Check if Node.js is installed
echo "Checking Node.js installation..."
if ! command -v node &> /dev/null; then
    echo "  ERROR: Node.js not found. Please install Node.js 18+ first."
    exit 1
fi
NODE_VERSION=$(node --version)
echo "  Found Node.js: $NODE_VERSION"

# Check if npm dependencies are installed
echo "Checking npm dependencies..."
if [ ! -d "$REACT_EDITOR_DIR/node_modules" ]; then
    echo "  Installing dependencies..."
    npm install --prefix "$REACT_EDITOR_DIR"
else
    echo "  Dependencies already installed"
fi

# Check if API server is running
echo "Checking API server availability..."
if curl -s "$API_URL/health" > /dev/null 2>&1; then
    echo "  API server is running at $API_URL"
else
    echo "  WARNING: API server is not available at $API_URL"
    echo "  Start API server first: ./start_api.sh"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "  Aborted."
        exit 1
    fi
fi

# Start React editor
echo ""
echo "Starting React workflow editor..."
echo ""
echo "========================================"
echo " Editor is ready!"
echo "========================================"
echo "  React Editor: http://localhost:$PORT"
echo "  API URL:      $API_URL"
echo ""
echo "Press Ctrl+C to stop the editor"
echo ""

# Set environment variables for React
export VITE_API_BASE_URL="$API_URL"
export VITE_API_PORT=$(echo "$API_URL" | cut -d':' -f3)

# Change to react-editor directory
cd "$REACT_EDITOR_DIR"

# Start React dev server
npx vite --port "$PORT"
