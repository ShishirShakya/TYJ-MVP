"""
PDF chunk validation functionality.

This module contains functions to validate that PDF chunks are available
and valid for question generation.
"""

from typing import Tuple

from shared.pdf_processing import _validate_context
from shared.constants import (
    PDF_ERROR_SUFFIX_LOAD_BEFORE_START,
    PDF_ERROR_SUFFIX_LOAD_VALID,
    PDF_ERROR_SUFFIX_RELOAD,
    format_pdf_validation_error,
)


def validate_chunks_available(get_chunks_fn) -> Tuple[bool, str, int]:
    """
    Validate that CHUNKS contains valid content for question generation.
    
    Args:
        get_chunks_fn: Function to get chunks (for thread safety)
    
    Returns:
        tuple[bool, str, int]: (is_valid, error_message, valid_count)
        - is_valid: True if valid chunks are available, False otherwise
        - error_message: Detailed error message if validation fails, empty string if valid
        - valid_count: Number of valid chunks found (0 if validation fails)
    
    This function checks:
    1. CHUNKS is not empty
    2. CHUNKS does not contain only fallback message
    3. All chunks pass _validate_context() validation
    4. At least one valid chunk exists
    """
    # Check if chunks are available (use helper function for thread safety)
    chunks = get_chunks_fn()
    if not chunks:
        return False, f"No PDF content loaded. {PDF_ERROR_SUFFIX_LOAD_BEFORE_START}", 0
    
    # Check if CHUNKS contains only fallback message
    if len(chunks) == 1 and chunks[0].startswith("(No textbook content available"):
        return False, "PDF content not available. Please load a valid PDF from the Settings tab.", 0
    
    # Validate all chunks
    valid_chunks = []
    for chunk in chunks:
        is_valid, error = _validate_context(chunk, min_chars=50)
        if is_valid:
            valid_chunks.append(chunk)
    
    # Check if we have at least one valid chunk
    if not valid_chunks:
        chunks = get_chunks_fn()
        return False, f"{format_pdf_validation_error(len(chunks), 0)}. {PDF_ERROR_SUFFIX_RELOAD}", 0
    
    # Success - return valid count
    chunks = get_chunks_fn()
    return True, f"PDF validated: {len(valid_chunks)}/{len(chunks)} chunks are valid.", len(valid_chunks)

