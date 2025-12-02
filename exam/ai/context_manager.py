"""
Context management module for exam.ipynb.

This module contains functions for managing conversation history and context:
- History message building from state
- Operation-specific history selection
- Context optimization for cost reduction
"""

from typing import Dict, Any, Optional

# Import centralized prompts (supports encrypted prompts in production)
from shared.config.prompts import SYSTEM_PROMPT

# Constants
# COST OPTIMIZATION: Reduced history lengths to save tokens
MAX_HISTORY_LENGTH = 20  # Reduced from 50 - saves ~60% on history tokens
MAX_HISTORY_LENGTH_QUESTION = 4  # Only need last 2 exchanges for question generation
MAX_HISTORY_LENGTH_FOLLOWUP = 0  # Follow-ups need no history (only current Q&A)
MAX_HISTORY_LENGTH_FEEDBACK = 15  # More context needed for grading


def msgs_from_state(s: Dict[str, Any], operation_type: str = "feedback") -> list:
    """
    Build messages list from state with operation-specific history limits.
    
    COST OPTIMIZATION: Different operations get different history lengths.
    
    Args:
        s: Session state dictionary
        operation_type: Type of operation ("question", "followup", "feedback")
        
    Returns:
        List of message dictionaries with system prompt and history
    """
    # Defensive check: ensure s is a dict
    if not isinstance(s, dict):
        # If s is not a dict, return minimal valid messages list
        return [{"role": "system", "content": SYSTEM_PROMPT}]
    
    history = s.get("history", [])
    
    # Defensive check: ensure history is a list
    if not isinstance(history, list):
        history = []
        # Also fix it in the state to prevent future issues
        # Double-check s is still a dict before modifying
        if isinstance(s, dict):
            s["history"] = []
        else:
            # If s became non-dict, just use empty history
            history = []
    
    # COST OPTIMIZATION: Operation-specific history limits
    if operation_type == "question":
        max_items = MAX_HISTORY_LENGTH_QUESTION
    elif operation_type == "followup":
        max_items = MAX_HISTORY_LENGTH_FOLLOWUP
    elif operation_type == "feedback":
        max_items = MAX_HISTORY_LENGTH_FEEDBACK
    else:
        max_items = MAX_HISTORY_LENGTH
    
    # Trim history to operation-specific limit
    if len(history) > max_items:
        history = history[-max_items:]
    
    return [{"role": "system", "content": SYSTEM_PROMPT}] + history


def _get_relevant_history(s: Dict[str, Any], operation_type: str = "feedback", max_items: Optional[int] = None) -> list:
    """
    COST OPTIMIZATION: Select only relevant history messages for specific operation.
    
    Returns optimized history list.
    
    Args:
        s: Session state dictionary
        operation_type: Type of operation ("question", "followup", "feedback")
        max_items: Maximum number of history items (if None, uses operation-specific default)
        
    Returns:
        List of relevant history messages
    """
    if max_items is None:
        if operation_type == "question":
            max_items = MAX_HISTORY_LENGTH_QUESTION
        elif operation_type == "followup":
            max_items = MAX_HISTORY_LENGTH_FOLLOWUP
        elif operation_type == "feedback":
            max_items = MAX_HISTORY_LENGTH_FEEDBACK
        else:
            max_items = MAX_HISTORY_LENGTH
    
    full_history = s.get("history", [])
    
    if operation_type == "followup":
        # For follow-ups, return empty (we'll use minimal context)
        return []
    elif operation_type == "question":
        # For questions, only need last 2-3 exchanges
        return full_history[-max_items:] if len(full_history) > max_items else full_history
    elif operation_type == "feedback":
        # For feedback, need more context but still limited
        return full_history[-max_items:] if len(full_history) > max_items else full_history
    
    return full_history[:max_items] if len(full_history) > max_items else full_history

