"""
Audio processing and flow control functions for exam interface.

This module contains functions for:
- Microphone recording handling
- Audio transcription and validation
- Flow control (follow-up or grade)

Note: This module uses dependency injection for Gradio and other dependencies
to ensure compatibility across different environments.
"""

import os
import shutil
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable, Tuple, TYPE_CHECKING

from openai import OpenAI

from shared.dependency_extractor import extract_dependencies
from shared.logging_config import get_logger
from shared.constants import (
    PROCESSING_ASSESSMENT_MSG,
    PROCESSING_FOLLOWUP_MSG,
    PROCESSING_AUDIO_RESPONSE_MSG,
    format_processing_message_with_context,
    TIMEOUT_ERROR_MESSAGE,
    TIMEOUT_ERROR_STATUS,
    INFO_CHECK_CONSENT,
    format_termination_message,
)

# Type hints only - no runtime import
if TYPE_CHECKING:
    import gradio as gr

logger = get_logger()


def handle_mic(
    audio_path: str,
    s: Dict[str, Any],
    gr_module,
    client: OpenAI,
    dependencies: Dict[str, Any],
    progress: Optional[Callable] = None
) -> Tuple:
    """
    Handle microphone recording: transcribe, validate, and control flow.
    
    Args:
        audio_path: Path to recorded audio file
        s: State dictionary
        gr_module: Gradio module
        client: OpenAI client
        dependencies: Dictionary with dependencies (see list in docstring)
        progress: Optional progress callback
        
    Returns:
        Tuple of (state, audio, status_update, mic_update, history, cam_update, status_update, finish_update, timeout_update)
    """
    # Extract dependencies (DRY: using helper to reduce duplication)
    deps = extract_dependencies(
        dependencies,
        required_keys=[
            "ensure_state", "update_network_status", "save_state_to_disk",
            "_paths_for_session", "queue_answer_locally", "transcribe",
            "_detect_profanity", "_count_meaningful_words", "_detect_answer_reuse",
            "_hash_answer", "analyze_speech_stylometry", "ask_followup_question",
            "grade_current_block", "tts_to_mp3", "get_max_answer_timeout_sec",
            "_calculate_timeout_status", "_proctor_end_updates", "_categorize_error",
            "MAX_SESSION_DURATION_SEC", "MIN_WORDS", "MAX_SHORT_ATTEMPTS",
            "SHORT_PROMPT_TTS", "time_provider", "get_audio_duration"
        ],
        optional_keys=["extract_audio_features", "compare_voiceprints", "_HAS_LIBROSA"]
    )
    
    s = deps["ensure_state"](s)
    
    # OBSERVABILITY: Log phase for debugging flow issues (Principle #13)
    current_phase = s.get("phase")
    logger.info(
        "handle_mic_phase_check",
        session_id=s.get("session_id", "unknown"),
        phase=current_phase,
        audio_path=audio_path,
        audio_path_present=bool(audio_path),
        message=f"handle_mic called with phase={current_phase}"
    )
    
    # Check for security events (tab blur, clipboard usage)
    # These are detected by JavaScript and stored in localStorage
    # We check for events that occurred during the answer period
    if s.get("phase") in ("awaiting_main_answer", "awaiting_followup_answer"):
        # Import violation thresholds and critical violations from config
        from exam.config import VIOLATION_THRESHOLDS, CRITICAL_VIOLATIONS
        
        # Check for recent security events
        security_events = s.get("security_events", [])
        if security_events:
            # Check for events in the last answer period
            q_time = s.get("current", {}).get("q_time")
            if q_time:
                recent_events = [
                    evt for evt in security_events
                    if evt.get("ts_iso") and 
                    datetime.fromisoformat(evt["ts_iso"].replace("Z", "+00:00")).timestamp() > q_time
                ]
                if recent_events:
                    # Count violations by type
                    violation_counts = {}
                    for evt in recent_events:
                        evt_type = evt.get("type")
                        if evt_type in VIOLATION_THRESHOLDS or evt_type in CRITICAL_VIOLATIONS:
                            violation_counts[evt_type] = violation_counts.get(evt_type, 0) + 1
                    
                    # Check for critical violations (immediate termination)
                    for evt in recent_events:
                        evt_type = evt.get("type")
                        if evt_type in CRITICAL_VIOLATIONS:
                            # Immediate termination for critical violations
                            s.setdefault("flags", []).append(evt_type)
                            s["phase"] = "complete"
                            deps["save_state_to_disk"](s)
                            # Clear auto-saved state to prevent resume
                            try:
                                p = deps["_paths_for_session"](s)
                                if os.path.exists(p["STATE_PATH"]):
                                    os.remove(p["STATE_PATH"])
                            except Exception as cleanup_error:
                                # OBSERVABILITY: Log cleanup errors for debugging (Principle #13)
                                logger.debug(
                                    "state_file_cleanup_failed",
                                    session_id=s.get("session_id", "unknown"),
                                    error_type=type(cleanup_error).__name__,
                                    error_message=str(cleanup_error)[:200],
                                    message="Failed to remove state file during exam termination (non-critical)"
                                )
                            
                            # Stop proctoring if active
                            proctor_cam_upd, proctor_status_upd = deps["_proctor_end_updates"](s, gr_module)
                            
                            # Add termination message to chat history
                            termination_msg = format_termination_message(evt_type)
                            s.setdefault("history", []).append({
                                "role": "assistant",
                                "content": termination_msg
                            })
                            
                            audio = deps["tts_to_mp3"](termination_msg.replace("❌", "").replace("**", ""), client, s)
                            return (
                                s, audio,
                                gr_module.update(value=termination_msg),
                                gr_module.update(value=None, interactive=False),
                                s["history"], proctor_cam_upd, proctor_status_upd, gr_module.update(visible=True, interactive=True), gr_module.update(value="", visible=False)
                            )
                    
                    # Check cumulative violation thresholds
                    for evt_type, count in violation_counts.items():
                        if evt_type in VIOLATION_THRESHOLDS:
                            threshold = VIOLATION_THRESHOLDS[evt_type]
                            
                            # Progressive warning system with countdown
                            remaining = threshold - count
                            
                            if count == 1 and threshold > 1:
                                # First violation - warning with countdown
                                violation_names = {
                                    "TAB_BLUR": "tab switch",
                                    "CLIPBOARD_PASTE": "paste operation",
                                    "CLIPBOARD_COPY": "copy operation",
                                    "ANSWER_REUSE_DETECTED": "answer reuse"
                                }
                                violation_name = violation_names.get(evt_type, evt_type.lower().replace("_", " "))
                                warning_msg = f"⚠️ **First Warning:** {violation_name.capitalize()} detected ({count}/{threshold}). {remaining} more {'warning' if remaining == 1 else 'warnings'} before exam termination."
                                s.setdefault("history", []).append({
                                    "role": "assistant",
                                    "content": warning_msg
                                })
                                # Flag but don't terminate yet
                                if evt_type not in s.get("flags", []):
                                    s.setdefault("flags", []).append(evt_type)
                            
                            elif count == threshold - 1 and threshold > 2:
                                # Final warning (one more before termination)
                                violation_names = {
                                    "TAB_BLUR": "tab switch",
                                    "CLIPBOARD_PASTE": "paste operation",
                                    "CLIPBOARD_COPY": "copy operation",
                                    "ANSWER_REUSE_DETECTED": "answer reuse"
                                }
                                violation_name = violation_names.get(evt_type, evt_type.lower().replace("_", " "))
                                warning_msg = f"⚠️ **Final Warning:** {violation_name.capitalize()} detected ({count}/{threshold}). One more violation will terminate the exam."
                                s.setdefault("history", []).append({
                                    "role": "assistant",
                                    "content": warning_msg
                                })
                                # Ensure flag is set
                                if evt_type not in s.get("flags", []):
                                    s.setdefault("flags", []).append(evt_type)
                            
                            elif count == 2 and threshold > 2:
                                # Second warning (if threshold > 2)
                                violation_names = {
                                    "TAB_BLUR": "tab switch",
                                    "CLIPBOARD_PASTE": "paste operation",
                                    "CLIPBOARD_COPY": "copy operation",
                                    "ANSWER_REUSE_DETECTED": "answer reuse"
                                }
                                violation_name = violation_names.get(evt_type, evt_type.lower().replace("_", " "))
                                warning_msg = f"⚠️ **Second Warning:** {violation_name.capitalize()} detected ({count}/{threshold}). {remaining} more {'warning' if remaining == 1 else 'warnings'} before exam termination."
                                s.setdefault("history", []).append({
                                    "role": "assistant",
                                    "content": warning_msg
                                })
                                # Ensure flag is set
                                if evt_type not in s.get("flags", []):
                                    s.setdefault("flags", []).append(evt_type)
                            
                            elif count >= threshold:
                                # Threshold exceeded - terminate
                                s.setdefault("flags", []).append(evt_type)
                                s.setdefault("flags", []).append(f"{evt_type}_THRESHOLD_EXCEEDED")
                                s["phase"] = "complete"
                                deps["save_state_to_disk"](s)
                                # Clear auto-saved state to prevent resume
                                try:
                                    p = deps["_paths_for_session"](s)
                                    if os.path.exists(p["STATE_PATH"]):
                                        os.remove(p["STATE_PATH"])
                                except Exception:
                                    pass
                                
                                # Stop proctoring if active
                                proctor_cam_upd, proctor_status_upd = deps["_proctor_end_updates"](s, gr_module)
                                
                                # Add termination message to chat history
                                termination_messages = {
                                    "TAB_BLUR": f"❌ **Exam terminated:** Tab switch threshold exceeded ({count}/{threshold}). Exam terminated due to multiple violations.",
                                    "CLIPBOARD_PASTE": f"❌ **Exam terminated:** Paste operation threshold exceeded ({count}/{threshold}). Exam terminated due to multiple violations.",
                                    "CLIPBOARD_COPY": f"❌ **Exam terminated:** Copy operation threshold exceeded ({count}/{threshold}). Exam terminated due to multiple violations.",
                                    "ANSWER_REUSE_DETECTED": f"❌ **Exam terminated:** Answer reuse threshold exceeded ({count}/{threshold}). Exam terminated due to multiple violations."
                                }
                                termination_msg = termination_messages.get(evt_type, f"❌ **Exam terminated:** {evt_type} threshold exceeded ({count}/{threshold}). Exam terminated.")
                                s.setdefault("history", []).append({
                                    "role": "assistant",
                                    "content": termination_msg
                                })
                                
                                audio = deps["tts_to_mp3"](termination_msg.replace("❌", "").replace("**", ""), client, s)
                                return (
                                    s, audio,
                                    gr_module.update(value=termination_msg),
                                    gr_module.update(value=None, interactive=False),
                                    s["history"], proctor_cam_upd, proctor_status_upd, gr_module.update(visible=True, interactive=True), gr_module.update(value="", visible=False)
                                )
                    
                    # Log non-threshold violations (for audit)
                    for evt in recent_events:
                        evt_type = evt.get("type")
                        if evt_type in ("TAB_BLUR", "CLIPBOARD_COPY", "CLIPBOARD_PASTE") and evt_type not in s.get("flags", []):
                            # Only flag if not already flagged and not exceeding threshold
                            if evt_type not in violation_counts or violation_counts[evt_type] < VIOLATION_THRESHOLDS.get(evt_type, float('inf')):
                                s.setdefault("flags", []).append(evt_type)

    # Update network status
    network_status = deps["update_network_status"](s)
    
    # Gate on consent and phase
    if not s.get("consent", False):
        return (
            s, None,
            gr_module.update(value="🔒 Please check the consent box to begin."),
            gr_module.update(value=None, interactive=False),
            s["history"], gr_module.update(), gr_module.update(), gr_module.update(interactive=False)  # Finish button remains disabled
        )
    if s.get("phase") not in ("awaiting_main_answer", "awaiting_followup_answer"):
        # Mic should only be enabled when timer countdown starts (elapsed >= 0)
        from exam.ui.helpers import _calculate_mic_interactive_state
        mic_interactive = _calculate_mic_interactive_state(s, gr_module)
        return (
            s, None,
            gr_module.update(value="ℹ️ Press **Record** once to hear the question, then press **Record** again to answer."),
            gr_module.update(value=None, interactive=mic_interactive),
            s["history"], gr_module.update(), gr_module.update(), gr_module.update(interactive=False), deps["_calculate_timeout_status"](s, gr_module, deps["get_max_answer_timeout_sec"])  # Finish button remains disabled, timeout countdown
        )

    # GUARDRAIL: Session Timeout Check (maximum total exam duration)
    # DETERMINISTIC: Use time_provider instead of time.time() (Principle #5)
    session_start = s.get("session_start_time", 0)
    if session_start:
        time_provider = deps.get("time_provider")
        current_time = time_provider.time() if time_provider else time.time()
        session_elapsed = current_time - session_start
        if session_elapsed > deps["MAX_SESSION_DURATION_SEC"]:
            s.setdefault("flags", []).append("SESSION_TIMEOUT")
            s["phase"] = "complete"
            deps["save_state_to_disk"](s)
            # Clear auto-saved state to prevent resume
            try:
                p = deps["_paths_for_session"](s)
                if os.path.exists(p["STATE_PATH"]):
                    os.remove(p["STATE_PATH"])
            except Exception as cleanup_error:
                # OBSERVABILITY: Log cleanup errors for debugging (Principle #13)
                logger.debug(
                    "state_file_cleanup_failed",
                    session_id=s.get("session_id", "unknown"),
                    error_type=type(cleanup_error).__name__,
                    error_message=str(cleanup_error)[:200],
                    message="Failed to remove state file during exam termination (non-critical)"
                )
            audio = deps["tts_to_mp3"]("Exam session ended due to maximum duration exceeded.", client, s)
            proctor_cam_upd, proctor_status_upd = deps["_proctor_end_updates"](s, gr_module)
            # Add termination message to chat history (only if not already added)
            timeout_message = "⚠️ **Session timeout:** Maximum exam duration exceeded. Exam session ended."
            history = s.get("history", [])
            # Check if message already exists in history to prevent duplicates
            message_exists = any(
                isinstance(msg, dict) and msg.get("content") == timeout_message
                for msg in history
            )
            if not message_exists:
                s.setdefault("history", []).append({
                    "role": "assistant",
                    "content": timeout_message
                })
            return (
                s, audio,
                gr_module.update(value="⚠️ Session timeout: Maximum exam duration exceeded. Exam ended."),
                gr_module.update(value=None, interactive=False),
                s["history"], proctor_cam_upd, proctor_status_upd, gr_module.update(visible=True, interactive=True), gr_module.update(value="", visible=False)  # Show and enable finish button (exam complete), hide timeout countdown
            )
    
    # GUARDRAIL: Answer Timeout Check (maximum time allowed to answer a question)
    # DETERMINISTIC: Use time_provider instead of time.time() (Principle #5)
    q_time = s.get("current", {}).get("q_time")
    if q_time:
        time_provider = deps.get("time_provider")
        current_time = time_provider.time() if time_provider else time.time()
        elapsed = current_time - q_time
        max_timeout = deps["get_max_answer_timeout_sec"](s)  # Pass state to get value from state dict if context var unavailable
        if elapsed > max_timeout:
            s.setdefault("flags", []).append("ANSWER_TIMEOUT")
            s["phase"] = "complete"
            deps["save_state_to_disk"](s)
            # Clear auto-saved state to prevent resume
            try:
                p = deps["_paths_for_session"](s)
                if os.path.exists(p["STATE_PATH"]):
                    os.remove(p["STATE_PATH"])
            except Exception as cleanup_error:
                # OBSERVABILITY: Log cleanup errors for debugging (Principle #13)
                logger.debug(
                    "state_file_cleanup_failed",
                    session_id=s.get("session_id", "unknown"),
                    error_type=type(cleanup_error).__name__,
                    error_message=str(cleanup_error)[:200],
                    message="Failed to remove state file during exam termination (non-critical)"
                )
            audio = deps["tts_to_mp3"]("Exam session ended due to inactivity timeout.", client, s)
            proctor_cam_upd, proctor_status_upd = deps["_proctor_end_updates"](s, gr_module)
            # Add termination message to chat history
            s.setdefault("history", []).append({
                "role": "assistant",
                "content": TIMEOUT_ERROR_MESSAGE
            })
            return (
                s, audio,
                gr_module.update(value=TIMEOUT_ERROR_STATUS),
                gr_module.update(value=None, interactive=False),
                s["history"], proctor_cam_upd, proctor_status_upd, gr_module.update(visible=True, interactive=True), gr_module.update(value="⏱️ **Time expired!**", visible=True)  # Show and enable finish button (exam complete), show timeout expired
            )

    # Stop timer immediately when student stops recording (after timeout check, before processing)
    # This ensures students are only timed on their actual answer time, not system processing time
    # This is fairer as students cannot control transcription/analysis delays
    # DETERMINISTIC: Use time_provider instead of time.time() (Principle #5)
    if s.get("phase") in ("awaiting_main_answer", "awaiting_followup_answer"):
        if q_time:  # q_time still exists from timeout check above
            time_provider = deps.get("time_provider")
            current_time = time_provider.time() if time_provider else time.time()
            # Record submission time for audit trail
            elapsed_at_submission = current_time - q_time
            s["current"]["answer_submitted_at"] = current_time
            s["current"]["answer_time_elapsed"] = elapsed_at_submission
            # Stop timer - student has finished answering
            s["current"]["q_time"] = None

    try:
        # Validate audio file first
        if not audio_path or not os.path.exists(audio_path):
            logger.warning(
                "audio_path_missing_or_invalid",
                session_id=s.get("session_id", "unknown"),
                phase=current_phase,
                audio_path=audio_path,
                audio_path_type=type(audio_path).__name__ if audio_path else "None",
                audio_exists=os.path.exists(audio_path) if audio_path else False,
                message=f"handle_mic called with invalid audio_path: {audio_path}"
            )
            logger.error(
                "audio_file_missing",
                session_id=s.get("session_id", "unknown"),
                audio_path=audio_path,
                audio_path_exists=os.path.exists(audio_path) if audio_path else False,
                phase=current_phase,
                message="No audio file found for processing"
            )
            # Remove processing message if it exists
            if s.get("history") and s["history"][-1].get("content") == "🎤 Processing your audio...":
                s["history"].pop()
            # Add clear error message to chat history so user sees it
            error_msg = "⚠️ **No audio recorded.** Please click **Record**, speak your answer, then click **Stop** to submit."
            if error_msg not in [msg.get("content", "") for msg in s.get("history", [])]:
                s.setdefault("history", []).append({
                    "role": "assistant",
                    "content": error_msg
                })
            # Mic should only be enabled when timer countdown starts (elapsed >= 0)
            from exam.ui.helpers import _calculate_mic_interactive_state
            mic_interactive = _calculate_mic_interactive_state(s, gr_module)
            return (
                s, None,
                gr_module.update(value=error_msg),
                gr_module.update(value=None, interactive=mic_interactive),
                s["history"], gr_module.update(), gr_module.update(), gr_module.update(interactive=False), deps["_calculate_timeout_status"](s, gr_module, deps["get_max_answer_timeout_sec"])
            )
        
        # Log successful audio path validation
        logger.debug(
            "audio_path_valid",
            session_id=s.get("session_id", "unknown"),
            phase=current_phase,
            audio_path=audio_path,
            audio_exists=True,
            message=f"Audio file validated, proceeding with transcription"
        )
        print(f"[AUDIO_FLOW] Audio file validated: audio_path={audio_path}, phase={current_phase}", flush=True)
        
        # Copy audio file to session directory to ensure persistence
        # Gradio's temp files may be cleaned up, so we copy to session-specific directory
        # This ensures the file is available for transcription, voiceprint analysis, and offline queuing
        original_audio_path = audio_path
        copy_success = False
        max_retries = 1  # Retry once if copy fails
        
        for attempt in range(max_retries + 1):
            try:
                paths = deps["_paths_for_session"](s)
                session_tmp_dir = paths["TMP_DIR"]
                os.makedirs(session_tmp_dir, exist_ok=True)
                
                # Generate unique filename for this recording
                audio_filename = f"recording_{uuid.uuid4().hex[:8]}.wav"
                session_audio_path = os.path.join(session_tmp_dir, audio_filename)
                
                # SECURITY: Validate path to prevent path traversal attacks
                # Ensure the resolved path is within the session temp directory
                abs_session_tmp_dir = os.path.abspath(session_tmp_dir)
                abs_session_audio_path = os.path.abspath(session_audio_path)
                if not abs_session_audio_path.startswith(abs_session_tmp_dir):
                    raise ValueError(
                        f"Invalid audio path - path traversal detected: "
                        f"session_audio_path={session_audio_path}, "
                        f"session_tmp_dir={session_tmp_dir}"
                    )
                
                # Copy file to session directory
                shutil.copy2(audio_path, session_audio_path)
                
                # Track in state for cleanup
                s.setdefault("_tmp_files", []).append(session_audio_path)
                
                # Use copied path for all subsequent operations
                audio_path = session_audio_path
                copy_success = True
                
                logger.debug(
                    "audio_file_copied_to_session",
                    session_id=s.get("session_id", "unknown"),
                    original_path=original_audio_path,
                    session_path=session_audio_path,
                    attempt=attempt + 1,
                    message="Audio file copied to session directory for persistence"
                )
                break  # Success - exit retry loop
                
            except Exception as copy_error:
                # If copy fails, log warning and retry if attempts remaining
                if attempt < max_retries:
                    logger.warning(
                        "audio_file_copy_failed_retrying",
                        session_id=s.get("session_id", "unknown"),
                        original_path=original_audio_path,
                        error_type=type(copy_error).__name__,
                        error_message=str(copy_error)[:200],
                        attempt=attempt + 1,
                        max_retries=max_retries + 1,
                        message=f"Failed to copy audio file (attempt {attempt + 1}/{max_retries + 1}), retrying..."
                    )
                    # Wait a bit before retry (exponential backoff)
                    time.sleep(0.1 * (attempt + 1))
                else:
                    # Final attempt failed - log error and continue with original path
                    logger.warning(
                        "audio_file_copy_failed",
                        session_id=s.get("session_id", "unknown"),
                        original_path=original_audio_path,
                        error_type=type(copy_error).__name__,
                        error_message=str(copy_error)[:200],
                        attempts=max_retries + 1,
                        message="Failed to copy audio file to session directory after all retries, using original path"
                    )
                    # Continue with original path if copy fails
                    copy_success = False
        
        if not copy_success:
            logger.warning(
                "audio_file_copy_final_failure",
                session_id=s.get("session_id", "unknown"),
                original_path=original_audio_path,
                message="Using original audio path - session copy failed. File may be cleaned up by Gradio."
            )
        
        # Check network status before transcription
        if network_status == "offline":
            # Queue answer locally when offline (using copied audio path)
            deps["queue_answer_locally"](s, "(Audio recorded offline - will process when connection restored)", audio_path)
            s["history"].append({"role": "user", "content": "📴 Answer recorded offline. Will process when connection is restored."})
            # Mic should only be enabled when timer countdown starts (elapsed >= 0)
            # After recording stops, q_time is cleared, so mic will be disabled
            from exam.ui.helpers import _calculate_mic_interactive_state
            mic_interactive = _calculate_mic_interactive_state(s, gr_module)
            return (
                s, None,
                gr_module.update(value="📴 Offline: Answer recorded locally. Will process when connection is restored."),
                gr_module.update(value=None, interactive=mic_interactive),
                s["history"], gr_module.update(), gr_module.update(), gr_module.update(interactive=False), deps["_calculate_timeout_status"](s, gr_module, deps["get_max_answer_timeout_sec"])
            )
        
        # Transcribe
        s["history"].append({"role": "user", "content": "🎤 Processing your audio..."})
        try:
            text = deps["transcribe"](audio_path, client, progress=progress).strip()
            if not text:
                logger.warning(
                    "transcription_empty",
                    session_id=s.get("session_id", "unknown"),
                    audio_path=audio_path,
                    audio_exists=os.path.exists(audio_path) if audio_path else False,
                    audio_size=os.path.getsize(audio_path) if audio_path and os.path.exists(audio_path) else 0,
                    message="Transcription returned empty text"
                )
                text = "(Unclear audio—please try again.)"
            else:
                logger.debug(
                    "transcription_success",
                    session_id=s.get("session_id", "unknown"),
                    audio_path=audio_path,
                    transcript_length=len(text),
                    transcript_preview=text[:100] if text else "",
                    message="Audio transcription successful"
                )
        except Exception as transcribe_error:
            logger.error(
                "transcription_failed",
                session_id=s.get("session_id", "unknown"),
                audio_path=audio_path,
                audio_exists=os.path.exists(audio_path) if audio_path else False,
                audio_size=os.path.getsize(audio_path) if audio_path and os.path.exists(audio_path) else 0,
                error_type=type(transcribe_error).__name__,
                error_message=str(transcribe_error)[:200],
                message="Audio transcription failed"
            )
            text = f"(Transcription error: {type(transcribe_error).__name__})"
        # Replace temporary processing message with actual transcription
        s["history"][-1] = {"role": "user", "content": text}
        
        # Keep processing message active until grading starts
        # This ensures progress bar stays visible between transcription and assessment generation
        # The message will be replaced by grading.py when assessment is ready
        # ORDERING FIX: Check if this is a follow-up answer to use correct message type
        # Determine if this is a follow-up or main answer
        is_followup = (
            s.get("current", {}).get("followups_done", 0) > 0 or
            s.get("phase") == "awaiting_followup_answer"
        )
        
        # Use appropriate message based on answer type
        processing_msg = PROCESSING_FOLLOWUP_MSG if is_followup else PROCESSING_ASSESSMENT_MSG
        msg_with_context = format_processing_message_with_context(
            processing_msg,
            s,
            include_followup_info=is_followup
        )
        s["history"].append({"role": "assistant", "content": msg_with_context})
        
        # Debug logging: Transcription complete
        logger.debug(
            "transcription_complete_proceeding_to_flow",
            session_id=s.get("session_id", "unknown"),
            phase=s.get("phase"),
            text_length=len(text) if text else 0,
            text_preview=text[:50] if text else "",
            message="Transcription complete, proceeding to validation and flow control"
        )

        # PROFANITY CHECK: Terminate session if profanity detected
        if deps["_detect_profanity"](text):
            # Text already in history (replacing processing message), no need to append again
            # Record the text for audit trail before terminating
            s["current"]["answers"].append(text)
            s["answers_tslog_all"].append({"ts_iso": datetime.now(timezone.utc).isoformat() + "Z", "text": text})
            s.setdefault("flags", []).append("PROFANITY_DETECTED")
            # Stop timer when profanity is detected
            s["current"]["q_time"] = None
            s["phase"] = "complete"
            deps["save_state_to_disk"](s)
            # Clear auto-saved state to prevent resume
            try:
                p = deps["_paths_for_session"](s)
                if os.path.exists(p["STATE_PATH"]):
                    os.remove(p["STATE_PATH"])
            except Exception:
                pass
            
            # Stop proctoring if active
            proctor_cam_upd, proctor_status_upd = deps["_proctor_end_updates"](s, gr_module)
            
            # Add termination message to chat history
            s.setdefault("history", []).append({
                "role": "assistant",
                "content": "❌ **Profanity detected:** Exam terminated due to inappropriate language. You need to redo the Viva Voce."
            })
            
            # Terminate with message
            termination_message = "Profanity detected. You need to redo the Viva Voce."
            audio = deps["tts_to_mp3"](termination_message, client, s)
            return (
                s, audio,
                gr_module.update(value="❌ Profanity detected. You need to redo the Viva Voce."),
                gr_module.update(value=None, interactive=False),
                s["history"], proctor_cam_upd, proctor_status_upd, gr_module.update(visible=True, interactive=True), gr_module.update(value="", visible=False)  # Show and enable finish button (exam complete), hide timeout countdown
            )

        # ADVANCED ANTI-CHEAT: Voiceprint consistency check
        # Only run if librosa is available for voiceprint analysis
        if deps["_HAS_LIBROSA"] and deps["extract_audio_features"] and deps["compare_voiceprints"]:
            audio_features = deps["extract_audio_features"](audio_path)
            if audio_features:
                consent_features = s.get("consent_audio_features")
                if consent_features:
                    voice_similar = deps["compare_voiceprints"](consent_features, audio_features)
                    if not voice_similar:
                        # Critical violation - immediate termination
                        from exam.config import CRITICAL_VIOLATIONS
                        s.setdefault("flags", []).append("VOICEPRINT_MISMATCH")
                        s["phase"] = "complete"
                        deps["save_state_to_disk"](s)
                        # Clear auto-saved state to prevent resume
                        try:
                            p = deps["_paths_for_session"](s)
                            if os.path.exists(p["STATE_PATH"]):
                                os.remove(p["STATE_PATH"])
                        except Exception:
                            pass
                        
                        # Stop proctoring if active
                        proctor_cam_upd, proctor_status_upd = deps["_proctor_end_updates"](s, gr_module)
                        
                        # Add termination message to chat history
                        termination_msg = "❌ **Critical violation:** Voiceprint mismatch detected. Different person detected. Exam terminated."
                        s.setdefault("history", []).append({
                            "role": "assistant",
                            "content": termination_msg
                        })
                        
                        audio = deps["tts_to_mp3"]("Critical violation: Voiceprint mismatch detected. Different person detected. Exam terminated.", client, s)
                        return (
                            s, audio,
                            gr_module.update(value=termination_msg),
                            gr_module.update(value=None, interactive=False),
                            s["history"], proctor_cam_upd, proctor_status_upd, gr_module.update(visible=True, interactive=True), gr_module.update(value="", visible=False)
                        )
                else:
                    # Store consent features for future comparison (first recording after consent)
                    s["consent_audio_features"] = audio_features
        
        # GUARDRAIL: AI-Generated Answer Detection (Stylometric Consistency Check)
        # Detects unnatural fluency patterns: speech rate, hesitation, lexical diversity, zero-pause delivery
        prev_answers = s.get("current", {}).get("answers", [])
        stylo_flags = deps["analyze_speech_stylometry"](text, prev_answers)
        for flag in stylo_flags:
            s.setdefault("flags", []).append(flag)

        # GUARDRAIL: Enhanced Answer Reuse Detection (prevents recycling of memorized responses)
        # Checks both exact hash matches AND semantic similarity to catch near-duplicates
        previous_hashes = s.get("answer_hashes", [])
        previous_texts = s.get("answer_texts", [])
        if deps["_detect_answer_reuse"](text, previous_hashes, previous_texts):
            from exam.config import VIOLATION_THRESHOLDS
            s.setdefault("flags", []).append("ANSWER_REUSE_DETECTED")
            
            # Count answer reuse violations
            reuse_count = sum(1 for flag in s.get("flags", []) if flag == "ANSWER_REUSE_DETECTED")
            threshold = VIOLATION_THRESHOLDS.get("ANSWER_REUSE_DETECTED", 2)
            
            # Progressive warning system
            if reuse_count == 1 and threshold > 1:
                # First violation - warning only
                warning_msg = "⚠️ **Warning:** Answer reuse detected. Multiple violations will result in exam termination."
                s.setdefault("history", []).append({
                    "role": "assistant",
                    "content": warning_msg
                })
            elif reuse_count >= threshold:
                # Threshold exceeded - terminate
                s.setdefault("flags", []).append("ANSWER_REUSE_DETECTED_THRESHOLD_EXCEEDED")
                s["phase"] = "complete"
                deps["save_state_to_disk"](s)
                # Clear auto-saved state to prevent resume
                try:
                    p = deps["_paths_for_session"](s)
                    if os.path.exists(p["STATE_PATH"]):
                        os.remove(p["STATE_PATH"])
                except Exception:
                    pass
                
                # Stop proctoring if active
                proctor_cam_upd, proctor_status_upd = deps["_proctor_end_updates"](s, gr_module)
                
                # Add termination message to chat history
                termination_msg = f"❌ **Exam terminated:** Answer reuse threshold exceeded ({reuse_count}/{threshold}). Exam terminated due to multiple violations."
                s.setdefault("history", []).append({
                    "role": "assistant",
                    "content": termination_msg
                })
                
                audio = deps["tts_to_mp3"](termination_msg.replace("❌", "").replace("**", ""), client, s)
                return (
                    s, audio,
                    gr_module.update(value=termination_msg),
                    gr_module.update(value=None, interactive=False),
                    s["history"], proctor_cam_upd, proctor_status_upd, gr_module.update(visible=True, interactive=True), gr_module.update(value="", visible=False)
                )
        
        # Store hash and text of current answer for future comparison
        answer_hash = deps["_hash_answer"](text)
        s.setdefault("answer_hashes", []).append(answer_hash)
        s.setdefault("answer_texts", []).append(text)  # Store text for semantic similarity

        # Transcription already added to history (replacing processing message)
        # Append to answers and audit log
        s["current"]["answers"].append(text)
        s["answers_tslog_all"].append({"ts_iso": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z", "text": text})
        deps["save_state_to_disk"](s)

        # Duplicate detection: remove consecutive duplicate user messages
        if len(s.get("history", [])) >= 2:
            if (s["history"][-1].get("role") == "user" and 
                s["history"][-2].get("role") == "user" and
                s["history"][-1].get("content") == s["history"][-2].get("content")):
                s["history"].pop()  # Remove duplicate

        # Short-answer handling
        words = deps["_count_meaningful_words"](text)
        if words < deps["MIN_WORDS"]:
            s["current"]["short_attempts"] += 1
            # If we still have retries left, prompt and stop here
            if s["current"]["short_attempts"] < deps["MAX_SHORT_ATTEMPTS"]:
                # Add brief prompt to history (so it appears in chat and audio plays)
                s["history"].append({"role":"assistant","content":PROCESSING_AUDIO_RESPONSE_MSG})
                s["history"][-1] = {"role":"assistant","content":deps["SHORT_PROMPT_TTS"]}
                audio = deps["tts_to_mp3"](deps["SHORT_PROMPT_TTS"], client, s, progress=progress)
                # Get audio duration and start timer AFTER audio finishes playing
                # This allows student to re-answer after the brief prompt plays
                audio_duration = deps["get_audio_duration"](audio) if audio else 0.0
                # DETERMINISTIC: Use time_provider instead of time.time() (Principle #5)
                time_provider = deps.get("time_provider")
                if time_provider:
                    s["current"]["q_time"] = time_provider.time() + audio_duration
                # Store audio path in state so it persists across _stream_proctor calls
                if audio:
                    s["current"]["last_examiner_audio"] = audio
                # Mic should only be enabled when timer countdown starts (elapsed >= 0)
                # Timer starts after audio finishes, so mic will be enabled then
                from exam.ui.helpers import _calculate_mic_interactive_state
                mic_interactive = _calculate_mic_interactive_state(s, gr_module)
                return (
                    s, audio,
                    gr_module.update(value="ℹ️ Your answer seems brief. Please elaborate."),
                    gr_module.update(value=None, interactive=mic_interactive),
                    s["history"], gr_module.update(), gr_module.update(), gr_module.update(interactive=False), deps["_calculate_timeout_status"](s, gr_module, deps["get_max_answer_timeout_sec"])  # Finish button remains disabled, timeout countdown
                )
            # Otherwise, continue flow but reset the counter
            s["current"]["short_attempts"] = 0
        else:
            # Good-length answer resets the counter
            s["current"]["short_attempts"] = 0

        # Timer already stopped when recording ended (for fairness - students only timed on answer time, not processing)
        # Flow control: follow-up or grade
        if s["phase"] == "awaiting_main_answer":
            # Safety check: Ensure current block exists
            if "current" not in s or s["current"] is None:
                s["current"] = {}
            s["current"]["followups_done"] = 0
            # Ensure target_followups is set (defensive check)
            if "target_followups" not in s["current"]:
                # Fallback: get from state if available
                get_followup_range = deps.get("get_followup_range")
                if get_followup_range:
                    followups_min, followups_max = get_followup_range(s)
                    # Use same logic as in grading.py and questions.py
                    if followups_max == 0:
                        s["current"]["target_followups"] = 0
                    elif followups_min == 0 and followups_max == 1:
                        s["current"]["target_followups"] = s["_rng"].randint(0, 1)
                    else:
                        s["current"]["target_followups"] = s["_rng"].randint(followups_min, followups_max)
                else:
                    # Ultimate fallback
                    s["current"]["target_followups"] = 0
            
            # Only ask followup if target_followups > 0
            target_followups = s["current"].get("target_followups", 0)
            
            # Debug logging: Flow control decision
            logger.debug(
                "flow_control_main_answer",
                session_id=s.get("session_id", "unknown"),
                phase=s.get("phase"),
                target_followups=target_followups,
                followups_done=s["current"].get("followups_done", 0),
                has_ask_followup="ask_followup_question" in deps,
                has_grade_block="grade_current_block" in deps,
                message=f"Flow control: phase=awaiting_main_answer, target_followups={target_followups}"
            )
            logger.debug(
                "audio_flow_control",
                session_id=s.get("session_id", "unknown"),
                phase="awaiting_main_answer",
                target_followups=target_followups,
                has_ask_followup='ask_followup_question' in deps,
                has_grade_block='grade_current_block' in deps,
                message="Audio flow control decision point"
            )
            
            if target_followups > 0:
                # Verify dependency exists
                if "ask_followup_question" not in deps:
                    logger.error(
                        "missing_dependency_ask_followup",
                        session_id=s.get("session_id", "unknown"),
                        available_keys=list(deps.keys()),
                        message="ask_followup_question dependency missing, falling back to grade"
                    )
                    # Fallback: grade instead
                    if "grade_current_block" in deps:
                        s, audio, status_upd, mic_upd, _hist, cam_upd, cam_status_upd, finish_upd = deps["grade_current_block"](
                            s, gr_module, client, dependencies, progress=progress
                        )
                        if audio:
                            s["current"]["last_examiner_audio"] = audio
                        return s, audio, status_upd, mic_upd, s["history"], cam_upd, cam_status_upd, finish_upd, gr_module.update(value="", visible=False)
                    else:
                        logger.error(
                            "missing_dependency_grade_block",
                            session_id=s.get("session_id", "unknown"),
                            message="Both ask_followup_question and grade_current_block missing!"
                        )
                        raise ValueError("Missing required dependencies: ask_followup_question and grade_current_block")
                
                try:
                    logger.debug(
                        "calling_ask_followup_question",
                        session_id=s.get("session_id", "unknown"),
                        message="Calling ask_followup_question"
                    )
                    s, audio, status_upd, mic_upd, _hist, cam_upd, cam_status_upd, finish_upd, timeout_upd = deps["ask_followup_question"](
                        s, gr_module, client, dependencies, progress=progress
                    )
                    logger.debug(
                        "ask_followup_question_complete",
                        session_id=s.get("session_id", "unknown"),
                        has_audio=audio is not None,
                        message="ask_followup_question completed successfully"
                    )
                    # Store audio path in state so it persists across _stream_proctor calls
                    if audio:
                        s["current"]["last_examiner_audio"] = audio
                    return s, audio, status_upd, mic_upd, s["history"], cam_upd, cam_status_upd, finish_upd, timeout_upd  # Use timeout countdown from ask_followup_question
                except Exception as followup_error:
                    logger.error(
                        "ask_followup_question_failed",
                        session_id=s.get("session_id", "unknown"),
                        error_type=type(followup_error).__name__,
                        error_message=str(followup_error)[:500],
                        message="ask_followup_question raised exception"
                    )
                    # Re-raise to be caught by outer exception handler
                    raise
            else:
                # No followups needed, grade immediately
                if "grade_current_block" not in deps:
                    logger.error(
                        "missing_dependency_grade_block",
                        session_id=s.get("session_id", "unknown"),
                        available_keys=list(deps.keys()),
                        message="grade_current_block dependency missing!"
                    )
                    raise ValueError("Missing required dependency: grade_current_block")
                
                try:
                    logger.debug(
                        "calling_grade_current_block",
                        session_id=s.get("session_id", "unknown"),
                        message="Calling grade_current_block (no followups needed)"
                    )
                    s, audio, status_upd, mic_upd, _hist, cam_upd, cam_status_upd, finish_upd = deps["grade_current_block"](
                        s, gr_module, client, dependencies, progress=progress
                    )
                    logger.debug(
                        "grade_current_block_complete",
                        session_id=s.get("session_id", "unknown"),
                        has_audio=audio is not None,
                        message="grade_current_block completed successfully"
                    )
                    # Store audio path in state so it persists across _stream_proctor calls
                    if audio:
                        s["current"]["last_examiner_audio"] = audio
                    return s, audio, status_upd, mic_upd, s["history"], cam_upd, cam_status_upd, finish_upd, gr_module.update(value="", visible=False)  # Hide timeout countdown when grading
                except Exception as grade_error:
                    logger.error(
                        "grade_current_block_failed",
                        session_id=s.get("session_id", "unknown"),
                        error_type=type(grade_error).__name__,
                        error_message=str(grade_error)[:500],
                        message="grade_current_block raised exception"
                    )
                    # Re-raise to be caught by outer exception handler
                    raise

        # Handle followup answers - only process when phase is "awaiting_followup_answer"
        if s["phase"] == "awaiting_followup_answer":
            # Ensure followups_done is initialized
            if "followups_done" not in s["current"]:
                s["current"]["followups_done"] = 0
            s["current"]["followups_done"] += 1
            target_followups = s["current"].get("target_followups", 0)
            
            # Debug logging (can help diagnose flow issues)
            logger.debug(
                "flow_control_followup_answer",
                session_id=s.get("session_id", "unknown"),
                followups_done=s['current']['followups_done'],
                target_followups=target_followups,
                phase=s.get('phase'),
                asked_main=s.get('asked_main', 0),
                has_ask_followup="ask_followup_question" in deps,
                has_grade_block="grade_current_block" in deps,
                message=f"Flow control: phase=awaiting_followup_answer, followups_done={s['current']['followups_done']}/{target_followups}"
            )
            
            if s["current"]["followups_done"] < target_followups:
                # More followups needed
                if "ask_followup_question" not in deps:
                    logger.error(
                        "missing_dependency_ask_followup",
                        session_id=s.get("session_id", "unknown"),
                        available_keys=list(deps.keys()),
                        message="ask_followup_question dependency missing, falling back to grade"
                    )
                    # Fallback: grade instead
                    if "grade_current_block" in deps:
                        s, audio, status_upd, mic_upd, _hist, cam_upd, cam_status_upd, finish_upd = deps["grade_current_block"](
                            s, gr_module, client, dependencies, progress=progress
                        )
                        if audio:
                            s["current"]["last_examiner_audio"] = audio
                        return s, audio, status_upd, mic_upd, s["history"], cam_upd, cam_status_upd, finish_upd, gr_module.update(value="", visible=False)
                    else:
                        raise ValueError("Missing required dependencies: ask_followup_question and grade_current_block")
                
                try:
                    # Update processing message to indicate follow-up is coming
                    # This provides clarity to the user about what's happening next
                    if isinstance(s.get("history"), list):
                        for i in range(len(s["history"]) - 1, -1, -1):
                            if isinstance(s["history"][i], dict) and PROCESSING_ASSESSMENT_MSG in s["history"][i].get("content", ""):
                                # Add progress context including follow-up info
                                msg_with_context = format_processing_message_with_context(
                                    PROCESSING_FOLLOWUP_MSG,
                                    s,
                                    include_followup_info=True
                                )
                                s["history"][i] = {"role": "assistant", "content": msg_with_context}
                                break
                    
                    logger.debug(
                        "calling_ask_followup_question_followup",
                        session_id=s.get("session_id", "unknown"),
                        followup_number=s["current"]["followups_done"],
                        message=f"Calling ask_followup_question (followup {s['current']['followups_done']}/{target_followups})"
                    )
                    s, audio, status_upd, mic_upd, _hist, cam_upd, cam_status_upd, finish_upd, timeout_upd = deps["ask_followup_question"](
                        s, gr_module, client, dependencies, progress=progress
                    )
                    logger.debug(
                        "ask_followup_question_complete_followup",
                        session_id=s.get("session_id", "unknown"),
                        has_audio=audio is not None,
                        message="ask_followup_question completed successfully"
                    )
                    # Store audio path in state so it persists across _stream_proctor calls
                    if audio:
                        s["current"]["last_examiner_audio"] = audio
                    return s, audio, status_upd, mic_upd, s["history"], cam_upd, cam_status_upd, finish_upd, timeout_upd  # Use timeout countdown from ask_followup_question
                except Exception as followup_error:
                    logger.error(
                        "ask_followup_question_failed_followup",
                        session_id=s.get("session_id", "unknown"),
                        error_type=type(followup_error).__name__,
                        error_message=str(followup_error)[:500],
                        message="ask_followup_question raised exception"
                    )
                    raise
            else:
                # All followups done, grade now
                if "grade_current_block" not in deps:
                    logger.error(
                        "missing_dependency_grade_block",
                        session_id=s.get("session_id", "unknown"),
                        available_keys=list(deps.keys()),
                        message="grade_current_block dependency missing!"
                    )
                    raise ValueError("Missing required dependency: grade_current_block")
                
                try:
                    logger.debug(
                        "calling_grade_current_block_followup",
                        session_id=s.get("session_id", "unknown"),
                        followups_completed=s["current"]["followups_done"],
                        message="Calling grade_current_block (all followups completed)"
                    )
                    s, audio, status_upd, mic_upd, _hist, cam_upd, cam_status_upd, finish_upd = deps["grade_current_block"](
                        s, gr_module, client, dependencies, progress=progress
                    )
                    logger.debug(
                        "grade_current_block_complete_followup",
                        session_id=s.get("session_id", "unknown"),
                        has_audio=audio is not None,
                        message="grade_current_block completed successfully"
                    )
                    # Store audio path in state so it persists across _stream_proctor calls
                    if audio:
                        s["current"]["last_examiner_audio"] = audio
                    return s, audio, status_upd, mic_upd, s["history"], cam_upd, cam_status_upd, finish_upd, gr_module.update(value="", visible=False)  # Hide timeout countdown when grading
                except Exception as grade_error:
                    logger.error(
                        "grade_current_block_failed_followup",
                        session_id=s.get("session_id", "unknown"),
                        error_type=type(grade_error).__name__,
                        error_message=str(grade_error)[:500],
                        message="grade_current_block raised exception"
                    )
                    raise

        # Handle unexpected phases (fallback for debugging)
        if s.get("phase") not in ("awaiting_main_answer", "awaiting_followup_answer"):
            logger.warning(
                "unexpected_phase_in_handle_mic",
                session_id=s.get("session_id", "unknown"),
                phase=s.get("phase"),
                message=f"handle_mic called with unexpected phase: {s.get('phase')}"
            )
            print(f"[AUDIO_FLOW_ERROR] Unexpected phase: {s.get('phase')}", flush=True)
            # Return a safe fallback response
            return (
                s,
                None,  # audio
                gr_module.update(value=f"⚠️ Unexpected phase: {s.get('phase')}. Please refresh."),
                gr_module.update(),  # mic_update
                s.get("history", []),  # history
                gr_module.update(),  # cam_update
                gr_module.update(),  # cam_status_update
                gr_module.update(),  # finish_update
                gr_module.update()  # timeout_update
            )

    except Exception as e:
        # Use centralized error handling
        from exam.flow.error_handling import handle_flow_error
        return handle_flow_error(
            s=s,
            e=e,
            gr_module=gr_module,
            dependencies=deps,
            processing_message="🎤 Processing your audio...",
            default_msg="Audio processing failed",
            tuple_length=9,
            error_context="audio_processing_error"
        )

