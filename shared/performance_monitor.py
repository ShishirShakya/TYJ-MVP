"""
Performance monitoring and metrics collection.

Phase 3.1: Performance monitoring for API calls and operations.

This module provides:
- Timing decorators for performance measurement
- Metrics collection for API calls
- Performance statistics
"""

import time
from typing import Dict, Any, Optional, Callable
from functools import wraps
from threading import Lock
from collections import defaultdict
import structlog

logger = structlog.get_logger(__name__)

# Thread-safe metrics storage
_metrics_lock = Lock()
_operation_timings: Dict[str, list] = defaultdict(list)
_operation_counts: Dict[str, int] = defaultdict(int)
_operation_errors: Dict[str, int] = defaultdict(int)


def record_timing(operation: str, duration: float, success: bool = True):
    """
    Record timing for an operation.
    
    Phase 3.1: Performance monitoring.
    
    Args:
        operation: Operation name (e.g., "generate_question")
        duration: Duration in seconds
        success: Whether operation succeeded
    """
    with _metrics_lock:
        _operation_timings[operation].append(duration)
        _operation_counts[operation] += 1
        
        # Keep only last 1000 timings per operation
        if len(_operation_timings[operation]) > 1000:
            _operation_timings[operation] = _operation_timings[operation][-1000:]
        
        if not success:
            _operation_errors[operation] += 1


def measure_performance(operation: str):
    """
    Decorator to measure function performance.
    
    Phase 3.1: Performance monitoring decorator.
    
    Usage:
        @measure_performance("generate_question")
        def generate_question(text):
            return expensive_operation(text)
    
    Args:
        operation: Operation name for metrics
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                raise
            finally:
                duration = time.time() - start_time
                record_timing(operation, duration, success)
        return wrapper
    return decorator


def get_performance_stats() -> Dict[str, Any]:
    """
    Get performance statistics for all operations.
    
    Phase 3.1: Performance monitoring.
    
    Returns:
        Dictionary with performance statistics
    """
    with _metrics_lock:
        stats = {}
        
        for operation, timings in _operation_timings.items():
            if not timings:
                continue
            
            sorted_timings = sorted(timings)
            count = len(timings)
            
            # Calculate percentiles
            p50_idx = int(count * 0.5)
            p95_idx = int(count * 0.95)
            p99_idx = int(count * 0.99)
            
            stats[operation] = {
                "count": count,
                "errors": _operation_errors.get(operation, 0),
                "error_rate": _operation_errors.get(operation, 0) / count if count > 0 else 0,
                "min": min(timings),
                "max": max(timings),
                "mean": sum(timings) / count,
                "p50": sorted_timings[p50_idx] if p50_idx < count else 0,
                "p95": sorted_timings[p95_idx] if p95_idx < count else 0,
                "p99": sorted_timings[p99_idx] if p99_idx < count else 0,
            }
        
        return stats


def reset_metrics():
    """Reset all performance metrics."""
    with _metrics_lock:
        _operation_timings.clear()
        _operation_counts.clear()
        _operation_errors.clear()

