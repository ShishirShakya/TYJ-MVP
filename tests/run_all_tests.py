#!/usr/bin/env python3
"""
Test runner script for running all tests in the VivaAI Assessment System.

This script provides an easy way to run all tests with different configurations.
"""

import sys
import subprocess
import argparse
from pathlib import Path


def run_tests(test_path=None, verbose=False, coverage=False, markers=None, parallel=False):
    """
    Run pytest tests with specified options.
    
    Args:
        test_path: Specific test path to run (None for all tests)
        verbose: Run with verbose output
        coverage: Generate coverage report
        markers: Run tests with specific markers (e.g., "integration", "unit")
        parallel: Run tests in parallel (requires pytest-xdist)
    """
    # Base pytest command using uv run
    cmd = ["uv", "run", "pytest"]
    
    # Add test path
    if test_path:
        cmd.append(test_path)
    else:
        cmd.append("tests/")
    
    # Verbose output
    if verbose:
        cmd.append("-v")
    
    # Coverage
    if coverage:
        cmd.extend([
            "--cov=exam",
            "--cov=shared",
            "--cov=app",
            "--cov-report=html",
            "--cov-report=term-missing"
        ])
    
    # Markers
    if markers:
        cmd.extend(["-m", markers])
    
    # Parallel execution
    if parallel:
        cmd.extend(["-n", "auto"])
    
    # Additional useful options
    cmd.extend([
        "--tb=short",  # Shorter traceback format
        "--strict-markers",  # Fail on unknown markers
    ])
    
    print(f"Running: {' '.join(cmd)}")
    print("=" * 60)
    
    # Run tests
    result = subprocess.run(cmd)
    return result.returncode


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run tests for VivaAI Assessment System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all tests
  uv run python tests/run_all_tests.py

  # Run only integration tests
  uv run python tests/run_all_tests.py --markers integration

  # Run with coverage
  uv run python tests/run_all_tests.py --coverage

  # Run specific test file
  uv run python tests/run_all_tests.py tests/integration/test_complete_exam_flow.py

  # Run in parallel
  uv run python tests/run_all_tests.py --parallel

  # Or run pytest directly
  uv run pytest tests/ -v
        """
    )
    
    parser.add_argument(
        "test_path",
        nargs="?",
        default=None,
        help="Specific test path to run (default: all tests)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Run with verbose output"
    )
    
    parser.add_argument(
        "-c", "--coverage",
        action="store_true",
        help="Generate coverage report"
    )
    
    parser.add_argument(
        "-m", "--markers",
        help="Run tests with specific markers (e.g., 'integration', 'unit')"
    )
    
    parser.add_argument(
        "-p", "--parallel",
        action="store_true",
        help="Run tests in parallel (requires pytest-xdist)"
    )
    
    args = parser.parse_args()
    
    # Run tests
    exit_code = run_tests(
        test_path=args.test_path,
        verbose=args.verbose,
        coverage=args.coverage,
        markers=args.markers,
        parallel=args.parallel
    )
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

