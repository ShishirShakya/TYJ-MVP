"""
State management module for exam.ipynb.

This module contains functions for managing exam state:
- State initialization and validation
- State persistence (save, load, auto-save)
- Network status and offline queue management
"""

from .core import ensure_state, reset_current_block, get_followup_range
from .persistence import (
    atomic_write_json_secure,
    save_state_to_disk,
    auto_save_state,
    load_state_from_disk,
    resume_from_disk,
    AUTO_SAVE_INTERVAL_SEC,
)
from .network import (
    check_network_status,
    update_network_status,
    queue_answer_locally,
    process_queued_answers,
    NETWORK_CHECK_INTERVAL_SEC,
    NETWORK_CHECK_TIMEOUT_SEC,
)
from .validation import (
    validate_state_invariants,
    validate_state_before_persistence,
    enforce_state_constraints,
    validate_transaction_boundary,
    StateInvariant,
)

__all__ = [
    # Core state management
    "ensure_state",
    "reset_current_block",
    "get_followup_range",
    # Persistence
    "atomic_write_json_secure",
    "save_state_to_disk",
    "auto_save_state",
    "load_state_from_disk",
    "resume_from_disk",
    "AUTO_SAVE_INTERVAL_SEC",
    # Network management
    "check_network_status",
    "update_network_status",
    "queue_answer_locally",
    "process_queued_answers",
    "NETWORK_CHECK_INTERVAL_SEC",
    "NETWORK_CHECK_TIMEOUT_SEC",
    # Validation (Principle #22)
    "validate_state_invariants",
    "validate_state_before_persistence",
    "enforce_state_constraints",
    "validate_transaction_boundary",
    "StateInvariant",
]

