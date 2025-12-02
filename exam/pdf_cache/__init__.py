"""
PDF caching module for exam.ipynb.

This module contains PDF caching functionality including:
- Core caching functions (memory and disk cache)
- PDF loading with caching
- Chunk validation
"""

from exam.pdf_cache.cache import (
    get_cached_pdf_content,
    save_pdf_to_cache,
    cleanup_old_pdf_cache,
    PDF_CACHE_DIR,
    PDF_CACHE_TIMEOUT_HOURS,
    MAX_CACHE_SIZE_MB,
    MAX_PDF_MEMORY_CACHE_ENTRIES,
)

# Note: Internal cache functions are not exported

from exam.pdf_cache.loader import load_pdf_from_url_with_cache

from exam.pdf_cache.validation import validate_chunks_available

__all__ = [
    # Cache functions
    "get_cached_pdf_content",
    "save_pdf_to_cache",
    "cleanup_old_pdf_cache",
    # Loader
    "load_pdf_from_url_with_cache",
    # Validation
    "validate_chunks_available",
    # Constants
    "PDF_CACHE_DIR",
    "PDF_CACHE_TIMEOUT_HOURS",
    "MAX_CACHE_SIZE_MB",
    "MAX_PDF_MEMORY_CACHE_ENTRIES",
]

