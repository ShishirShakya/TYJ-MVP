"""
Error handling utilities - Single Source of Truth for flow error handling.

This module provides centralized error handling for flow functions to ensure
consistent error messages and reduce duplication.
"""

import time
from typing import Dict, Any, Optional, Tuple, TYPE_CHECKING
from shared.logging_config import get_logger
from shared.time_provider import get_default_time_provider
from shared.constants import DEFAULT_ERROR_OCCURRED

if TYPE_CHECKING:
    import gradio as gr

logger = get_logger()


def handle_flow_error(
    s: Dict[str, Any],
    e: Exception,
    gr_module: Any,
    dependencies: Dict[str, Any],
    processing_message: Optional[str] = None,
    default_msg: str = DEFAULT_ERROR_OCCURRED,
    tuple_length: int = 8,
    error_context: str = "flow_error"
) -> Tuple:
    """
    Centralized error handling for flow functions.
    
    This is the Single Source of Truth for flow error handling (Principle #2: SSOT).
    All flow functions should use this function for consistent error handling.
    
    **Contract**:
    - **Inputs**: State dict, exception, gradio module, dependencies dict, optional params
    - **Outputs**: Standardized error tuple matching expected format
    - **Invariants**: State must be a dict (validated internally)
    - **Failure Modes**: Always returns valid tuple, never raises exceptions
    
    **Error Sanitization** (Principle #7):
    - Internal error details are logged with correlation IDs (request_id, session_id)
    - User-facing messages are sanitized and don't expose implementation details
    - Error types are categorized for appropriate handling (retryable vs non-retryable)
    - Stack traces and internal error messages are never exposed to users
    
    **Error Recovery** (Principle #16):
    - Attempts to recover corrupted state from disk before creating new state
    - Removes processing messages from history to prevent UI confusion
    - Preserves state integrity even when errors occur
    
    Args:
        s: State dictionary (must be dict, validated internally)
        e: Exception that occurred (any exception type)
        gr_module: Gradio module for UI updates
        dependencies: Dependencies dictionary (must contain error handling functions)
        processing_message: Optional message to remove from history (e.g., "🔊 Generating...")
        default_msg: Default error message if sanitization fails (default: "Error occurred")
        tuple_length: Expected tuple length (8 or 9, default: 8)
        error_context: Context for logging (e.g., "question_generation_error")
        
    Returns:
        Standardized error tuple matching expected format:
        - For tuple_length=8: (state, audio, status, mic, history, cam, proctor, timeout)
        - For tuple_length=9: (state, audio, status, mic, history, cam, proctor, timeout, finish)
        All tuple elements are Gradio update objects or None
        
    Raises:
        Never raises exceptions. Always returns valid tuple even on error.
        
    Example:
        ```python
        try:
            result = some_operation()
        except Exception as e:
            return handle_flow_error(
                s=state,
                e=e,
                gr_module=gr,
                dependencies=dependencies,
                error_context="operation_failed"
            )
        ```
    """
    # Defensive check: ensure s is a dict
    if not isinstance(s, dict):
        # DATA INTEGRITY: Attempt to recover state from disk before creating new state (Principle #22)
        # This prevents data loss when state is corrupted in memory
        session_id = None
        try:
            # Try to extract session_id from corrupted state if possible
            if hasattr(s, 'get'):
                session_id = s.get("session_id") if callable(s.get) else None
            elif isinstance(s, str):
                # If state is a string, try to parse session_id from it
                import re
                match = re.search(r'"session_id"\s*:\s*"([^"]+)"', s)
                if match:
                    session_id = match.group(1)
        except Exception as parse_error:
            # OBSERVABILITY: Log parsing errors for debugging (Principle #13)
            logger.debug(
                "state_session_id_parse_failed",
                error_type=type(parse_error).__name__,
                error_message=str(parse_error)[:200],
                message="Failed to parse session_id from corrupted state, will attempt recovery"
            )
        
        # Attempt recovery from disk if we have a session_id
        if session_id:
            try:
                from exam.state.persistence import load_state_from_disk
                from exam.state.validation import validate_state_invariants
                recovered = load_state_from_disk(session_id)
                if recovered and isinstance(recovered, dict):
                    # DATA INTEGRITY: Validate recovered state before using it (Principle #22)
                    is_valid, validation_error = validate_state_invariants(recovered)
                    if not is_valid:
                        # RECOVERY: Try lenient validation for recovery (allow missing optional fields)
                        # Critical fields that must be present for recovery
                        critical_fields = {"session_id", "request_id", "student_id", "phase"}
                        has_critical = all(field in recovered for field in critical_fields)
                        has_valid_types = (
                            isinstance(recovered.get("history"), list) and
                            isinstance(recovered.get("scores"), list) and
                            isinstance(recovered.get("rubrics"), list)
                        )
                        
                        if has_critical and has_valid_types:
                            # Lenient mode: accept if critical fields present and types are valid
                            # Missing optional fields can be regenerated by ensure_state()
                            is_valid = True
                            logger.warning(
                                "state_recovery_lenient_validation",
                                session_id=session_id,
                                validation_error=validation_error,
                                message="State recovered with lenient validation (missing optional fields will be regenerated)"
                            )
                    
                    if is_valid:
                        s = recovered
                        logger.warning(
                            "state_recovered_from_disk",
                            session_id=session_id,
                            message="State was corrupted in memory but successfully recovered and validated from disk"
                        )
                    else:
                        logger.error(
                            "state_recovery_validation_failed",
                            session_id=session_id,
                            validation_error=validation_error,
                            message="State recovered from disk but failed validation (missing critical fields), will create new state"
                        )
                        # Recovery failed validation, create new state below
                        s = None
                else:
                    # Recovery failed, create new state below
                    s = None
            except Exception as recovery_error:
                logger.error(
                    "state_recovery_failed",
                    session_id=session_id,
                    error_type=type(recovery_error).__name__,
                    error_message=str(recovery_error)[:200],
                    message="Failed to recover state from disk, creating new state"
                )
                # DATA INTEGRITY: Clean up corrupted state file after failed recovery (Principle #22)
                if session_id:
                    try:
                        from exam.file_utils import _paths_for_session
                        import os
                        import uuid
                        import shutil
                        paths = _paths_for_session({"session_id": session_id})
                        state_path = paths.get("STATE_PATH")
                        if state_path and os.path.exists(state_path):
                            # RESOURCE MANAGEMENT: Validate backup directory before moving file
                            backup_dir = os.path.dirname(state_path) or "."
                            if not os.path.exists(backup_dir):
                                logger.warning(
                                    "backup_directory_missing",
                                    session_id=session_id,
                                    backup_dir=backup_dir,
                                    message="Backup directory does not exist, cannot move corrupted file"
                                )
                            elif not os.access(backup_dir, os.W_OK):
                                logger.warning(
                                    "backup_directory_not_writable",
                                    session_id=session_id,
                                    backup_dir=backup_dir,
                                    message="Backup directory is not writable, cannot move corrupted file"
                                )
                            else:
                                # Check disk space (require at least 1MB free)
                                try:
                                    stat = shutil.disk_usage(backup_dir)
                                    free_space_mb = stat.free / (1024 * 1024)
                                    if free_space_mb < 1:
                                        logger.warning(
                                            "insufficient_disk_space",
                                            session_id=session_id,
                                            free_space_mb=free_space_mb,
                                            message="Insufficient disk space for backup, skipping corrupted file move"
                                        )
                                    else:
                                        # DATA INTEGRITY: Use UUID to prevent naming collisions (was timestamp-only)
                                        # DETERMINISTIC: Use time_provider from dependencies if available (Principle #5)
                                        time_provider = dependencies.get("time_provider") or get_default_time_provider()
                                        unique_id = str(uuid.uuid4())[:8]  # Short UUID for readability
                                        corrupted_backup = f"{state_path}.corrupted.{int(time_provider.time())}.{unique_id}"
                                        try:
                                            os.rename(state_path, corrupted_backup)
                                            logger.info(
                                                "corrupted_state_file_moved",
                                                session_id=session_id,
                                                original_path=state_path,
                                                backup_path=corrupted_backup,
                                                message="Moved corrupted state file to backup location"
                                            )
                                        except Exception as move_error:
                                            logger.warning(
                                                "corrupted_state_file_cleanup_failed",
                                                session_id=session_id,
                                                error=str(move_error)[:200],
                                                message="Failed to move corrupted state file"
                                            )
                                except Exception as disk_check_error:
                                    logger.warning(
                                        "disk_space_check_failed",
                                        session_id=session_id,
                                        error=str(disk_check_error)[:200],
                                        message="Failed to check disk space, attempting backup anyway"
                                    )
                                    # Attempt backup anyway if disk check fails
                                    # DETERMINISTIC: Use time_provider from dependencies if available (Principle #5)
                                    time_provider = dependencies.get("time_provider") or get_default_time_provider()
                                    unique_id = str(uuid.uuid4())[:8]
                                    corrupted_backup = f"{state_path}.corrupted.{int(time_provider.time())}.{unique_id}"
                                    try:
                                        os.rename(state_path, corrupted_backup)
                                        logger.info(
                                            "corrupted_state_file_moved",
                                            session_id=session_id,
                                            original_path=state_path,
                                            backup_path=corrupted_backup,
                                            message="Moved corrupted state file to backup location (disk check failed)"
                                        )
                                    except Exception as move_error:
                                        logger.warning(
                                            "corrupted_state_file_cleanup_failed",
                                            session_id=session_id,
                                            error=str(move_error)[:200],
                                            message="Failed to move corrupted state file"
                                        )
                    except Exception as cleanup_error:
                        logger.warning(
                            "corrupted_state_cleanup_error",
                            session_id=session_id,
                            error=str(cleanup_error)[:200],
                            message="Error during corrupted state file cleanup"
                        )
                s = None
        
        # Only create new state if recovery failed or no session_id available
        if not isinstance(s, dict):
            import uuid
            from datetime import datetime, timezone
            logger.warning(
                "state_corruption_new_state_created",
                session_id=session_id or "unknown",
                message="State was corrupted and could not be recovered, creating new minimal state"
            )
            s = {
                "session_id": str(uuid.uuid4()),
                "request_id": str(uuid.uuid4()),
                "student_id": "unknown",
                "phase": "idle",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "session_start_time": 0.0,
                "history": [],
                "scores": [],
                "rubrics": [],
                "flags": [],
                "consent": False,
            }
    
    # Remove temporary processing message if it exists
    # Defensive check: ensure s is a dict and history is a list before modifying
    if isinstance(s, dict) and processing_message and s.get("history"):
        history = s.get("history")
        if isinstance(history, list) and len(history) > 0:
            last_msg = history[-1]
            if isinstance(last_msg, dict) and last_msg.get("content") == processing_message:
                s["history"].pop()
    
    # Get error metadata if available (from with_retry)
    error_metadata = getattr(e, 'error_metadata', None)
    if error_metadata:
        error_message = error_metadata["message"]
        error_type = error_metadata["type"]
        is_retryable = error_metadata["retry"]
    else:
        # Fallback: categorize error manually
        _categorize_error = dependencies.get("_categorize_error")
        if _categorize_error:
            error_type, error_metadata = _categorize_error(e)
            error_message = error_metadata["message"]
            is_retryable = error_metadata.get("retry", False)
        else:
            # Ultimate fallback
            error_type = type(e).__name__
            error_message = default_msg
            is_retryable = True
            error_metadata = {
                "_internal_error_class": error_type,
                "_internal_error": str(e)
            }
    
    # OBSERVABILITY: Log internal error details with correlation ID
    request_id = s.get("request_id", "unknown")
    logger.error(
        error_context,
        request_id=request_id,
        session_id=s.get("session_id", "unknown"),
        error_type=error_metadata.get("_internal_error_class", error_type),
        error_message=error_metadata.get("_internal_error", str(e))[:500],  # Increased from 200 to 500 for better debugging
        is_retryable=is_retryable,
        message=f"{error_context} occurred - internal details logged separately"
    )
    
    # Create user-friendly error message (sanitized)
    user_message = f"❌ {error_message}"
    if is_retryable:
        user_message += " (You can try again)"
    
    # Build error tuple using response builder
    from exam.flow.response_builder import build_error_tuple
    
    # Handle timeout update for 9-tuple returns (like handle_mic)
    timeout_update = None
    if tuple_length >= 9:
        _calculate_timeout_status = dependencies.get("_calculate_timeout_status")
        get_max_answer_timeout_sec = dependencies.get("get_max_answer_timeout_sec")
        if _calculate_timeout_status and get_max_answer_timeout_sec:
            # Use actual timeout calculation if available
            timeout_update = _calculate_timeout_status(s, gr_module, get_max_answer_timeout_sec)
        else:
            # Default: hide timeout
            timeout_update = gr_module.update(value="", visible=False)
    
    return build_error_tuple(
        s=s,
        gr_module=gr_module,
        error_message=user_message,
        mic_interactive=False,
        finish_interactive=False,
        finish_visible=False,
        timeout_update=timeout_update,
        tuple_length=tuple_length
    )


__all__ = [
    "handle_flow_error",
]

