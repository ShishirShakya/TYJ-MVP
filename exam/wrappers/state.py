"""
State management wrapper functions for exam.ipynb.

These wrapper functions bridge between the notebook's global variables/context variables
and the modular state management functions. They handle backward compatibility and provide
a clean interface.

Note: These functions accept constants as parameters to avoid direct access to notebook globals.
The notebook should create thin wrapper functions that pass the constants from its scope.
"""

from typing import Dict, Optional

from exam.state import (
    ensure_state as _ensure_state_base,
    save_state_to_disk as _save_state_to_disk_base,
    auto_save_state as _auto_save_state_base,
    queue_answer_locally as _queue_answer_locally_base,
    load_state_from_disk as _load_state_from_disk_base,
    resume_from_disk as _resume_from_disk_base,
)
from exam.context_vars import (
    get_n_questions,
    get_followups_min,
    get_followups_max,
    get_passphrase,
)


def ensure_state(s: Dict) -> Dict:
    """
    Wrapper for ensure_state that uses notebook getter functions.
    
    Args:
        s: State dictionary
    
    Returns:
        Updated state dictionary
    """
    s = _ensure_state_base(s)
    # Update values using getter functions from notebook context
    # Always use getter functions to get current context values
    s["limit"] = s.get("limit", get_n_questions())
    s["followups_min"] = s.get("followups_min", get_followups_min())
    s["followups_max"] = s.get("followups_max", get_followups_max())
    s["passphrase"] = s.get("passphrase", get_passphrase())
    return s


def save_state_to_disk(s: Dict, *, PERSIST_OK: bool) -> bool:
    """
    Wrapper for save_state_to_disk that passes PERSIST_OK.
    
    Args:
        s: State dictionary
        PERSIST_OK: Persistence flag from notebook
    
    Returns:
        True if saved successfully, False otherwise
    """
    return _save_state_to_disk_base(s, persist_ok=PERSIST_OK)


def auto_save_state(s: Dict, *, PERSIST_OK: bool) -> bool:
    """
    Wrapper for auto_save_state that passes PERSIST_OK.
    
    Args:
        s: State dictionary
        PERSIST_OK: Persistence flag from notebook
    
    Returns:
        True if saved successfully, False otherwise
    """
    return _auto_save_state_base(s, persist_ok=PERSIST_OK)


def queue_answer_locally(
    s: Dict,
    answer_text: str,
    answer_audio_path: Optional[str] = None,
    *,
    PERSIST_OK: bool
) -> None:
    """
    Wrapper for queue_answer_locally that passes PERSIST_OK.
    
    Args:
        s: State dictionary
        answer_text: Answer text to queue
        answer_audio_path: Optional audio file path
        PERSIST_OK: Persistence flag from notebook
    """
    return _queue_answer_locally_base(s, answer_text, answer_audio_path, persist_ok=PERSIST_OK)


def load_state_from_disk():
    """
    Wrapper for load_state_from_disk.
    
    Returns:
        Loaded state dictionary or None
    """
    return _load_state_from_disk_base()


def resume_from_disk(*, ensure_state_fn: Optional[callable] = None):
    """
    Wrapper for resume_from_disk that passes ensure_state function.
    
    Args:
        ensure_state_fn: ensure_state function from notebook (required)
    
    Returns:
        Resumed state dictionary or None
    """
    if ensure_state_fn is None:
        # Default to ensure_state from this module
        ensure_state_fn = ensure_state
    return _resume_from_disk_base(ensure_state_fn=ensure_state_fn)

