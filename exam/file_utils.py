"""
File utilities for exam.ipynb - session path management.

This module contains file utility functions used only by exam.ipynb.
Functions used by multiple apps are in shared/.
"""

import os
import uuid
from typing import Dict, Any, Optional
from shared.platform import PlatformProvider, get_default_platform_provider


def _session_dir(session_id: str, platform_provider: Optional[PlatformProvider] = None) -> str:
    """
    Get or create session directory for a given session ID.
    
    Uses platform provider for portability (Principle #6).
    
    Args:
        session_id: Unique session identifier
        platform_provider: Optional platform provider (uses default if not provided)
        
    Returns:
        Path to session directory
    """
    if platform_provider is None:
        platform_provider = get_default_platform_provider()
    
    temp_dir = platform_provider.get_temp_dir()
    d = platform_provider.join_path(temp_dir, "vivaai", session_id)
    os.makedirs(d, exist_ok=True)
    return d


def _paths_for_session(
    s: Dict[str, Any],
    platform_provider: Optional[PlatformProvider] = None
) -> Dict[str, str]:
    """
    Generate all file paths for a session.
    
    Uses platform provider for portability (Principle #6).
    
    Args:
        s: Session state dictionary (must contain 'session_id' or will generate one)
        platform_provider: Optional platform provider (uses default if not provided)
        
    Returns:
        Dictionary with paths:
        - STATE_PATH: Path to state JSON file
        - TOMBSTONE_PATH: Path to sealed tomb file
        - DEVICE_KEY_PATH: Path to device key PEM file
        - OTET_LEDGER_PATH: Path to OTET ledger CSV file
        - TMP_DIR: Temporary directory for session
    """
    if platform_provider is None:
        platform_provider = get_default_platform_provider()
    
    sid = s.get("session_id") or str(uuid.uuid4())
    root = _session_dir(sid, platform_provider)
    return {
        "STATE_PATH": platform_provider.join_path(root, "viva_state.json"),
        "TOMBSTONE_PATH": platform_provider.join_path(root, "sealed.tomb"),
        "DEVICE_KEY_PATH": platform_provider.join_path(root, "device_key.pem"),
        "OTET_LEDGER_PATH": platform_provider.join_path(root, "otet_ledger.csv"),
        "TMP_DIR": root,
    }

