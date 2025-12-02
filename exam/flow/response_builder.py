"""
Response builder utilities - Single Source of Truth for flow responses.

Standardizes response format across all flow functions to improve consistency.
Note: Flow functions return tuples for Gradio compatibility, not dictionaries.
"""

from typing import Dict, Any, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    import gradio as gr

# SSOT for empty timeout data
EMPTY_TIMEOUT = {"value": "", "visible": False}

__all__ = [
    "build_error_tuple",
    "EMPTY_TIMEOUT",
]


def build_error_tuple(
    s: Dict[str, Any],
    gr_module: Any,
    error_message: str,
    mic_interactive: bool = False,
    finish_interactive: bool = False,
    finish_visible: bool = False,
    timeout_update: Optional[Any] = None,
    tuple_length: int = 8
) -> Tuple:
    """
    Build standardized error tuple for flow functions.
    
    This is the Single Source of Truth for error response format.
    
    Args:
        s: State dictionary
        gr_module: Gradio module
        error_message: Sanitized error message
        mic_interactive: Mic button interactive flag
        finish_interactive: Finish button interactive flag
        finish_visible: Finish button visible flag
        timeout_update: Optional timeout update (gr_module.update() call result)
        tuple_length: Expected tuple length (8 or 9)
        
    Returns:
        Standardized error tuple matching expected format
    """
    # Base tuple: (state, audio, status, mic, history, cam, proctor, ...)
    base = (
        s,
        None,  # audio
        gr_module.update(value=error_message),  # status
        gr_module.update(value=None, interactive=mic_interactive),  # mic
        s.get("history", []),  # history
        gr_module.update(),  # cam
        gr_module.update(),  # proctor status
    )
    
    # Add finish button update if tuple_length >= 8
    if tuple_length >= 8:
        base = base + (gr_module.update(visible=finish_visible, interactive=finish_interactive),)
    
    # Add timeout update if tuple_length >= 9
    if tuple_length >= 9:
        if timeout_update is not None:
            base = base + (timeout_update,)
        else:
            # Default: hide timeout
            base = base + (gr_module.update(value="", visible=False),)
    
    return base

