#!/usr/bin/env python
"""
Pho Workflow Editor - Standalone Startup Script

This script starts only the React workflow editor.
The Pho API server should be started separately using start_api.py

Usage:
    python start_editor.py [--port PORT] [--api-url API_URL]

Examples:
    python start_editor.py
    python start_editor.py --port 8300
    python start_editor.py --port 9000 --api-url http://localhost:9000
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse
import requests


def check_node_installed():
    """Check if Node.js is installed."""
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        return True, result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False, None


def check_dependencies(react_dir: Path) -> bool:
    """Check if npm dependencies are installed."""
    return (react_dir / "node_modules").exists()


def install_dependencies(react_dir: Path):
    """Install npm dependencies."""
    subprocess.run(
        ["npm", "install"],
        cwd=react_dir,
        check=True
    )


def check_api_running(api_url: str) -> bool:
    """Check if API server is running."""
    try:
        response = requests.get(f"{api_url}/health", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Start Pho Workflow Editor")
    parser.add_argument(
        "--port",
        type=int,
        default=9000,
        help="Port for React dev server (default: 9000)"
    )
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8300",
        help="API server URL (default: http://127.0.0.1:8300)"
    )

    args = parser.parse_args()

    # Set paths
    script_dir = Path(__file__).parent
    pho_root = script_dir.parent
    react_editor_dir = pho_root / "web" / "react-editor"

    print("=" * 40)
    print(" Pho Workflow Editor")
    print("=" * 40)
    print()
    print("Configuration:")
    print(f"  Editor Port: {args.port}")
    print(f"  API URL:     {args.api_url}")
    print()

    # Check if Node.js is installed
    print("Checking Node.js installation...")
    node_installed, node_version = check_node_installed()
    if not node_installed:
        print("  ERROR: Node.js not found. Please install Node.js 18+ first.")
        sys.exit(1)
    print(f"  Found Node.js: {node_version}")

    # Check if npm dependencies are installed
    print("Checking npm dependencies...")
    if not check_dependencies(react_editor_dir):
        print("  Installing dependencies...")
        install_dependencies(react_editor_dir)
    else:
        print("  Dependencies already installed")

    # Check if API server is running
    print("Checking API server availability...")
    if check_api_running(args.api_url):
        print(f"  API server is running at {args.api_url}")
    else:
        print(f"  WARNING: API server is not available at {args.api_url}")
        print("  Start API server first: python start_api.py")
        print()
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("  Aborted.")
            sys.exit(1)

    # Start React editor
    print()
    print("Starting React workflow editor...")
    print()
    print("=" * 40)
    print(" Editor is ready!")
    print("=" * 40)
    print(f"  React Editor: http://localhost:{args.port}")
    print(f"  API URL:      {args.api_url}")
    print()
    print("Press Ctrl+C to stop the editor")
    print()

    # Set environment variables for React
    env = os.environ.copy()
    env["VITE_API_BASE_URL"] = args.api_url
    env["VITE_API_PORT"] = str(urlparse(args.api_url).port or "8300")
    
    # Ensure PATH uses the correct separator for the platform
    if os.name == 'nt':  # Windows check
        env['PATH'] = os.environ['PATH']

    # Start React dev server
    try:
        # On Windows, we might need to use shell=True or call npx differently
        cmd = ["npx", "vite", "--port", str(args.port)]
        
        # For Windows compatibility, try using shell=True
        subprocess.run(
            cmd,
            cwd=react_editor_dir,
            env=env,
            check=True,
            shell=True
        )
    except KeyboardInterrupt:
        print("\nEditor stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"\nERROR: Failed to start editor: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
