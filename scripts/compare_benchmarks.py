"""
Benchmark comparison script for CI/CD.

Compares current benchmark results against a baseline and flags regressions.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple


def load_benchmark_json(file_path: str) -> Dict[str, Any]:
    """Load benchmark results from JSON file."""
    with open(file_path, 'r') as f:
        return json.load(f)


def compare_benchmarks(
    current: Dict[str, Any],
    baseline: Dict[str, Any],
    regression_threshold: float = 0.20,  # 20% slower
    improvement_threshold: float = 0.10   # 10% faster
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Compare current benchmarks against baseline.
    
    Returns:
        Tuple of (regressions, improvements, unchanged)
    """
    regressions = []
    improvements = []
    unchanged = []
    
    # Create lookup for baseline benchmarks
    baseline_lookup = {}
    for bench in baseline.get("benchmarks", []):
        baseline_lookup[bench["name"]] = bench
    
    # Compare each current benchmark
    for current_bench in current.get("benchmarks", []):
        name = current_bench["name"]
        baseline_bench = baseline_lookup.get(name)
        
        if not baseline_bench:
            # New benchmark, skip
            continue
        
        # Get mean times (stored in seconds, convert to nanoseconds for display)
        current_mean_sec = current_bench["stats"]["mean"]
        baseline_mean_sec = baseline_bench["stats"]["mean"]
        
        # Convert to nanoseconds for consistent formatting
        current_mean_ns = current_mean_sec * 1_000_000_000
        baseline_mean_ns = baseline_mean_sec * 1_000_000_000
        
        # Calculate percentage change
        if baseline_mean_sec == 0:
            continue
        
        change_pct = ((current_mean_sec - baseline_mean_sec) / baseline_mean_sec) * 100
        
        comparison = {
            "name": name,
            "baseline_mean": baseline_mean_ns,
            "current_mean": current_mean_ns,
            "change_pct": change_pct,
            "change_abs": (current_mean_sec - baseline_mean_sec) * 1_000_000_000
        }
        
        if change_pct > regression_threshold * 100:
            # Regression: >20% slower
            regressions.append(comparison)
        elif change_pct < -improvement_threshold * 100:
            # Improvement: >10% faster
            improvements.append(comparison)
        else:
            # Within acceptable range
            unchanged.append(comparison)
    
    return regressions, improvements, unchanged


def format_time(nanoseconds: float) -> str:
    """Format nanoseconds to human-readable time."""
    if nanoseconds is None or nanoseconds == 0:
        return "0.00ns"
    if nanoseconds < 1000:
        return f"{nanoseconds:.2f}ns"
    elif nanoseconds < 1_000_000:
        return f"{nanoseconds / 1000:.2f}us"  # Use 'us' instead of μs for Windows compatibility
    elif nanoseconds < 1_000_000_000:
        return f"{nanoseconds / 1_000_000:.2f}ms"
    else:
        return f"{nanoseconds / 1_000_000_000:.2f}s"


def print_comparison_report(
    regressions: List[Dict[str, Any]],
    improvements: List[Dict[str, Any]],
    unchanged: List[Dict[str, Any]]
):
    """Print a formatted comparison report."""
    print("\n" + "=" * 80)
    print("BENCHMARK COMPARISON REPORT")
    print("=" * 80)
    
    if regressions:
        print(f"\n[REGRESSIONS] ({len(regressions)} benchmarks >20% slower):")
        print("-" * 80)
        for reg in sorted(regressions, key=lambda x: x["change_pct"], reverse=True):
            print(f"  {reg['name']}")
            print(f"    Baseline: {format_time(reg['baseline_mean'])}")
            print(f"    Current:  {format_time(reg['current_mean'])}")
            print(f"    Change:   +{reg['change_pct']:.1f}% ({format_time(reg['change_abs'])})")
            print()
    
    if improvements:
        print(f"\n[IMPROVEMENTS] ({len(improvements)} benchmarks >10% faster):")
        print("-" * 80)
        for imp in sorted(improvements, key=lambda x: x["change_pct"]):
            print(f"  {imp['name']}")
            print(f"    Baseline: {format_time(imp['baseline_mean'])}")
            print(f"    Current:  {format_time(imp['current_mean'])}")
            print(f"    Change:   {imp['change_pct']:.1f}% ({format_time(imp['change_abs'])})")
            print()
    
    if unchanged:
        print(f"\n[UNCHANGED] ({len(unchanged)} benchmarks within ±10%):")
        print("-" * 80)
        for unc in sorted(unchanged, key=lambda x: abs(x["change_pct"]), reverse=True)[:10]:  # Top 10
            print(f"  {unc['name']}: {unc['change_pct']:+.1f}%")
        if len(unchanged) > 10:
            print(f"  ... and {len(unchanged) - 10} more")
        print()
    
    print("=" * 80)
    print(f"Total benchmarks compared: {len(regressions) + len(improvements) + len(unchanged)}")
    print("=" * 80)


def main():
    """Main entry point for benchmark comparison."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Compare benchmark results against baseline")
    parser.add_argument(
        "current",
        type=str,
        help="Path to current benchmark results JSON file"
    )
    parser.add_argument(
        "baseline",
        type=str,
        nargs="?",
        help="Path to baseline benchmark results JSON file (optional, will use artifact if not provided)"
    )
    parser.add_argument(
        "--regression-threshold",
        type=float,
        default=0.20,
        help="Percentage threshold for regression detection (default: 0.20 = 20%%)"
    )
    parser.add_argument(
        "--improvement-threshold",
        type=float,
        default=0.10,
        help="Percentage threshold for improvement detection (default: 0.10 = 10%%)"
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit with error code if regressions are detected"
    )
    
    args = parser.parse_args()
    
    # Load current results
    current_path = Path(args.current)
    if not current_path.exists():
        print(f"Error: Current benchmark file not found: {current_path}", file=sys.stderr)
        sys.exit(1)
    
    current = load_benchmark_json(str(current_path))
    
    # Load baseline results
    baseline_path = None
    if args.baseline:
        baseline_path = Path(args.baseline)
    else:
        # Try to find baseline in common locations
        possible_baselines = [
            Path(".benchmarks") / "benchmark" / "0001_benchmark.json",
            Path("benchmark-baseline.json"),
            Path(".github") / "benchmark-baseline.json"
        ]
        
        for path in possible_baselines:
            if path.exists():
                baseline_path = path
                break
    
    if not baseline_path or not baseline_path.exists():
        print("Warning: No baseline found. Skipping comparison.", file=sys.stderr)
        print("Run benchmarks with --benchmark-save=baseline to create a baseline.", file=sys.stderr)
        sys.exit(0)
    
    baseline = load_benchmark_json(str(baseline_path))
    
    # Compare benchmarks
    regressions, improvements, unchanged = compare_benchmarks(
        current,
        baseline,
        regression_threshold=args.regression_threshold,
        improvement_threshold=args.improvement_threshold
    )
    
    # Print report
    print_comparison_report(regressions, improvements, unchanged)
    
    # Exit with error if regressions found and --fail-on-regression is set
    if regressions and args.fail_on_regression:
        print(f"\n[FAILED] {len(regressions)} performance regression(s) detected!", file=sys.stderr)
        sys.exit(1)
    
    if regressions:
        print(f"\n[WARNING] {len(regressions)} performance regression(s) detected (not failing CI)")
    else:
        print("\n[SUCCESS] No performance regressions detected!")


if __name__ == "__main__":
    main()
