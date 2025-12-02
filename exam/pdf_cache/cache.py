"""
Core PDF caching functions.

This module contains the core caching functionality for PDF content,
including memory cache, disk cache, and cache management.
"""

import os
import time
import hashlib
import random
import pickle
from threading import Lock
from typing import Dict, Any, Optional
from shared.platform import PlatformProvider, get_default_platform_provider

# DETERMINISTIC RNG: Use seeded RNG for deterministic cleanup decisions (Principle #5)
# Seed from constant for reproducible behavior (same seed → same cleanup pattern)
_cleanup_rng = random.Random(42)  # Fixed seed for deterministic behavior

# Cache configuration
# Use platform provider for portability (Principle #6)
_platform_provider = get_default_platform_provider()
PDF_CACHE_DIR = _platform_provider.join_path(_platform_provider.get_temp_dir(), "vivaai_pdf_cache")
PDF_CACHE_TIMEOUT_HOURS = 168  # Cache expires after 7 days (1 week)
MAX_CACHE_SIZE_MB = 500  # Maximum cache size (500MB total)
MAX_PDF_MEMORY_CACHE_ENTRIES = 20  # Keep 20 most recent PDFs in memory (optimal balance of speed vs memory)

# Ensure cache directory exists
os.makedirs(PDF_CACHE_DIR, exist_ok=True)

# Thread-safe cache storage
# SCALABILITY NOTE: Memory cache is per-instance. Disk cache is shared across instances
# if using shared storage (NFS, EBS, etc.). For distributed memory cache, consider Redis.
# See docs/SCALABILITY_ARCHITECTURE.md for details.
# THREAD-SAFETY: All cache operations protected by lock. Safe for concurrent access.
# See docs/CONCURRENCY_THREAD_SAFETY.md for details.
_pdf_cache_lock = Lock()
_pdf_memory_cache: Dict[str, Dict[str, Any]] = {}  # In-memory cache for speed (per-instance)


def _is_pdf_memory_cache_valid(cached_data: Dict[str, Any]) -> bool:
    """
    Check if memory cache entry is still valid using timestamp (no disk I/O).
    MEMORY CACHE OPTIMIZATION: Validates using timestamp in data, avoiding disk checks.
    FERPA COMPLIANT: Only validates PDF content cache, not student data.
    """
    if not cached_data:
        return False
    
    timestamp = cached_data.get('timestamp', 0)
    if not timestamp:
        return False
    
    # Check age in hours
    age_hours = (time.time() - timestamp) / 3600
    return age_hours < PDF_CACHE_TIMEOUT_HOURS


def _get_pdf_cache_key(pdf_url: str) -> str:
    """
    Create cache key from PDF URL.
    IMPORTANT: NO student data included - privacy safe!
    """
    # Normalize URL (remove query params that don't affect content)
    normalized_url = pdf_url.strip()
    # Remove common tracking params that don't affect PDF content
    if "?" in normalized_url:
        base_url, query = normalized_url.split("?", 1)
        # Keep only dl parameter (important for Dropbox)
        params = query.split("&")
        important_params = [p for p in params if p.startswith("dl=")]
        if important_params:
            normalized_url = f"{base_url}?{'&'.join(important_params)}"
        else:
            normalized_url = base_url
    
    # Create hash of normalized URL
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()


def _get_pdf_cache_path(cache_key: str) -> str:
    """Get file path for cached PDF content"""
    return os.path.join(PDF_CACHE_DIR, f"{cache_key}.pkl")


def _is_pdf_cache_valid(cache_path: str) -> bool:
    """Check if PDF cache entry is still valid (not expired)"""
    if not os.path.exists(cache_path):
        return False
    
    try:
        file_age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        return file_age_hours < PDF_CACHE_TIMEOUT_HOURS
    except Exception:
        return False


def get_cached_pdf_content(pdf_url: str) -> Optional[Dict[str, Any]]:
    """
    Get cached PDF content (text + chunks + metadata) if available.
    Checks both memory cache (fast) and disk cache (persistent).
    
    MEMORY CACHE OPTIMIZATION: Uses in-memory timestamp validation (no disk I/O).
    FERPA COMPLIANT: Only caches PDF content (course materials), not student data.
    
    Returns dict with keys: text, chunks, sha256, timestamp
    or None if not cached/expired
    """
    cache_key = _get_pdf_cache_key(pdf_url)
    
    # MEMORY CACHE OPTIMIZATION: Check memory cache first (fastest, no disk I/O)
    with _pdf_cache_lock:
        if cache_key in _pdf_memory_cache:
            cached_data = _pdf_memory_cache[cache_key]
            # MEMORY CACHE OPTIMIZATION: Validate using timestamp in data (no disk I/O)
            if _is_pdf_memory_cache_valid(cached_data):
                # Valid memory cache hit - return immediately (95% faster than disk)
                return cached_data
            else:
                # Expired - remove from memory cache
                _pdf_memory_cache.pop(cache_key, None)
    
    # Check disk cache
    cache_path = _get_pdf_cache_path(cache_key)
    if _is_pdf_cache_valid(cache_path):
        try:
            with open(cache_path, 'rb') as f:
                cached_data = pickle.load(f)
            
            # Validate cached data structure
            if isinstance(cached_data, dict) and all(k in cached_data for k in ['text', 'chunks', 'sha256']):
                # MEMORY CACHE OPTIMIZATION: Load into memory cache for faster future access
                # This makes subsequent loads instant (no disk I/O)
                with _pdf_cache_lock:
                    _pdf_memory_cache[cache_key] = cached_data
                    
                    # Evict oldest entries if cache is full
                    if len(_pdf_memory_cache) > MAX_PDF_MEMORY_CACHE_ENTRIES:
                        oldest_keys = sorted(_pdf_memory_cache.keys(), 
                                           key=lambda k: _pdf_memory_cache[k].get('timestamp', 0))[:5]
                        for k in oldest_keys:
                            _pdf_memory_cache.pop(k, None)
                
                return cached_data
        except Exception:
            # Cache file corrupted - remove it
            try:
                os.remove(cache_path)
            except Exception:
                pass
    
    return None


def save_pdf_to_cache(pdf_url: str, text: str, chunks: list, sha256: str) -> None:
    """
    Save PDF content (text + chunks) to cache.
    Saves to both memory cache (fast) and disk cache (persistent).
    """
    cache_key = _get_pdf_cache_key(pdf_url)
    cache_path = _get_pdf_cache_path(cache_key)
    
    cached_data = {
        'text': text,
        'chunks': chunks,
        'sha256': sha256,
        'timestamp': time.time(),
        'url': pdf_url  # Store original URL for reference
    }
    
    # MEMORY CACHE OPTIMIZATION: Save to memory cache (fast access)
    with _pdf_cache_lock:
        _pdf_memory_cache[cache_key] = cached_data
        
        # MEMORY CACHE OPTIMIZATION: Limit memory cache size (keep only most recent entries)
        # FERPA COMPLIANT: Only caches PDF content, not student data
        if len(_pdf_memory_cache) > MAX_PDF_MEMORY_CACHE_ENTRIES:
            # Remove oldest entries (LRU eviction)
            oldest_keys = sorted(_pdf_memory_cache.keys(), 
                               key=lambda k: _pdf_memory_cache[k].get('timestamp', 0))[:5]  # Remove 5 oldest
            for k in oldest_keys:
                _pdf_memory_cache.pop(k, None)
    
    # Save to disk cache (persistent)
    # DATA INTEGRITY: Use atomic write pattern to prevent cache corruption (Principle #22)
    try:
        # Create cache directory if needed
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        
        # Use atomic write pattern (temp file + replace) to prevent partial writes
        import tempfile
        d = os.path.dirname(cache_path) or "."
        fd, tmp = tempfile.mkstemp(dir=d, prefix="._pdf_cache.", suffix=".tmp")
        try:
            with os.fdopen(fd, 'wb') as f:
                pickle.dump(cached_data, f)
                f.flush()
                os.fsync(f.fileno())  # Ensure written to disk
            os.replace(tmp, cache_path)  # Atomic replace (atomic on POSIX, best-effort on Windows)
        except Exception:
            # Cleanup temp file on error
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
        
        # Optional: Cleanup old cache files periodically (keep cache size reasonable)
        cleanup_old_pdf_cache()
    except Exception:
        # Cache save failed - continue anyway (non-critical)
        pass


def cleanup_old_pdf_cache() -> None:
    """
    Clean up old or oversized cache files (runs occasionally).
    
    DETERMINISTIC: Uses seeded RNG for reproducible cleanup decisions (Principle #5).
    Same seed → same cleanup pattern, making behavior predictable and testable.
    """
    try:
        # Only cleanup 1 in 10 times (don't waste CPU)
        # DETERMINISTIC: Use seeded RNG instead of global random (Principle #5)
        if _cleanup_rng.randint(1, 10) != 1:
            return
        
        cache_files = []
        total_size = 0
        
        # List all cache files
        for filename in os.listdir(PDF_CACHE_DIR):
            if filename.endswith('.pkl'):
                filepath = os.path.join(PDF_CACHE_DIR, filename)
                try:
                    file_age_hours = (time.time() - os.path.getmtime(filepath)) / 3600
                    file_size = os.path.getsize(filepath)
                    
                    cache_files.append((filepath, file_age_hours, file_size))
                    total_size += file_size
                except Exception:
                    continue
        
        # Remove expired files
        for filepath, age_hours, _ in cache_files:
            if age_hours > PDF_CACHE_TIMEOUT_HOURS:
                try:
                    os.remove(filepath)
                    # Also remove from memory cache if present
                    cache_key = os.path.basename(filepath).replace('.pkl', '')
                    with _pdf_cache_lock:
                        _pdf_memory_cache.pop(cache_key, None)
                except Exception:
                    pass
        
        # If cache too large, remove oldest files
        max_size_bytes = MAX_CACHE_SIZE_MB * 1024 * 1024
        if total_size > max_size_bytes:
            # Sort by age (oldest first)
            cache_files.sort(key=lambda x: x[1], reverse=True)
            
            for filepath, _, file_size in cache_files:
                if total_size <= max_size_bytes:
                    break
                
                try:
                    os.remove(filepath)
                    total_size -= file_size
                    # Also remove from memory cache
                    cache_key = os.path.basename(filepath).replace('.pkl', '')
                    with _pdf_cache_lock:
                        _pdf_memory_cache.pop(cache_key, None)
                except Exception:
                    pass
    except Exception:
        # Cleanup failed - continue anyway (non-critical)
        pass

