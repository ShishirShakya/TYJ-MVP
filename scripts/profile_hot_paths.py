#!/usr/bin/env python3
"""
Performance profiling script for hot paths.

Profiles critical operations to identify bottlenecks:
- Question generation
- Grading
- PDF loading
- Batch processing
"""

import cProfile
import pstats
import io
from typing import Dict, Any
import time


def profile_question_generation():
    """Profile question generation operation."""
    print("=" * 80)
    print("Profiling: Question Generation")
    print("=" * 80)
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Simulate question generation
    # This would call actual question generation in real scenario
    time.sleep(0.1)  # Simulate work
    
    profiler.disable()
    
    s = io.StringIO()
    stats = pstats.Stats(profiler, stream=s)
    stats.sort_stats('cumulative')
    stats.print_stats(20)  # Top 20 functions
    
    print(s.getvalue())


def profile_grading():
    """Profile grading operation."""
    print("=" * 80)
    print("Profiling: Grading")
    print("=" * 80)
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Simulate grading
    time.sleep(0.05)  # Simulate work
    
    profiler.disable()
    
    s = io.StringIO()
    stats = pstats.Stats(profiler, stream=s)
    stats.sort_stats('cumulative')
    stats.print_stats(20)
    
    print(s.getvalue())


def profile_percentile_calculation():
    """Profile percentile calculation (old vs optimized)."""
    print("=" * 80)
    print("Profiling: Percentile Calculation")
    print("=" * 80)
    
    from bisect import bisect_right
    import random
    
    # Generate test data
    random.seed(42)
    batch_size = 100
    num_files = 100
    all_grades = [random.uniform(0, 100) for _ in range(batch_size)]
    test_grades = [random.uniform(0, 100) for _ in range(num_files)]
    
    # Profile old method
    print("\n--- Old Method (O(n²)) ---")
    profiler_old = cProfile.Profile()
    profiler_old.enable()
    
    for grade in test_grades:
        percentile_val = (sum(1 for g in all_grades if g <= grade) / len(all_grades)) * 100
    
    profiler_old.disable()
    
    s = io.StringIO()
    stats = pstats.Stats(profiler_old, stream=s)
    stats.sort_stats('cumulative')
    stats.print_stats(10)
    print(s.getvalue())
    
    # Profile optimized method
    print("\n--- Optimized Method (O(n log n)) ---")
    profiler_new = cProfile.Profile()
    profiler_new.enable()
    
    sorted_grades = sorted(all_grades)
    for grade in test_grades:
        percentile_val = (bisect_right(sorted_grades, grade) / len(sorted_grades)) * 100
    
    profiler_new.disable()
    
    s = io.StringIO()
    stats = pstats.Stats(profiler_new, stream=s)
    stats.sort_stats('cumulative')
    stats.print_stats(10)
    print(s.getvalue())


def profile_chunk_reuse_check():
    """Profile chunk reuse check (old vs optimized)."""
    print("=" * 80)
    print("Profiling: Chunk Reuse Check")
    print("=" * 80)
    
    import hashlib
    
    # Generate test data
    num_previous = 100
    previous_questions_meta = [
        {"context_sha256": hashlib.sha256(f"context{i}".encode()).hexdigest(), "question_text": f"Question {i}"}
        for i in range(num_previous)
    ]
    ctx_text = "target_context"
    ctx_sha = hashlib.sha256(ctx_text.encode()).hexdigest()
    
    # Add target to end
    previous_questions_meta.append({"context_sha256": ctx_sha, "question_text": "Target question"})
    
    # Profile old method
    print("\n--- Old Method (O(n)) ---")
    profiler_old = cProfile.Profile()
    profiler_old.enable()
    
    for _ in range(1000):  # Multiple checks
        chunk_reused = any(
            q_meta.get("context_sha256") == ctx_sha 
            for q_meta in previous_questions_meta 
            if q_meta.get("context_sha256")
        )
    
    profiler_old.disable()
    
    s = io.StringIO()
    stats = pstats.Stats(profiler_old, stream=s)
    stats.sort_stats('cumulative')
    stats.print_stats(10)
    print(s.getvalue())
    
    # Profile optimized method
    print("\n--- Optimized Method (O(1) lookup) ---")
    profiler_new = cProfile.Profile()
    profiler_new.enable()
    
    used_ctx_hashes = {
        q_meta.get("context_sha256") 
        for q_meta in previous_questions_meta 
        if q_meta.get("context_sha256")
    }
    
    for _ in range(1000):  # Multiple checks
        chunk_reused = ctx_sha in used_ctx_hashes
    
    profiler_new.disable()
    
    s = io.StringIO()
    stats = pstats.Stats(profiler_new, stream=s)
    stats.sort_stats('cumulative')
    stats.print_stats(10)
    print(s.getvalue())


def main():
    """Run all profiling operations."""
    print("Performance Profiling for Hot Paths")
    print("=" * 80)
    print()
    
    # Profile percentile calculation
    profile_percentile_calculation()
    print()
    
    # Profile chunk reuse check
    profile_chunk_reuse_check()
    print()
    
    # Note: Question generation and grading profiling would require
    # actual implementation calls, which may need dependencies set up
    print("Note: Question generation and grading profiling require")
    print("      actual implementation calls with dependencies.")
    print("      Run these in a test environment with proper setup.")


if __name__ == "__main__":
    main()

