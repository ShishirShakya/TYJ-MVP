#!/usr/bin/env python3
"""
Performance benchmark for percentile calculation optimization.

Compares O(n²) vs O(n log n) implementations to measure speedup.
"""

import time
import random
from bisect import bisect_right
from typing import List


def calculate_percentile_old(grade_float: float, all_grades_list: List[float]) -> float:
    """Old O(n²) percentile calculation."""
    if not all_grades_list:
        return 0.0
    percentile_val = (sum(1 for g in all_grades_list if g <= grade_float) / len(all_grades_list)) * 100
    return percentile_val


def calculate_percentile_optimized(grade_float: float, sorted_grades: List[float]) -> float:
    """Optimized O(n log n) percentile calculation."""
    if not sorted_grades:
        return 0.0
    percentile_val = (bisect_right(sorted_grades, grade_float) / len(sorted_grades)) * 100
    return percentile_val


def benchmark_percentile_calculation(batch_size: int, num_files: int) -> dict:
    """
    Benchmark percentile calculation for a batch of files.
    
    Args:
        batch_size: Number of grades in the batch
        num_files: Number of files to calculate percentile for
        
    Returns:
        Dictionary with timing results
    """
    # Generate random grades
    random.seed(42)  # Reproducible results
    all_grades = [random.uniform(0, 100) for _ in range(batch_size)]
    
    # Generate random grades to calculate percentile for
    test_grades = [random.uniform(0, 100) for _ in range(num_files)]
    
    # Benchmark old method
    start_time = time.perf_counter()
    for grade in test_grades:
        calculate_percentile_old(grade, all_grades)
    old_time = time.perf_counter() - start_time
    
    # Benchmark optimized method
    sorted_grades = sorted(all_grades)  # Sort once
    start_time = time.perf_counter()
    for grade in test_grades:
        calculate_percentile_optimized(grade, sorted_grades)
    new_time = time.perf_counter() - start_time
    
    speedup = old_time / new_time if new_time > 0 else float('inf')
    
    return {
        "batch_size": batch_size,
        "num_files": num_files,
        "old_time_seconds": old_time,
        "new_time_seconds": new_time,
        "speedup": speedup,
        "time_saved_seconds": old_time - new_time,
        "time_saved_percent": ((old_time - new_time) / old_time * 100) if old_time > 0 else 0
    }


def main():
    """Run benchmarks with various batch sizes."""
    print("=" * 80)
    print("Percentile Calculation Performance Benchmark")
    print("=" * 80)
    print()
    
    test_cases = [
        (10, 10),      # Small batch
        (50, 50),      # Medium batch
        (100, 100),    # Large batch
        (500, 500),    # Very large batch
        (1000, 1000),  # Extremely large batch
    ]
    
    results = []
    
    for batch_size, num_files in test_cases:
        print(f"Benchmarking: {batch_size} grades, {num_files} files...")
        result = benchmark_percentile_calculation(batch_size, num_files)
        results.append(result)
        
        print(f"  Old method:    {result['old_time_seconds']:.6f}s")
        print(f"  New method:    {result['new_time_seconds']:.6f}s")
        print(f"  Speedup:       {result['speedup']:.2f}x")
        print(f"  Time saved:   {result['time_saved_seconds']:.6f}s ({result['time_saved_percent']:.1f}%)")
        print()
    
    # Summary
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"{'Batch Size':<15} {'Files':<10} {'Old Time (s)':<15} {'New Time (s)':<15} {'Speedup':<10}")
    print("-" * 80)
    
    for result in results:
        print(f"{result['batch_size']:<15} {result['num_files']:<10} "
              f"{result['old_time_seconds']:<15.6f} {result['new_time_seconds']:<15.6f} "
              f"{result['speedup']:<10.2f}x")
    
    print()
    print("Expected complexity:")
    print("  Old method: O(n²) - O(batch_size × num_files)")
    print("  New method: O(n log n) - O(batch_size × log(batch_size) + num_files × log(batch_size))")
    print()
    print("For large batches, the optimized method should show significant speedup.")


if __name__ == "__main__":
    main()

