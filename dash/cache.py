"""
Cache management for dash.ipynb.

This module handles transcript caching with FERPA compliance:
- Cache expiration (1 hour timeout)
- Session ID obfuscation for privacy
- Cache cleanup operations
- Thread-safe operations for concurrent access

The cache dictionary is stored at module level to persist across requests.
THREAD-SAFETY: All cache operations are protected by a lock for concurrent access.
"""

import threading
from typing import Dict, Any, Optional
from dash.config import TRANSCRIPT_CACHE_TIMEOUT_SECONDS, logger
from shared.time_provider import get_default_time_provider

# Module-level cache dictionary
# FERPA COMPLIANCE: Cache expires after 1 hour to limit data retention
# RESOURCE MANAGEMENT: Cache size bounded to prevent memory exhaustion (Principle #9)
# Format: {filename: {"transcript": str, "timestamp": float}}
_batch_decrypt_transcript_cache: Dict[str, Dict[str, Any]] = {}

# THREAD-SAFETY: Lock protects cache dictionary from concurrent access
_cache_lock = threading.Lock()

# RESOURCE MANAGEMENT: Maximum cache size to prevent unbounded memory growth
# If cache exceeds this size, oldest entries are evicted during cleanup
MAX_CACHE_SIZE = 1000  # Maximum number of cached transcripts


def get_cache_entry(filename: str) -> Optional[Dict[str, Any]]:
    """
    Get cache entry for a filename.
    Returns None if entry doesn't exist or is expired.
    
    THREAD-SAFE: Protected by lock for concurrent access.
    
    Args:
        filename: Filename to look up in cache
        
    Returns:
        Cache entry dictionary or None if not found/expired
    """
    with _cache_lock:
        entry = _batch_decrypt_transcript_cache.get(filename)
        if entry and _is_cache_entry_valid(entry):
            return entry.copy()  # Return copy to prevent external mutation
    return None


def set_cache_entry(filename: str, transcript: Optional[str]) -> None:
    """
    Set cache entry for a filename.
    Stores transcript with current timestamp.
    
    THREAD-SAFE: Protected by lock for concurrent access.
    RESOURCE MANAGEMENT: Enforces cache size bounds to prevent memory exhaustion.
    
    Args:
        filename: Filename to store in cache
        transcript: Transcript text (or None to clear entry)
    """
    with _cache_lock:
        if transcript is None:
            # Clear entry if transcript is None
            _batch_decrypt_transcript_cache.pop(filename, None)
        else:
            # RESOURCE MANAGEMENT: Enforce cache size bounds atomically
            # THREAD-SAFETY: Check size and evict atomically within lock to prevent race conditions
            # If cache is full, evict oldest entries first (atomic operation)
            while len(_batch_decrypt_transcript_cache) >= MAX_CACHE_SIZE:
                # Find oldest entry by timestamp (atomic within lock)
                if not _batch_decrypt_transcript_cache:
                    break  # Safety check: empty cache
                oldest_key = min(
                    _batch_decrypt_transcript_cache.keys(),
                    key=lambda k: _batch_decrypt_transcript_cache[k].get("timestamp", 0)
                )
                _batch_decrypt_transcript_cache.pop(oldest_key, None)
                logger.debug(
                    "cache_eviction",
                    message="Evicted oldest cache entry to maintain size limit",
                    evicted_key=oldest_key,
                    cache_size=len(_batch_decrypt_transcript_cache)
                )
            
            # DETERMINISTIC: Use time provider instead of time.time() for testability
            current_time = get_default_time_provider().time()
            _batch_decrypt_transcript_cache[filename] = {
                "transcript": transcript,
                "timestamp": current_time
            }


def _is_cache_entry_valid(entry: Dict[str, Any]) -> bool:
    """
    Check if cache entry is still valid (not expired).
    
    DETERMINISTIC: Uses time provider for deterministic behavior (Principle #5).
    
    Args:
        entry: Cache entry dictionary with 'timestamp' key
        
    Returns:
        True if entry is valid, False if expired or invalid
    """
    if not entry or "timestamp" not in entry:
        return False
    # DETERMINISTIC: Use time provider instead of time.time() for testability
    current_time = get_default_time_provider().time()
    age_seconds = current_time - entry["timestamp"]
    return age_seconds < TRANSCRIPT_CACHE_TIMEOUT_SECONDS


def _cleanup_expired_cache() -> int:
    """
    FERPA COMPLIANCE: Remove expired cache entries.
    
    THREAD-SAFE: Protected by lock for concurrent access.
    
    Returns:
        Number of expired entries removed
    """
    with _cache_lock:
        expired_keys = [
            k for k, v in _batch_decrypt_transcript_cache.items()
            if not _is_cache_entry_valid(v)
        ]
        for key in expired_keys:
            _batch_decrypt_transcript_cache.pop(key, None)
    
    if expired_keys:
        logger.info(
            "cache_cleanup",
            message="Cleaned up expired cache entries",
            expired_count=len(expired_keys)
        )
    
    return len(expired_keys)


def _obfuscate_session_id(session_id: str) -> str:
    """
    FERPA COMPLIANCE: Obfuscate Session IDs to protect PII.
    Returns masked ID showing only last 4 characters.
    
    Args:
        session_id: Original session ID string
        
    Returns:
        Obfuscated session ID (e.g., "****abcd" for "12345678abcd")
    """
    if not session_id or len(session_id) <= 4:
        return "****" if session_id else ""
    # Show only last 4 characters, mask the rest
    return f"****{session_id[-4:]}"


# Export cache dictionary access functions for dependency injection
def get_cache_dict() -> Dict[str, Dict[str, Any]]:
    """
    Get a copy of the cache dictionary (for dependency injection).
    
    SECURITY: Returns a copy to prevent external mutation of cache state.
    Direct access should be avoided; use get_cache_entry/set_cache_entry instead.
    
    Returns:
        Copy of the cache dictionary
    """
    with _cache_lock:
        return _batch_decrypt_transcript_cache.copy()

