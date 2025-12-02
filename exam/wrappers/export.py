"""
Export wrapper functions for exam.ipynb.

These wrapper functions bridge between the notebook's global variables/context variables
and the modular export functions. They handle backward compatibility and provide a clean interface.

Note: These functions accept global variables and wrapper functions as parameters to avoid
direct access to notebook globals. The notebook should create thin wrapper functions that
pass the globals and wrapper functions from its scope.
"""

from typing import Dict, List, Optional, Callable, Tuple

from exam.export import (
    finalize_and_export_encrypted as _finalize_and_export_encrypted_base,
    auto_wipe_local_after_export as _auto_wipe_local_after_export_base,
)


def _auto_wipe_local_after_export(
    s: Dict,
    *,
    PERSIST_OK: bool,
    CHUNKS: List[str],
    TEXTBOOK_SHA256: str,
) -> List[str]:
    """
    Wrapper for auto_wipe_local_after_export that handles global variables.
    
    This wrapper handles global variables (PERSIST_OK, CHUNKS, TEXTBOOK_SHA256)
    that are used in the notebook but not in the module.
    
    Args:
        s: State dictionary
        PERSIST_OK: Persistence flag from notebook (will be updated to False)
        CHUNKS: Global CHUNKS variable from notebook (will be updated)
        TEXTBOOK_SHA256: Global TEXTBOOK_SHA256 variable from notebook (will be updated)
    
    Returns:
        List of removed file paths
    
    Note: The notebook will need to update its globals after calling this function.
    """
    # Call the base function
    removed = _auto_wipe_local_after_export_base(s)
    
    # Return updated values for notebook to update globals
    # Note: The notebook will update PERSIST_OK, CHUNKS, TEXTBOOK_SHA256 after calling
    return removed


def finalize_and_export_encrypted(
    s: Dict,
    *,
    # Wrapper functions from notebook
    ensure_state_fn: Callable,
    save_state_to_disk_fn: Callable,
    get_chunks_fn: Callable,
    get_textbook_sha256_fn: Callable,
    get_max_answer_timeout_sec_fn: Callable,
    # Global variables from notebook
    PERSIST_OK: bool,
    CHUNKS: List[str],
    TEXTBOOK_SHA256: str,
) -> Tuple[str, str]:
    """
    Wrapper for finalize_and_export_encrypted that handles global variables and context variables.
    
    This wrapper handles global variables (PERSIST_OK, CHUNKS, TEXTBOOK_SHA256) and
    context variables (get_chunks, get_textbook_sha256, get_max_answer_timeout_sec) that
    are used in the notebook but need to be passed to the module function.
    
    Args:
        s: State dictionary
        ensure_state_fn: ensure_state function from notebook
        save_state_to_disk_fn: save_state_to_disk function from notebook
        get_chunks_fn: get_chunks function from notebook
        get_textbook_sha256_fn: get_textbook_sha256 function from notebook
        get_max_answer_timeout_sec_fn: get_max_answer_timeout_sec function from notebook
        PERSIST_OK: Persistence flag from notebook
        CHUNKS: Global CHUNKS variable from notebook
        TEXTBOOK_SHA256: Global TEXTBOOK_SHA256 variable from notebook
    
    Returns:
        Tuple of (file_path, summary_message)
    """
    # Call the base function with all necessary parameters
    return _finalize_and_export_encrypted_base(
        s,
        ensure_state_fn=ensure_state_fn,
        save_state_to_disk_fn=save_state_to_disk_fn,
        get_chunks_fn=get_chunks_fn,
        get_textbook_sha256_fn=get_textbook_sha256_fn,
        get_max_answer_timeout_sec_fn=get_max_answer_timeout_sec_fn,
        PERSIST_OK=PERSIST_OK,
        CHUNKS=CHUNKS,
        TEXTBOOK_SHA256=TEXTBOOK_SHA256,
    )

