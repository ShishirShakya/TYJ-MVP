"""
Wipe local state after export module for exam.ipynb.

This module contains functions for wiping local state after exam export:
- Auto-wipe local state after export
"""

import os
from typing import Dict, Any, List

from exam.file_utils import _paths_for_session
from exam.audio import cleanup_session_tmp
from exam.context_vars import chunks_ctx, textbook_sha256_ctx
from shared.constants import FALLBACK_NO_TEXTBOOK_CONTENT


def auto_wipe_local_after_export(s: Dict[str, Any]) -> List[str]:
    """
    Wipe local state after export to prevent resume.
    
    This function removes local state files, device keys, and clears PDF data
    after the exam is exported to prevent resume attempts.
    
    Args:
        s: State dictionary
        
    Returns:
        List of removed file names
    """
    from exam.config import PERSIST_OK
    
    # Note: PERSIST_OK is imported from config, but we need to modify it
    # Since it's a mutable state variable, we'll import it and modify it
    # The actual modification happens in the notebook wrapper
    
    p = _paths_for_session(s)
    removed = []
    for path in (p["STATE_PATH"], p["DEVICE_KEY_PATH"]):
        try:
            if os.path.exists(path):
                os.remove(path)
                removed.append(os.path.basename(path))
        except Exception:
            pass
    try:
        with open(p["TOMBSTONE_PATH"], "wb") as f:
            f.write(b"sealed")
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        pass
    
    # Note: PERSIST_OK modification is handled in the notebook wrapper
    # since it's a mutable state variable
    
    cleanup_session_tmp(s)
    
    # MEMORY OPTIMIZATION: Clear PDF data after exam to reduce system load
    # This frees memory from chunks and PDF text after the exam is complete
    # Update context variables (thread-safe)
    # SSOT: Use constant from shared.constants (Principle #2)
    # Graceful failure: Fallback if import failed (Principle #16)
    try:
        chunks_ctx.set([FALLBACK_NO_TEXTBOOK_CONTENT])
    except NameError:
        # Fallback only if import failed (shouldn't happen, but graceful failure)
        from shared.constants import FALLBACK_NO_TEXTBOOK_CONTENT
        chunks_ctx.set([FALLBACK_NO_TEXTBOOK_CONTENT])
    textbook_sha256_ctx.set("")
    
    # Note: Global CHUNKS and TEXTBOOK_SHA256 are handled in the notebook wrapper
    # since they're global variables
    
    removed.append("PDF_data")
    
    return removed


__all__ = ["auto_wipe_local_after_export"]

