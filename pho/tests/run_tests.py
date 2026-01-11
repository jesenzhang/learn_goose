#!/usr/bin/env python
"""
Pho Test Runner

Comprehensive test execution script that:
1. Runs unit tests
2. Runs integration tests
3. Runs benchmarks
4. Generates coverage report
5. Outputs test results summary

Usage:
    python tests/run_tests.py
    python tests/run_tests.py --skip-load
    python tests/run_tests.py --only-unit
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple


# ANSI colors
class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


def print_header(text: str):
    """Print a header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 80}{Colors.ENDC}\n")


def print_success(text: str):
    """Print success message."""
    print(f"{Colors.OKGREEN}[OK] {text}{Colors.ENDC}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.FAIL}[X] {text}{Colors.ENDC}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.WARNING}[!] {text}{Colors.ENDC}")


def run_command(cmd: List[str], description: str) -> Tuple[bool, str, float]:
    """Run a command and return success, output, and duration."""
    print(f"{Colors.OKCYAN}Running: {description}{Colors.ENDC}")
    print(f"Command: {' '.join(cmd)}\n")

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        duration = time.time() - start
        success = result.returncode == 0
        return success, result.stdout + result.stderr, duration
    except Exception as e:
        duration = time.time() - start
        return False, str(e), duration


def run_unit_tests(verbose: bool = False) -> bool:
    """Run unit tests."""
    print_header("UNIT TESTS")

    cmd = ["python", "-m", "pytest", "tests/unit/", "-v"]
    if verbose:
        cmd.append("-vv")

    success, output, duration = run_command(cmd, "Unit Tests")

    print(output)
    print(f"\nDuration: {duration:.2f}s")

    if success:
        print_success("Unit tests passed!")
    else:
        print_error("Unit tests failed!")

    return success


def run_integration_tests(verbose: bool = False) -> bool:
    """Run integration tests."""
    print_header("INTEGRATION TESTS")

    cmd = ["python", "-m", "pytest", "tests/integration/", "-v"]
    if verbose:
        cmd.append("-vv")

    success, output, duration = run_command(cmd, "Integration Tests")

    print(output)
    print(f"\nDuration: {duration:.2f}s")

    if success:
        print_success("Integration tests passed!")
    else:
        print_error("Integration tests failed!")

    return success


def run_benchmarks() -> bool:
    """Run performance benchmarks."""
    print_header("PERFORMANCE BENCHMARKS")

    cmd = [
        "python", "-m", "pytest",
        "tests/benchmark/",
        "--benchmark-only",
        "--benchmark-sort=name",
    ]

    success, output, duration = run_command(cmd, "Benchmarks")

    print(output)
    print(f"\nDuration: {duration:.2f}s")

    if success:
        print_success("Benchmarks completed!")
    else:
        print_error("Benchmarks failed!")

    return success


def run_coverage() -> bool:
    """Run tests with coverage."""
    print_header("COVERAGE REPORT")

    cmd = [
        "python", "-m", "pytest",
        "tests/",
        "--cov=pho",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "-v",
    ]

    success, output, duration = run_command(cmd, "Coverage Tests")

    print(output)
    print(f"\nDuration: {duration:.2f}s")
    print(f"\nHTML coverage report: {Colors.OKCYAN}htmlcov/index.html{Colors.ENDC}")

    if success:
        print_success("Coverage report generated!")
    else:
        print_error("Coverage tests failed!")

    return success


def print_load_test_instructions():
    """Print instructions for running load tests."""
    print_header("LOAD TEST INSTRUCTIONS")

    print(f"{Colors.WARNING}Load tests require the API server to be running.{Colors.ENDC}\n")
    print("To run load tests:")
    print(f"{Colors.OKCYAN}1. Start the API server:{Colors.ENDC}")
    print("   pho-api")
    print(f"\n{Colors.OKCYAN}2. In another terminal, run Locust:{Colors.ENDC}")
    print("   locust -f tests/load/agent_load_test.py --host=http://localhost:8000")
    print(f"\n{Colors.OKCYAN}3. Or run headless:{Colors.ENDC}")
    print("   locust -f tests/load/agent_load_test.py --headless \\")
    print("     --host=http://localhost:8000 --users=100 --spawn-rate=10 --run-time=1m")


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Pho Test Runner")
    parser.add_argument("--skip-load", action="store_true", help="Skip load test instructions")
    parser.add_argument("--only-unit", action="store_true", help="Only run unit tests")
    parser.add_argument("--only-integration", action="store_true", help="Only run integration tests")
    parser.add_argument("--only-benchmark", action="store_true", help="Only run benchmarks")
    parser.add_argument("--coverage", action="store_true", help="Run coverage report")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    print_header("Pho Framework Test Suite v0.1.0")

    results = {}
    start_time = time.time()

    if args.only_benchmark:
        results["benchmarks"] = run_benchmarks()
    elif args.only_unit:
        results["unit"] = run_unit_tests(verbose=args.verbose)
    elif args.only_integration:
        results["integration"] = run_integration_tests(verbose=args.verbose)
    elif args.coverage:
        results["coverage"] = run_coverage()
    else:
        # Run all tests
        results["unit"] = run_unit_tests(verbose=args.verbose)
        results["integration"] = run_integration_tests(verbose=args.verbose)
        results["benchmarks"] = run_benchmarks()

        if not args.skip_load:
            print_load_test_instructions()

    # Print summary
    total_duration = time.time() - start_time
    print_header("TEST SUMMARY")

    for test_type, passed in results.items():
        if passed:
            print_success(f"{test_type.upper()}: PASSED")
        else:
            print_error(f"{test_type.upper()}: FAILED")

    print(f"\n{Colors.OKCYAN}Total Duration: {total_duration:.2f}s{Colors.ENDC}")

    # Exit with error code if any test failed
    if not all(results.values()):
        sys.exit(1)
    else:
        print_success("\n[SUCCESS] All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
