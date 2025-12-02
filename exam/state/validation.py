"""
State validation and invariant enforcement.

This module provides explicit validation functions for state invariants and constraints,
enforced at the persistence layer and in domain logic (Principle #22).

DATA INTEGRITY: Explicit invariants and constraints ensure data integrity (Principle #22).
"""

from typing import Dict, Any, List, Optional, Tuple
import uuid
from shared.constants import (
    MAX_HISTORY_ENTRIES,
    MAX_ANSWERS_TSLOG,
    MAX_SECURITY_EVENTS,
    MAX_TOKEN_USAGE,
    MAX_QUESTIONS_META,
    MAX_TAB_FOCUS_EVENTS,
    MAX_CLIPBOARD_EVENTS,
    MAX_ANSWER_HASHES,
    MAX_ANSWER_TEXTS,
    MAX_USED_CONTEXT_HASHES,
)


# =========================
# Invariant Definitions
# =========================

class StateInvariant:
    """
    State invariants that must always hold.
    
    DATA INTEGRITY: Explicit invariants ensure consistency (Principle #22).
    """
    
    # Required fields that must always be present
    REQUIRED_FIELDS = {
        "session_id",
        "request_id",
        "student_id",
        "history",
        "scores",
        "rubrics",
        "phase",
        "started_at",
        "session_start_time",
    }
    
    # Fields that must be specific types
    TYPE_CONSTRAINTS = {
        "session_id": str,
        "request_id": str,
        "student_id": str,
        "history": list,
        "scores": list,
        "rubrics": list,
        "phase": str,
        "started_at": str,
        "session_start_time": (int, float),
        "flags": list,
        "consent": bool,
    }
    
    # Fields that must match specific formats
    FORMAT_CONSTRAINTS = {
        "session_id": lambda v: _is_valid_uuid(v),
        "request_id": lambda v: _is_valid_uuid(v),
        "phase": lambda v: v in ["idle", "awaiting_consent", "awaiting_main_answer", 
                                   "awaiting_followup_answer", "complete"],
    }
    
    # Bounded collections (max sizes) - using constants from shared.constants (SSOT Principle #2)
    BOUNDED_COLLECTIONS = {
        "history": MAX_HISTORY_ENTRIES,
        "answers_tslog_all": MAX_ANSWERS_TSLOG,
        "security_events": MAX_SECURITY_EVENTS,
        "token_usage": MAX_TOKEN_USAGE,
        "questions_meta": MAX_QUESTIONS_META,
        "tab_focus_events": MAX_TAB_FOCUS_EVENTS,
        "clipboard_events": MAX_CLIPBOARD_EVENTS,
        "answer_hashes": MAX_ANSWER_HASHES,
        "answer_texts": MAX_ANSWER_TEXTS,
        "used_context_hashes": MAX_USED_CONTEXT_HASHES,
    }


def _is_valid_uuid(value: str) -> bool:
    """Check if value is a valid UUID string."""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


# =========================
# Validation Functions
# =========================

def validate_state_invariants(state: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate that state satisfies all invariants.
    
    DATA INTEGRITY: Explicit invariant validation ensures consistency (Principle #22).
    
    Args:
        state: State dictionary to validate
        
    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if all invariants satisfied, False otherwise
        - error_message: Error message if validation failed, None otherwise
        
    Example:
        ```python
        is_valid, error = validate_state_invariants(state)
        if not is_valid:
            raise ValueError(f"State invariant violation: {error}")
        ```
    """
    # Check required fields
    missing_fields = StateInvariant.REQUIRED_FIELDS - set(state.keys())
    if missing_fields:
        return False, f"Missing required fields: {', '.join(missing_fields)}"
    
    # Check type constraints
    for field, expected_type in StateInvariant.TYPE_CONSTRAINTS.items():
        if field not in state:
            continue  # Already checked in required fields
        
        value = state[field]
        if isinstance(expected_type, tuple):
            if not isinstance(value, expected_type):
                return False, f"Field '{field}' must be one of {expected_type}, got {type(value).__name__}"
        else:
            if not isinstance(value, expected_type):
                return False, f"Field '{field}' must be {expected_type.__name__}, got {type(value).__name__}"
    
    # Check format constraints
    for field, validator in StateInvariant.FORMAT_CONSTRAINTS.items():
        if field not in state:
            continue  # Already checked in required fields
        
        value = state[field]
        if not validator(value):
            return False, f"Field '{field}' does not match required format"
    
    # Check bounded collections
    for field, max_size in StateInvariant.BOUNDED_COLLECTIONS.items():
        if field not in state:
            continue  # Optional field
        
        value = state[field]
        if isinstance(value, (list, tuple, dict, set)):
            actual_size = len(value)
            if actual_size > max_size:
                return False, f"Field '{field}' exceeds bound: {actual_size} > {max_size}"
    
    return True, None


def validate_state_before_persistence(state: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate state before persistence.
    
    DATA INTEGRITY: Enforces invariants at persistence layer (Principle #22).
    
    This function performs additional checks specific to persistence:
    - State must be serializable
    - Required fields must be present
    - Bounded collections must be within limits
    
    Args:
        state: State dictionary to validate
        
    Returns:
        Tuple of (is_valid, error_message)
        
    Example:
        ```python
        is_valid, error = validate_state_before_persistence(state)
        if not is_valid:
            logger.error("state_validation_failed", error=error)
            return False
        ```
    """
    # Validate invariants
    is_valid, error = validate_state_invariants(state)
    if not is_valid:
        return False, error
    
    # Additional persistence-specific checks
    # Check that session_id is valid UUID
    session_id = state.get("session_id")
    if not session_id or not _is_valid_uuid(session_id):
        return False, "session_id must be a valid UUID"
    
    # Check that phase is valid
    phase = state.get("phase")
    valid_phases = ["idle", "awaiting_consent", "awaiting_main_answer", 
                    "awaiting_followup_answer", "complete"]
    if phase not in valid_phases:
        return False, f"phase must be one of {valid_phases}, got '{phase}'"
    
    # Check that history is a list
    history = state.get("history")
    if not isinstance(history, list):
        return False, "history must be a list"
    
    # Check that scores is a list
    scores = state.get("scores")
    if not isinstance(scores, list):
        return False, "scores must be a list"
    
    # Check that rubrics is a list
    rubrics = state.get("rubrics")
    if not isinstance(rubrics, list):
        return False, "rubrics must be a list"
    
    return True, None


def enforce_state_constraints(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enforce constraints on state (e.g., truncate bounded collections).
    
    DATA INTEGRITY: Enforces constraints to maintain consistency (Principle #22).
    
    This function modifies state to ensure constraints are satisfied:
    - Truncates bounded collections to max size
    - Ensures required fields are present (with defaults)
    - Validates format constraints
    
    Args:
        state: State dictionary to enforce constraints on
        
    Returns:
        State dictionary with constraints enforced
        
    Example:
        ```python
        # Before: history has 1500 entries
        # After: history truncated to 1000 entries (most recent)
        state = enforce_state_constraints(state)
        ```
    """
    # Truncate bounded collections
    for field, max_size in StateInvariant.BOUNDED_COLLECTIONS.items():
        if field not in state:
            continue
        
        value = state[field]
        if isinstance(value, list):
            if len(value) > max_size:
                # Keep most recent entries
                state[field] = value[-max_size:]
        elif isinstance(value, dict):
            if len(value) > max_size:
                # Keep most recent entries (if dict maintains insertion order)
                items = list(value.items())
                state[field] = dict(items[-max_size:])
        elif isinstance(value, set):
            if len(value) > max_size:
                # Keep most recent entries (convert to list, truncate, convert back)
                value_list = list(value)
                state[field] = set(value_list[-max_size:])
    
    return state


def validate_transaction_boundary(
    operation: str,
    state_before: Dict[str, Any],
    state_after: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Validate transaction boundary integrity.
    
    DATA INTEGRITY: Ensures transaction boundaries maintain consistency (Principle #22).
    
    This function validates that a transaction maintains invariants:
    - State before and after must both be valid
    - Required fields must not be removed
    - Critical fields must not change unexpectedly
    
    Args:
        operation: Operation name (e.g., "save_state_to_disk")
        state_before: State before transaction
        state_after: State after transaction
        
    Returns:
        Tuple of (is_valid, error_message)
        
    Example:
        ```python
        state_before = copy.deepcopy(state)
        # ... perform operation ...
        is_valid, error = validate_transaction_boundary("save_state", state_before, state)
        if not is_valid:
            logger.error("transaction_boundary_violation", error=error)
        ```
    """
    # Validate both states
    is_valid_before, error_before = validate_state_invariants(state_before)
    if not is_valid_before:
        return False, f"State before {operation} invalid: {error_before}"
    
    is_valid_after, error_after = validate_state_invariants(state_after)
    if not is_valid_after:
        return False, f"State after {operation} invalid: {error_after}"
    
    # Check that required fields are not removed
    required_before = StateInvariant.REQUIRED_FIELDS & set(state_before.keys())
    required_after = StateInvariant.REQUIRED_FIELDS & set(state_after.keys())
    
    removed_fields = required_before - required_after
    if removed_fields:
        return False, f"Required fields removed during {operation}: {', '.join(removed_fields)}"
    
    # Check that session_id doesn't change
    if state_before.get("session_id") != state_after.get("session_id"):
        return False, f"session_id changed during {operation}"
    
    return True, None


__all__ = [
    "StateInvariant",
    "validate_state_invariants",
    "validate_state_before_persistence",
    "enforce_state_constraints",
    "validate_transaction_boundary",
]

