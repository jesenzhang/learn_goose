#!/usr/bin/env python
"""
Pho API Server - Standalone Startup Script

This script starts the Pho API server independently.

Usage:
    python start_api.py [--host HOST] [--port PORT] [--log-level LEVEL]

Examples:
    python start_api.py
    python start_api.py --host 0.0.0.0 --port 9000
    python start_api.py --log-level debug
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add pho to path
PHO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PHO_ROOT / "src"))


def main():
    parser = argparse.ArgumentParser(description="Start Pho API Server")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8300,
        help="Port to bind to (default: 8300)"
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug"],
        help="Logging level (default: info)"
    )
    parser.add_argument(
        "--log-file",
        help="Log file path (default: logs/api-server.log)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )

    args = parser.parse_args()

    # Setup logging
    log_file = args.log_file or str(PHO_ROOT / "web" / "logs" / "api-server.log")
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )

    logger = logging.getLogger(__name__)
    logger.info(f"Starting Pho API server on {args.host}:{args.port}")
    logger.info(f"Log file: {log_file}")

    # Import and run server
    try:
        from pho.api.app import run_server
        run_server(
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=args.log_level
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
