"""
Parsing utilities for dash.ipynb - transcript parsing functions.

This module contains parsing functions used only by dash.ipynb.
Functions used by multiple apps are in shared/.

DETERMINISTIC BEHAVIOR: All functions are pure and deterministic (Principle #5).
Same inputs always produce same outputs. No randomness or hidden state.
"""

import re
from typing import Tuple, Dict, Optional, Any
from datetime import datetime


def _grab(label: str, text: str) -> str:
    """
    Extract a labeled field from text.
    
    DETERMINISTIC: Same inputs always produce same outputs (Principle #5).
    
    Args:
        label: The label to search for (e.g., "SessionID")
        text: The text to search in
        
    Returns:
        The value after the label, or empty string if not found
        
    Contract:
        - Input: label (str), text (str)
        - Output: Extracted value (str) or empty string if not found
        - Deterministic: Same inputs → same output
    """
    m = re.search(rf"^{re.escape(label)}:\s*(.+)$", text, flags=re.MULTILINE)
    return m.group(1).strip() if m else ""


def _parse_plaintext_fields(pt_text: str) -> Tuple[str, str, str, int, Any, Any]:
    """
    Parse basic fields from plaintext transcript.
    
    DETERMINISTIC: Same input text always produces same parsed output (Principle #5).
    
    Args:
        pt_text: Plaintext transcript text
        
    Returns:
        Tuple of (session_id, started_at, completed_at, num_blocks, avg_overall, duration_sec)
        
    Contract:
        - Input: pt_text (str) - plaintext transcript
        - Output: Tuple of parsed fields
        - Deterministic: Same input → same output
        - No side effects: Pure function
    """
    session_id = _grab("SessionID", pt_text)
    started_at = _grab("StartedAt", pt_text)
    completed_at = _grab("CompletedAt", pt_text)
    overs = [int(x) for x in re.findall(r"Overall:\s*(\d{1,3})", pt_text)]
    avg_overall = round(sum(overs) / len(overs)) if overs else ""
    
    def _iso_to_dt(s):
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(s)
        except Exception:
            return None
    
    t1, t2 = _iso_to_dt(started_at), _iso_to_dt(completed_at)
    duration_sec = (t2 - t1).total_seconds() if (t1 and t2) else ""
    
    return session_id, started_at, completed_at, len(overs), avg_overall, duration_sec


def _parse_rubric_scores(pt_text: str) -> Dict[str, Optional[float]]:
    """
    Extract individual rubric dimension scores from plaintext.
    
    BIAS MITIGATION - RUBRIC TRANSPARENCY: Extract individual rubric dimension scores.
    DETERMINISTIC: Same input text always produces same parsed scores (Principle #5).
    
    Args:
        pt_text: Plaintext transcript text
        
    Returns:
        Dict with Conceptual, Analytical, Application, Reflection, and Overall scores (averages)
        Keys: "Conceptual", "Analytical", "Application", "Reflection", "Overall"
        Values: Average score (float) or None if no scores found
        
    Contract:
        - Input: pt_text (str) - plaintext transcript
        - Output: Dict[str, Optional[float]] - rubric dimension averages
        - Deterministic: Same input → same output
        - No side effects: Pure function
    """
    rubric_scores = {
        "Conceptual": [],
        "Analytical": [],
        "Application": [],
        "Reflection": [],
        "Overall": []
    }
    
    # Extract scores from plaintext (format: "Conceptual: 85", etc.)
    for dimension in ["Conceptual", "Analytical", "Application", "Reflection", "Overall"]:
        scores = [int(x) for x in re.findall(rf"{dimension}:\s*(\d{{1,3}})", pt_text)]
        rubric_scores[dimension] = scores
    
    # Calculate averages for each dimension
    averages = {}
    for dimension, scores in rubric_scores.items():
        if scores:
            averages[dimension] = round(sum(scores) / len(scores), 1)
        else:
            averages[dimension] = None
    
    return averages

