"""
Core state management functions for exam.ipynb.

This module contains functions for initializing and managing exam state:
- State initialization and validation
- Block reset functionality
- Followup range management
"""

import os
import uuid
import random
import time
from datetime import datetime
from typing import Dict, Any, Tuple, Optional

from exam.context_vars import get_course_id, get_exam_id
from shared.platform import PlatformProvider, get_default_platform_provider
from shared.time_provider import TimeProvider, get_default_time_provider


# Constants (fallback defaults)
FOLLOWUPS_MIN = 0
FOLLOWUPS_MAX = 1
N_QUESTIONS = 1
PASSPHRASE = ""


def ensure_state(
    s: Dict[str, Any],
    platform_provider: Optional[PlatformProvider] = None,
    time_provider: Optional[TimeProvider] = None,
    rng_seed: Optional[int] = None
) -> Dict[str, Any]:
    """
    Initialize and validate state dictionary with all required defaults.
    
    This function ensures that the state dictionary has all required fields
    initialized with appropriate default values. It's called at the start of
    every state-modifying operation to ensure state consistency.
    
    Note: This function uses default values for limit, followups_min, followups_max,
    and passphrase. The notebook can override these after calling ensure_state if needed.
    
    DETERMINISTIC: Accepts optional time_provider and rng_seed for reproducible behavior (Principle #5).
    Uses platform provider for portability (Principle #6).
    
    DATA INTEGRITY: Enforces state invariants and constraints (Principle #22).
    Ensures all required fields are present and have correct types.
    
    Args:
        s: State dictionary (may be None or empty)
        platform_provider: Optional platform provider (uses default if not provided)
        time_provider: Optional time provider (uses default if not provided)
        rng_seed: Optional RNG seed (uses os.urandom if not provided for security)
        
    Returns:
        Fully initialized state dictionary with all invariants satisfied
    """
    if platform_provider is None:
        platform_provider = get_default_platform_provider()
    
    if time_provider is None:
        time_provider = get_default_time_provider()
    
    if not s:
        s = {}
    
    # Generate session_id with collision detection
    # Check if session_id already exists and if a state file exists for it
    # DETERMINISTIC: Uses deterministic UUID generation if rng_seed provided (Principle #5)
    if "session_id" not in s or not s.get("session_id"):
        if rng_seed is not None:
            # Testing mode: Generate deterministic session ID
            from shared.deterministic_uuid import generate_session_id
            session_id = generate_session_id(f"test_session_{rng_seed}", test_mode=True)
        else:
            # Production mode: Generate random UUID for security
            session_id = str(uuid.uuid4())
        
        # Check for collision (extremely rare but possible)
        from exam.file_utils import _paths_for_session
        import structlog
        
        collision_check_state = {"session_id": session_id}
        collision_paths = _paths_for_session(collision_check_state)
        
        # If state file exists, regenerate UUID (collision detected)
        # Note: In test mode with deterministic IDs, collisions are expected and handled
        max_attempts = 10
        attempts = 0
        logger = structlog.get_logger()
        
        while os.path.exists(collision_paths["STATE_PATH"]) and attempts < max_attempts:
            logger.warning(
                "session_id_collision_detected",
                session_id=session_id,
                attempt=attempts + 1,
                message="Session ID collision detected, regenerating"
            )
            if rng_seed is not None:
                # Testing mode: Append attempt number to seed for uniqueness
                from shared.deterministic_uuid import generate_session_id
                session_id = generate_session_id(f"test_session_{rng_seed}_{attempts}", test_mode=True)
            else:
                # Production mode: Generate new random UUID
                session_id = str(uuid.uuid4())
            collision_check_state = {"session_id": session_id}
            collision_paths = _paths_for_session(collision_check_state)
            attempts += 1
        
        if attempts >= max_attempts:
            logger.error(
                "session_id_collision_max_attempts",
                message="Failed to generate unique session ID after max attempts"
            )
            # Still use the last generated ID - collision is extremely rare
        
        s.setdefault("session_id", session_id)
    # IDEMPOTENCY: Generate request ID for safe retries (Principle #21)
    # Request ID enables deduplication and prevents duplicate operations
    # DETERMINISTIC: Uses deterministic UUID generation if rng_seed provided (Principle #5)
    if "request_id" not in s or not s.get("request_id"):
        if rng_seed is not None:
            # Testing mode: Generate deterministic request ID
            from shared.deterministic_uuid import generate_request_id
            request_id = generate_request_id(f"{s.get('session_id', 'unknown')}_request", test_mode=True)
        else:
            # Production mode: Generate random UUID for security
            request_id = str(uuid.uuid4())
        s.setdefault("request_id", request_id)
    s.setdefault("student_id", "")
    
    # Log IP address on first state initialization (if available)
    # Uses platform provider for portability
    if "ip_address" not in s or not s.get("ip_address"):
        try:
            # Try to get local IP address using platform provider
            hostname = platform_provider.get_hostname()
            import socket
            local_ip = socket.gethostbyname(hostname)
            s.setdefault("ip_address", local_ip)
        except Exception:
            s.setdefault("ip_address", "UNKNOWN")
    
    # DETERMINISTIC: Use provided seed or generate secure random seed (Principle #5)
    # For testing, provide rng_seed; for production, use os.urandom for security
    if "_rng_seed" not in s:
        if rng_seed is not None:
            s["_rng_seed"] = rng_seed
        else:
            # SECURITY: Use os.urandom for production (cryptographically secure)
            # For deterministic testing, pass rng_seed parameter
            s["_rng_seed"] = int.from_bytes(os.urandom(8), "big")
    s.setdefault("_rng", random.Random(s["_rng_seed"]))
    # Ensure history is always a list (fix for cases where it might have been set to a string)
    if "history" not in s or not isinstance(s.get("history"), list):
        s["history"] = []
    s.setdefault("asked_main", 0)
    s.setdefault("scores", [])
    s.setdefault("rubrics", [])
    
    # Get values from state if already set, otherwise use defaults
    # Note: The notebook wrapper will update these using getter functions if needed
    if "limit" not in s:
        s["limit"] = N_QUESTIONS
    if "followups_min" not in s:
        s["followups_min"] = FOLLOWUPS_MIN
    if "followups_max" not in s:
        s["followups_max"] = FOLLOWUPS_MAX
    if "passphrase" not in s:
        s["passphrase"] = PASSPHRASE
    
    s.setdefault("course_id", s.get("course_id", get_course_id()))
    s.setdefault("exam_id", s.get("exam_id", get_exam_id()))
    s.setdefault("section_id", s.get("section_id", "UNKNOWN"))
    s.setdefault("phase", "idle")
    # DETERMINISTIC: Use time_provider instead of direct time calls (Principle #5)
    s.setdefault("started_at", time_provider.now().isoformat(timespec="seconds"))
    
    # DATA INTEGRITY: Reset session_start_time when phase is idle/complete
    # Prevents stale timestamps from previous sessions/deployments (Principle #22)
    current_phase = s.get("phase", "idle")
    if current_phase in ("idle", "complete"):
        s["session_start_time"] = 0  # No active exam, no timeout tracking
    else:
        s.setdefault("session_start_time", time_provider.time())  # Track session start timestamp for timeout detection
    s.setdefault("flags", [])
    s.setdefault("consent", False)
    
    # Security event tracking
    s.setdefault("security_events", [])  # List of security events with timestamps
    s.setdefault("tab_focus_events", [])  # Track tab focus/blur events
    s.setdefault("clipboard_events", [])  # Track copy/paste events
    
    # Auto-save tracking (for audit trail only, not for resume)
    s.setdefault("last_auto_save_time", 0)  # Track last auto-save timestamp
    
    # Network resilience tracking
    s.setdefault("network_status", "online")  # Track network status: "online", "offline", "checking"
    s.setdefault("last_network_check", 0)  # Track last network check timestamp
    s.setdefault("queued_answers", [])  # Queue answers when offline
    s.setdefault("network_check_interval", 5)  # Check network every 5 seconds
    s.setdefault("ready_for_question", False)  # armed on consent; first mic press plays question
    
    s.setdefault("current", {
        "main_question": None,
        "answers": [],
        "followups_done": 0,
        "target_followups": 0,
        "q_time": None,
        "short_attempts": 0,
        "ctx": None
    })
    s.setdefault("answers_tslog_all", [])
    s.setdefault("otet", None)
    
    # Proctoring state
    s.setdefault("proctor_state", None)
    s.setdefault("proctor_summary", {})
    s.setdefault("proctor_blocks", [])
    s.setdefault("webcam_enabled", False)
    s.setdefault("webcam_consent_acknowledged", False)
    s.setdefault("exam_started", False)
    
    # Answer reuse detection: track hashes and texts of all previous answers
    s.setdefault("answer_hashes", [])
    s.setdefault("answer_texts", [])  # Store texts for semantic similarity comparison
    
    # Context chunk tracking: prevent duplicate context reuse
    s.setdefault("used_context_hashes", set())  # Track hashes of used context chunks
    
    # Question provenance tracking for auditability (FERPA-compliant: only cryptographic hashes, no PII)
    s.setdefault("questions_meta", [])  # holds provenance for each main question
    
    # COST OPTIMIZATION: Token usage tracking for cost monitoring
    s.setdefault("token_usage", [])  # tracks token usage per operation
    
    return s


def reset_current_block(s: Dict[str, Any]) -> None:
    """
    Reset the current question block to initial state.
    
    **Contract**:
    - **Inputs**: State dictionary (must be dict)
    - **Outputs**: None (modifies state in place)
    - **Invariants**: State must be a dict (validated)
    - **Failure Modes**: Raises TypeError if state is not a dict
    
    Resets the current question block fields to their initial values:
    - Clears main question, answers, and context
    - Resets followup counters
    - Clears timing information
    
    This function is called when starting a new question block to ensure
    clean state for the next question.
    
    Args:
        s: State dictionary (must be dict, validated internally)
        
    Raises:
        TypeError: If state is not a dict
        
    Example:
        ```python
        reset_current_block(state)
        # state["current"] is now reset to initial values
        ```
    """
    # Defensive check: ensure s is a dict
    if not isinstance(s, dict):
        raise TypeError(f"reset_current_block received non-dict type: {type(s)}")
    
    s["current"] = {
        "main_question": None,
        "answers": [],
        "followups_done": 0,
        "target_followups": 0,
        "q_time": None,
        "short_attempts": 0,
        "ctx": None
    }


def get_followup_range(s: Dict[str, Any]) -> Tuple[int, int]:
    """
    Get followup range from state, with safeguards.
    
    **Contract**:
    - **Inputs**: State dictionary
    - **Outputs**: Tuple of (followups_min, followups_max)
    - **Invariants**: Always returns min <= max (validated)
    - **Failure Modes**: Uses defaults if values missing or invalid
    
    Returns (followups_min, followups_max) tuple with validation.
    Ensures min <= max to prevent ValueError in range operations.
    
    **Data Integrity** (Principle #22):
    - Validates that min <= max
    - Uses fallback defaults if values are missing
    - Handles corrupted state gracefully
    
    Args:
        s: State dictionary (may have followups_min/followups_max or use defaults)
        
    Returns:
        Tuple of (followups_min, followups_max) where min <= max
        
    Example:
        ```python
        min_followups, max_followups = get_followup_range(state)
        # Always ensures min_followups <= max_followups
        ```
    """
    followups_min = s.get("followups_min", FOLLOWUPS_MIN)
    followups_max = s.get("followups_max", FOLLOWUPS_MAX)
    
    # Safeguard: Ensure min <= max (handle edge cases from corrupted state)
    if followups_min > followups_max:
        followups_max = followups_min  # Use min as max to prevent ValueError
    
    return followups_min, followups_max

