"""
Configuration wrapper functions for exam.ipynb.

These wrapper functions bridge between the notebook's global variables/context variables
and the modular functions. They handle backward compatibility and provide a clean interface.

Note: These functions accept global variables as parameters to avoid direct access
to notebook globals. The notebook should create thin wrapper functions that pass
the globals from its scope.
"""

from typing import Tuple, List, Optional, Callable

from shared.config_parsing import (
    parse_professor_link_and_setup as _parse_professor_link_and_setup_shared,
)
from exam.context_vars import (
    course_id_ctx,
    exam_id_ctx,
    n_questions_ctx,
    followups_min_ctx,
    followups_max_ctx,
    passphrase_ctx,
    max_answer_timeout_sec_ctx,
    get_chunks as get_chunks_ctx,
    get_n_questions,
    get_followups_max,
    get_max_answer_timeout_sec,
    chunks_ctx,
    textbook_sha256_ctx,
)
from exam.pdf_cache import (
    load_pdf_from_url_with_cache as _load_pdf_from_url_with_cache_base,
    validate_chunks_available as _validate_chunks_available_base,
)
from exam.config import logger


def parse_professor_link_and_setup(
    url: str,
    *,
    # Callback functions (will be passed from notebook)
    load_pdf_callback: Optional[Callable] = None,
    validate_chunks_callback: Optional[Callable] = None,
    set_globals_callback: Optional[Callable] = None,
    calculate_session_duration_callback: Optional[Callable] = None,
) -> Tuple[bool, str, dict]:
    """
    Parse professor's link URL and automatically set up the examination.
    Returns: (success: bool, status_message: str, state_updates: dict)
    
    This is a wrapper around the shared parse_professor_link_and_setup function
    that provides exam-specific callbacks for context variables, PDF loading, etc.
    
    Args:
        url: Professor's link URL to parse
        load_pdf_callback: Callback function for loading PDF (from notebook)
        validate_chunks_callback: Callback function for validating chunks (from notebook)
        set_globals_callback: Callback function for setting global variables (from notebook)
        calculate_session_duration_callback: Callback function for calculating session duration (from notebook)
    
    Returns:
        Tuple of (success, status_message, state_updates)
    """
    # Define callbacks for exam-specific operations
    def set_context_callback(config_dict):
        """
        Set exam context variables.
        
        NOTE: Converts time_per_question (external/URL name) to max_answer_timeout_sec_ctx (internal/SSOT).
        This is the conversion point from external naming to internal naming.
        See exam/context_vars.py for naming convention documentation.
        """
        course_id_ctx.set(config_dict["course_id"])
        exam_id_ctx.set(config_dict["exam_id"])
        n_questions_ctx.set(config_dict["num_questions"])
        followups_min_ctx.set(config_dict["min_followups"])
        followups_max_ctx.set(config_dict["max_followups"])
        passphrase_ctx.set(config_dict["passphrase"])
        # Convert external name (time_per_question) to internal SSOT (max_answer_timeout_sec_ctx)
        max_answer_timeout_sec_ctx.set(config_dict["time_per_question"])
    
    # Use provided callbacks or defaults
    if set_globals_callback is None:
        def default_set_globals_callback(config_dict):
            """Set global variables for backward compatibility"""
            # Note: This callback would need to update the notebook's globals
            # The notebook will handle this through state_updates
            pass
        set_globals_callback = default_set_globals_callback
    
    if calculate_session_duration_callback is None:
        def default_calculate_session_duration_callback():
            """Recalculate MAX_SESSION_DURATION_SEC with new values"""
            max_timeout = get_max_answer_timeout_sec(None)  # No state available in callback, use context var or default
            n_questions = get_n_questions()
            followups_max = get_followups_max()
            return (max_timeout + 30 + 10) * (n_questions + (n_questions * followups_max))
        calculate_session_duration_callback = default_calculate_session_duration_callback
    
    # Call shared function with exam mode parameters and callbacks
    return _parse_professor_link_and_setup_shared(
        url,
        require_pdf=True,
        load_pdf=True,
        set_exam_context=True,
        default_decryption="",
        load_pdf_callback=load_pdf_callback,
        validate_chunks_callback=validate_chunks_callback,
        set_context_callback=set_context_callback,
        set_globals_callback=set_globals_callback,
        calculate_session_duration_callback=calculate_session_duration_callback
    )


def get_chunks(CHUNKS: Optional[List[str]] = None) -> List[str]:
    """
    Get chunks from context variable, fallback to global CHUNKS variable.
    
    This wrapper checks both the context variable and the global CHUNKS variable
    to handle cases where context variables might not be shared across Gradio handlers.
    
    Args:
        CHUNKS: Global CHUNKS variable from notebook (optional, for fallback)
    
    Returns:
        List of chunks
    """
    # First try to get from context variable
    chunks = get_chunks_ctx()
    
    # If context variable returns fallback message or empty, check global CHUNKS
    if not chunks or (len(chunks) == 1 and chunks[0].startswith("(No textbook content available")):
        # Check global CHUNKS variable as fallback
        if CHUNKS and not (len(CHUNKS) == 1 and CHUNKS[0].startswith("(No textbook content available")):
            return CHUNKS
    return chunks


def load_pdf_from_url_with_cache(
    url: str,
    *,
    TEXTBOOK_SHA256: Optional[str] = None,
    CHUNKS: Optional[List[str]] = None,
) -> Tuple[str, str, Optional[List[str]]]:
    """
    Wrapper for load_pdf_from_url_with_cache that handles global variables.
    Returns (status_message, updated_sha256, updated_chunks)
    
    Args:
        url: PDF URL to load
        TEXTBOOK_SHA256: Global TEXTBOOK_SHA256 variable (will be updated)
        CHUNKS: Global CHUNKS variable (will be updated)
    
    Returns:
        Tuple of (status_message, updated_sha256, updated_chunks)
        Note: updated_chunks is returned so notebook can update its global
    """
    # Call base function with context variables and current global values
    status_msg, new_sha256, new_chunks = _load_pdf_from_url_with_cache_base(
        url,
        logger=logger,
        textbook_sha256_ctx=textbook_sha256_ctx,
        chunks_ctx=chunks_ctx,
        current_textbook_sha256=TEXTBOOK_SHA256,
    )
    
    # Return updated values for notebook to update globals
    return status_msg, new_sha256, new_chunks


def validate_chunks_available(get_chunks_fn: Optional[Callable] = None) -> Tuple[bool, str, int]:
    """
    Wrapper for validate_chunks_available that uses notebook getter function.
    Returns (is_valid, error_message, valid_count)
    
    Args:
        get_chunks_fn: Function to get chunks (defaults to get_chunks from this module)
    
    Returns:
        Tuple of (is_valid, error_message, valid_count)
    """
    if get_chunks_fn is None:
        # Use a default that doesn't require CHUNKS parameter
        get_chunks_fn = lambda: get_chunks()
    return _validate_chunks_available_base(get_chunks_fn)
