"""
Security event logging module for exam.ipynb.

This module contains functions for logging security events:
- Security event logging to state
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional


def log_security_event(s: Dict[str, Any], event_type: str, event_detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Log security event to state.
    
    Args:
        s: State dictionary
        event_type: Type of security event (e.g., "TAB_BLUR", "CLIPBOARD_COPY", "CLIPBOARD_PASTE")
        event_detail: Optional dictionary with additional event details
        
    Returns:
        Updated state dictionary
    """
    from exam.state import ensure_state
    
    s = ensure_state(s)
    event = {
        "ts_iso": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "type": event_type,
        "detail": event_detail or {}
    }
    s.setdefault("security_events", []).append(event)
    
    # Also add to flags if it's a significant security event
    if event_type in ("TAB_BLUR", "CLIPBOARD_COPY", "CLIPBOARD_PASTE"):
        s.setdefault("flags", []).append(event_type)
    
    return s


__all__ = ["log_security_event"]

