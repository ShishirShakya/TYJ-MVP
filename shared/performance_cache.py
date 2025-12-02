"""
Performance caching for API responses and expensive operations.

Phase 3.1: Response caching to reduce API calls and improve performance.

This module provides caching for:
- Question generation responses
- Answer grading responses
- TTS audio generation
- Follow-up question generation

THREAD-SAFETY: All cache operations are thread-safe using locks.
"""

import time
import hashlib
import json
from threading import Lock
from typing import Dict, Any, Optional, Tuple
from functools import wraps

# Cache configuration
RESPONSE_CACHE_TTL_SEC = 3600  # 1 hour TTL for API responses
MAX_CACHE_ENTRIES = 1000  # Maximum cache entries
CACHE_CLEANUP_INTERVAL_SEC = 300  # Cleanup every 5 minutes

# Thread-safe cache storage
_cache_lock = Lock()
_response_cache: Dict[str, Dict[str, Any]] = {}
_last_cleanup_time = time.time()


def _get_cache_key(operation: str, *args, **kwargs) -> str:
    """
    Generate cache key from operation name and arguments.
    
    Args:
        operation: Operation name (e.g., "generate_question")
        *args: Positional arguments
        **kwargs: Keyword arguments
        
    Returns:
        Cache key string
    """
    # Create deterministic key from operation and arguments
    key_data = {
        "operation": operation,
        "args": args,
        "kwargs": sorted(kwargs.items()) if kwargs else []
    }
    key_str = json.dumps(key_data, sort_keys=True, default=str)
    return hashlib.sha256(key_str.encode()).hexdigest()


def _is_cache_entry_valid(entry: Dict[str, Any]) -> bool:
    """
    Check if cache entry is still valid (not expired).
    
    Args:
        entry: Cache entry dictionary
        
    Returns:
        True if entry is valid, False otherwise
    """
    if not entry:
        return False
    
    timestamp = entry.get("timestamp", 0)
    ttl = entry.get("ttl", RESPONSE_CACHE_TTL_SEC)
    
    return (time.time() - timestamp) < ttl


def _cleanup_cache():
    """Remove expired entries from cache."""
    global _last_cleanup_time
    
    current_time = time.time()
    if current_time - _last_cleanup_time < CACHE_CLEANUP_INTERVAL_SEC:
        return  # Too soon for cleanup
    
    _last_cleanup_time = current_time
    
    with _cache_lock:
        expired_keys = [
            key for key, entry in _response_cache.items()
            if not _is_cache_entry_valid(entry)
        ]
        
        for key in expired_keys:
            _response_cache.pop(key, None)
        
        # If cache is still too large, remove oldest entries
        if len(_response_cache) > MAX_CACHE_ENTRIES:
            sorted_entries = sorted(
                _response_cache.items(),
                key=lambda x: x[1].get("timestamp", 0)
            )
            # Remove oldest 10% of entries
            remove_count = len(sorted_entries) // 10
            for key, _ in sorted_entries[:remove_count]:
                _response_cache.pop(key, None)


def get_cached_response(operation: str, *args, **kwargs) -> Optional[Any]:
    """
    Get cached response if available and valid.
    
    Args:
        operation: Operation name
        *args: Positional arguments
        **kwargs: Keyword arguments
        
    Returns:
        Cached response if available, None otherwise
    """
    cache_key = _get_cache_key(operation, *args, **kwargs)
    
    with _cache_lock:
        entry = _response_cache.get(cache_key)
        if entry and _is_cache_entry_valid(entry):
            return entry.get("response")
    
    return None


def set_cached_response(
    operation: str,
    response: Any,
    ttl: int = RESPONSE_CACHE_TTL_SEC,
    *args,
    **kwargs
) -> None:
    """
    Cache a response.
    
    Args:
        operation: Operation name
        response: Response to cache
        ttl: Time-to-live in seconds
        *args: Positional arguments (for cache key)
        **kwargs: Keyword arguments (for cache key)
    """
    cache_key = _get_cache_key(operation, *args, **kwargs)
    
    with _cache_lock:
        _response_cache[cache_key] = {
            "response": response,
            "timestamp": time.time(),
            "ttl": ttl
        }
        
        # Periodic cleanup
        _cleanup_cache()


def cache_response(operation: str, ttl: int = RESPONSE_CACHE_TTL_SEC):
    """
    Decorator to cache function responses.
    
    Phase 3.1: Performance optimization decorator.
    
    Usage:
        @cache_response("generate_question", ttl=3600)
        def generate_question(text):
            return expensive_operation(text)
    
    Args:
        operation: Operation name for cache key
        ttl: Time-to-live in seconds
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Check cache first
            cached = get_cached_response(operation, *args, **kwargs)
            if cached is not None:
                return cached
            
            # Call function and cache result
            result = func(*args, **kwargs)
            set_cached_response(operation, result, ttl, *args, **kwargs)
            return result
        return wrapper
    return decorator


def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics for monitoring.
    
    Phase 3.1: Performance monitoring.
    
    Returns:
        Dictionary with cache statistics
    """
    with _cache_lock:
        valid_entries = sum(
            1 for entry in _response_cache.values()
            if _is_cache_entry_valid(entry)
        )
        
        return {
            "total_entries": len(_response_cache),
            "valid_entries": valid_entries,
            "expired_entries": len(_response_cache) - valid_entries,
            "max_entries": MAX_CACHE_ENTRIES,
            "cache_utilization": len(_response_cache) / MAX_CACHE_ENTRIES
        }

