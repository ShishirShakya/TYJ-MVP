"""
Session Recovery Module for exam.py.

This module provides functionality to recover and resume exam sessions
from saved state, allowing students to continue exams after browser crashes
or network interruptions.

DATA INTEGRITY: Validates recovered state before resuming (Principle #22).
"""

import os
import json
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import structlog

from exam.file_utils import _paths_for_session
from exam.state.core import ensure_state
from exam.state.validation import validate_state_invariants

logger = structlog.get_logger(__name__)


def check_for_saved_session(session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Check if a saved session exists and can be recovered.
    
    Args:
        session_id: Optional session ID to check. If None, checks for any saved session.
        
    Returns:
        State dictionary if valid session found, None otherwise
    """
    try:
        if session_id:
            # Check specific session
            state = {"session_id": session_id}
            paths = _paths_for_session(state)
            
            if not os.path.exists(paths["STATE_PATH"]):
                return None
            
            with open(paths["STATE_PATH"], "r", encoding="utf-8") as f:
                state = json.load(f)
            
            # Validate state
            is_valid, error = validate_state_invariants(state)
            if not is_valid:
                logger.warning(
                    "saved_session_invalid",
                    session_id=session_id,
                    error=error,
                    message="Saved session found but validation failed"
                )
                return None
            
            # Check if exam is completed (tombstone exists)
            if os.path.exists(paths["TOMBSTONE_PATH"]):
                logger.info(
                    "saved_session_completed",
                    session_id=session_id,
                    message="Saved session found but exam is already completed"
                )
                return None
            
            return state
        else:
            # Check for any saved session (scan state directory)
            # This is a simplified version - in production, you might want
            # to track active sessions in a database
            state_dir = Path(os.getenv("EXAM_STATE_DIR", "exam_state"))
            if not state_dir.exists():
                return None
            
            # Look for state files
            for state_file in state_dir.glob("**/state.json"):
                try:
                    with open(state_file, "r", encoding="utf-8") as f:
                        state = json.load(f)
                    
                    # Validate state
                    is_valid, error = validate_state_invariants(state)
                    if is_valid:
                        # Check if exam is completed
                        session_id = state.get("session_id")
                        if session_id:
                            paths = _paths_for_session(state)
                            if not os.path.exists(paths["TOMBSTONE_PATH"]):
                                return state
                except Exception as e:
                    logger.debug(
                        "failed_to_load_state_file",
                        path=str(state_file),
                        error=str(e),
                        message="Failed to load state file (skipping)"
                    )
                    continue
            
            return None
            
    except Exception as e:
        logger.error(
            "check_saved_session_error",
            session_id=session_id,
            error=str(e),
            message="Error checking for saved session"
        )
        return None


def get_session_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a summary of the session for display in UI.
    
    Phase 2.2.2: Enhanced session recovery UI.
    
    Args:
        state: State dictionary
        
    Returns:
        Dictionary with session summary information
    """
    asked_main = state.get("asked_main", 0)
    n_questions = state.get("limit", 0)
    scores = state.get("scores", [])
    phase = state.get("phase", "idle")
    session_id = state.get("session_id", "unknown")
    
    # Calculate progress percentage
    progress_pct = (asked_main / n_questions * 100) if n_questions > 0 else 0
    
    # Get average score if available
    avg_score = sum(scores) / len(scores) if scores else None
    
    # Determine status
    if phase == "complete":
        status = "Completed"
    elif phase == "idle":
        status = "Not Started"
    elif asked_main > 0:
        status = "In Progress"
    else:
        status = "Ready"
    
    return {
        "session_id": session_id[:8] + "..." if len(session_id) > 8 else session_id,
        "status": status,
        "progress": f"{asked_main}/{n_questions}",
        "progress_pct": progress_pct,
        "average_score": f"{avg_score:.1f}" if avg_score else "N/A",
        "questions_answered": asked_main,
        "total_questions": n_questions,
        "phase": phase
    }


def recover_session(
    saved_state: Dict[str, Any],
    ensure_state_fn: Optional[callable] = None
) -> Tuple[Dict[str, Any], str, bool, Dict[str, Any]]:
    """
    Recover a session from saved state.
    
    Phase 2.2.2: Enhanced to return session summary.
    
    Args:
        saved_state: Saved state dictionary
        ensure_state_fn: Optional function to ensure state (defaults to ensure_state)
        
    Returns:
        Tuple of (recovered_state, status_message, can_resume, session_summary)
        - recovered_state: Validated and ensured state
        - status_message: Human-readable status message
        - can_resume: Whether the session can be resumed
        - session_summary: Dictionary with session summary information
    """
    if ensure_state_fn is None:
        ensure_state_fn = ensure_state
    
    try:
        # Validate state
        is_valid, error = validate_state_invariants(saved_state)
        if not is_valid:
            # Try lenient validation for recovery
            critical_fields = {"session_id", "request_id", "student_id", "phase"}
            has_critical = all(field in saved_state for field in critical_fields)
            has_valid_types = (
                isinstance(saved_state.get("history"), list) and
                isinstance(saved_state.get("scores"), list) and
                isinstance(saved_state.get("rubrics"), list)
            )
            
            if not (has_critical and has_valid_types):
                return (
                    ensure_state_fn({}),
                    f"❌ Cannot recover session: {error}",
                    False,
                    {}
                )
            
            logger.warning(
                "session_recovery_lenient",
                session_id=saved_state.get("session_id"),
                error=error,
                message="Recovering session with lenient validation"
            )
        
        # Ensure state (fills in missing fields)
        recovered_state = ensure_state_fn(saved_state)
        
        # Check if exam is already completed
        phase = recovered_state.get("phase", "idle")
        if phase == "complete":
            session_summary = get_session_summary(recovered_state)
            return (
                recovered_state,
                f"ℹ️ **Exam Already Completed**\n\nThis exam session has already been completed.\n**Final Score:** {session_summary['average_score']}",
                False,
                session_summary
            )
        
        # Check if exam hasn't started yet
        if phase == "idle":
            session_summary = get_session_summary(recovered_state)
            return (
                recovered_state,
                "ℹ️ **No Active Session**\n\nNo active exam session found. Starting fresh.",
                False,
                session_summary
            )
        
        # Session can be resumed
        session_summary = get_session_summary(recovered_state)
        session_id = recovered_state.get("session_id", "unknown")
        asked_main = recovered_state.get("asked_main", 0)
        n_questions = recovered_state.get("limit", 0)
        
        status_msg = (
            f"✅ **Found Saved Session**\n\n"
            f"**Session ID:** {session_summary['session_id']}\n"
            f"**Status:** {session_summary['status']}\n"
            f"**Progress:** {session_summary['progress']} questions answered ({session_summary['progress_pct']:.0f}%)\n"
            f"**Average Score:** {session_summary['average_score']}\n\n"
            f"🔄 Would you like to resume from where you left off?"
        )
        
        logger.info(
            "session_recovered",
            session_id=session_id,
            asked_main=asked_main,
            n_questions=n_questions,
            phase=phase,
            message="Session successfully recovered"
        )
        
        return recovered_state, status_msg, True, session_summary
        
    except Exception as e:
        logger.error(
            "session_recovery_error",
            session_id=saved_state.get("session_id", "unknown"),
            error=str(e),
            message="Error recovering session"
        )
        return (
            ensure_state_fn({}),
            f"❌ Error recovering session: {str(e)}",
            False,
            {}
        )


def prompt_resume_session(
    saved_state: Dict[str, Any],
    ensure_state_fn: Optional[callable] = None
) -> Tuple[Dict[str, Any], str, bool, Dict[str, Any]]:
    """
    Prompt user to resume session or start fresh.
    
    Phase 2.2.2: Enhanced to return session summary and resume flag.
    
    This function provides a user-friendly way to handle session recovery,
    asking the user if they want to resume or start fresh.
    
    Args:
        saved_state: Saved state dictionary
        ensure_state_fn: Optional function to ensure state
        
    Returns:
        Tuple of (state, status_message, can_resume, session_summary)
        - state: Either recovered state or fresh state
        - status_message: Message to display to user
        - can_resume: Whether the session can be resumed
        - session_summary: Dictionary with session summary information
    """
    recovered_state, status_msg, can_resume, session_summary = recover_session(saved_state, ensure_state_fn)
    
    if can_resume:
        # Return recovered state with resume option
        return recovered_state, status_msg, True, session_summary
    else:
        # Cannot resume - start fresh
        if ensure_state_fn is None:
            ensure_state_fn = ensure_state
        fresh_state = ensure_state_fn({})
        return fresh_state, status_msg, False, session_summary

