"""
UI helper functions for exam interface.

This module contains helper functions for calculating UI display values:
- Timeout status calculation
- Progress metrics calculation
- Processing status extraction
- Connection status calculation
- Proctor webcam streaming
- Step indicator HTML generation

Note: This module uses dependency injection for Gradio to ensure compatibility
across different environments (Railway, Hugging Face, local). Gradio is passed
as a parameter rather than imported directly.
"""

import time
import os
from typing import Dict, Any, Callable, Optional, TYPE_CHECKING
from shared.time_provider import get_default_time_provider

# Type hints only - no runtime import
if TYPE_CHECKING:
    import gradio as gr

from shared.logging_config import get_logger
from shared.constants import (
    PROCESSING_ASSESSMENT_MSG,
    PROCESSING_FOLLOWUP_MSG,
    PROCESSING_AUDIO_RESPONSE_MSG,
    PROCESSING_AUDIO_MSG,
    UI_STATUS_GENERATING_QUESTION,
    UI_STATUS_ASKING_FOLLOWUP,
    UI_STATUS_GENERATING_ASSESSMENT,
    UI_STATUS_PROCESSING_AUDIO,
    TIMEOUT_ERROR_MESSAGE,
    STATUS_QUESTION_ASKED,
    STATUS_EXAM_COMPLETED,
    STATUS_EXAM_TERMINATED,
    INFO_CHECK_CHAT_HISTORY,
    TERMINATION_KEYWORDS,
    format_termination_message,
)
from exam.state import ensure_state, save_state_to_disk, auto_save_state, update_network_status
from exam.state.network import get_queue_status
from exam.context_vars import (
    get_n_questions,
    get_followups_max,
    get_max_answer_timeout_sec,
)
from exam.proctor import ProctorState, proctor_analyze_frame, PROCTOR_CONFIG
from exam.config import PROCESSING_BUFFER_SEC, SESSION_BUFFER_SEC
from shared.logging_config import get_logger

logger = get_logger()


def _calculate_timeout_status(
    s: Dict[str, Any],
    gr_module,  # Gradio module passed as dependency
    get_max_answer_timeout_sec_fn: Optional[Callable] = None,
):
    """
    Calculate timeout status for real-time display in MM:SS format with color-coding.
    
    Remaining time is clamped to 0 (never shows negative values). When remaining == 0,
    displays "00:00 - Time expired!" in red. Automatic termination is handled by
    _stream_proctor when elapsed >= max_timeout.
    
    Args:
        s: State dictionary
        gr_module: Gradio module (passed as dependency for version compatibility)
        get_max_answer_timeout_sec_fn: Optional function to get max answer timeout
        
    Returns:
        Gradio update object with timeout display
    """
    q_time = s.get("current", {}).get("q_time")
    if not q_time:
        return gr_module.update(value="", visible=False)
    
    # DETERMINISTIC: Use time_provider instead of time.time() (Principle #5)
    time_provider = get_default_time_provider()
    elapsed = time_provider.time() - q_time
    
    # If elapsed is negative, audio hasn't finished yet - hide timer until it finishes
    if elapsed < 0:
        return gr_module.update(value="", visible=False)
    
    # Get timeout from function or use default (pass state for cross-context reliability)
    if get_max_answer_timeout_sec_fn:
        max_timeout = get_max_answer_timeout_sec_fn(s)  # Pass state to get value from state dict if context var unavailable
    else:
        max_timeout = get_max_answer_timeout_sec(s)  # Pass state to get value from state dict if context var unavailable
    
    remaining = max_timeout - elapsed
    
    # Clamp remaining to 0 - never show negative time
    remaining = max(0, remaining)
    
    # Format as MM:SS
    minutes = int(remaining // 60)
    seconds = int(remaining % 60)
    time_str = f"{minutes:02d}:{seconds:02d}"
    
    # Color-coding based on remaining time (compact size)
    if remaining == 0:
        # Red - time expired
        return gr_module.update(value=f"<span style='color: #dc3545; font-weight: bold; font-size: 13px;'>⏱️ {time_str} - Time expired!</span>", visible=True)
    elif remaining <= 5:
        # Red - critical warning
        return gr_module.update(value=f"<span style='color: #dc3545; font-weight: bold; font-size: 13px;'>⏱️ {time_str}</span>", visible=True)
    elif remaining <= 15:
        # Orange - warning
        return gr_module.update(value=f"<span style='color: #fd7e14; font-weight: bold; font-size: 13px;'>⏱️ {time_str}</span>", visible=True)
    elif remaining <= 30:
        # Yellow - caution
        return gr_module.update(value=f"<span style='color: #ffc107; font-weight: bold; font-size: 13px;'>⏱️ {time_str}</span>", visible=True)
    else:
        # Green - normal
        return gr_module.update(value=f"<span style='color: #28a745; font-weight: bold; font-size: 13px;'>⏱️ {time_str}</span>", visible=True)


def _calculate_mic_interactive_state(s: Dict[str, Any], gr_module) -> bool:
    """
    Determine if microphone should be interactive based on timer state.
    
    Mic should be enabled ONLY when:
    1. Timer countdown is active (elapsed >= 0)
    2. Phase is awaiting answer (awaiting_main_answer or awaiting_followup_answer)
    3. Exam is not complete
    4. Timer has not expired (remaining > 0)
    
    Mic should be disabled when:
    1. Timer hasn't started yet (elapsed < 0, audio still playing)
    2. Timer expired (remaining <= 0)
    3. Recording stopped and processing began (q_time is None)
    4. Exam is complete
    5. Not in answer phase
    
    Args:
        s: State dictionary
        gr_module: Gradio module (passed as dependency for version compatibility)
        
    Returns:
        bool: True if mic should be interactive, False otherwise
    """
    s = ensure_state(s)
    
    # Disable if exam is complete
    if s.get("phase") == "complete":
        return False
    
    # Disable if not in answer phase
    if s.get("phase") not in ("awaiting_main_answer", "awaiting_followup_answer"):
        return False
    
    # Check timer state
    q_time = s.get("current", {}).get("q_time")
    if not q_time:
        # Timer not set or cleared - disable mic
        return False
    
    # DETERMINISTIC: Use time_provider instead of time.time() (Principle #5)
    time_provider = get_default_time_provider()
    elapsed = time_provider.time() - q_time
    
    # If elapsed < 0, audio is still playing - disable mic
    if elapsed < 0:
        return False
    
    # Timer has started (elapsed >= 0) - check if expired
    max_timeout = get_max_answer_timeout_sec(s)
    remaining = max_timeout - elapsed
    
    # Disable if timer expired
    if remaining <= 0:
        return False
    
    # Timer is active and not expired - enable mic
    return True


def _calculate_progress(
    s: Dict[str, Any],
    gr_module,  # Gradio module passed as dependency
    MAX_ANSWER_TIMEOUT_SEC: int,
    get_n_questions_fn: Optional[Callable] = None,
    get_followups_max_fn: Optional[Callable] = None,
):
    """
    Calculate progress metrics for real-time display.
    
    Args:
        s: State dictionary
        gr_module: Gradio module (passed as dependency for version compatibility)
        MAX_ANSWER_TIMEOUT_SEC: Maximum answer timeout in seconds
        get_n_questions_fn: Optional function to get number of questions
        get_followups_max_fn: Optional function to get max followups
        
    Returns:
        Gradio update object with progress display
    """
    s = ensure_state(s)
    
    # Get exam configuration
    if get_n_questions_fn:
        num_questions = s.get("limit", get_n_questions_fn())
    else:
        num_questions = s.get("limit", get_n_questions())
    
    if get_followups_max_fn:
        followups_max = s.get("followups_max", get_followups_max_fn())
    else:
        followups_max = s.get("followups_max", get_followups_max())
    
    questions_completed = s.get("asked_main", 0)
    
    # Calculate max duration dynamically based on exam configuration
    # Formula: (timeout + 30s process + 10s speak) * (N_QUESTIONS + FOLLOWUPS_MAX)
    max_duration_sec = (MAX_ANSWER_TIMEOUT_SEC + PROCESSING_BUFFER_SEC + SESSION_BUFFER_SEC) * (num_questions + (num_questions * followups_max))
    
    # Calculate time metrics
    # DETERMINISTIC: Use time_provider instead of time.time() (Principle #5)
    session_start = s.get("session_start_time", 0)
    if session_start:
        time_provider = get_default_time_provider()
        time_elapsed = time_provider.time() - session_start
        time_remaining = max_duration_sec - time_elapsed
        
        # Format time
        elapsed_min = int(time_elapsed // 60)
        elapsed_sec = int(time_elapsed % 60)
        
        # Handle negative time_remaining (session exceeded)
        if time_remaining <= 0:
            remaining_min = 0
            remaining_sec = 0
        else:
            remaining_min = int(time_remaining // 60)
            remaining_sec = int(time_remaining % 60)
        
        time_elapsed_str = f"{elapsed_min}m {elapsed_sec}s"
        time_remaining_str = f"{remaining_min}m {remaining_sec}s"
    else:
        # Session hasn't started - show full duration in consistent format
        total_min = int(max_duration_sec // 60)
        total_sec = int(max_duration_sec % 60)
        time_elapsed_str = "0m 0s"
        time_remaining_str = f"{total_min}m {total_sec}s"
    
    # Calculate progress percentage
    if num_questions > 0:
        progress_pct = int((questions_completed / num_questions) * 100)
    else:
        progress_pct = 0
    
    # Create progress display
    # Show progress when exam has started (not just when answering)
    exam_started = s.get("exam_started", False)
    if s.get("phase") == "complete" or (not exam_started and s.get("phase") in ("idle", "armed")):
        return gr_module.update(value="", visible=False)
    
    # Check if processing is happening (by checking last history message)
    processing_status = ""
    history = s.get("history", [])
    if history:
        last_msg = history[-1].get("content", "")
        if PROCESSING_AUDIO_RESPONSE_MSG in last_msg:
            processing_status = UI_STATUS_GENERATING_QUESTION
        elif PROCESSING_AUDIO_MSG in last_msg:
            processing_status = UI_STATUS_PROCESSING_AUDIO
    
    # Get chunk information if available
    chunk_index = s.get("current", {}).get("chunk_index")
    total_chunks = s.get("current", {}).get("total_chunks")
    chunk_info = ""
    if chunk_index and total_chunks:
        chunk_info = f"Chunk: {chunk_index}/{total_chunks}"
    
    # Build compact progress text (remove redundant labels)
    progress_parts = [
        f"📊 {questions_completed}/{num_questions} ({progress_pct}%)",
        f"⏳ {time_remaining_str}"
    ]
    
    # Add processing status if active
    if processing_status:
        progress_parts.insert(0, processing_status)
    
    # Add chunk info if available
    if chunk_info:
        progress_parts.append(chunk_info)
    
    # Use compact separator (double space instead of |)
    progress_text = "  ".join(progress_parts)

    return gr_module.update(value=progress_text, visible=True)


def _calculate_processing_status(s: Dict[str, Any], gr_module):  # Gradio module passed as dependency
    """
    Extract processing status from history for unified_status display with loading animation.
    Also shows termination messages when exam is complete.
    
    Args:
        s: State dictionary
        gr_module: Gradio module (passed as dependency for version compatibility)
        
    Returns:
        Gradio update object with processing status HTML or termination message
    """
    s = ensure_state(s)
    
    # Check if exam is complete - show termination message prominently
    if s.get("phase") == "complete":
        history = s.get("history", [])
        
        # Check if this is normal completion (no violations) vs termination (violations)
        flags = s.get("flags", [])
        has_violations = any(
            flag in flags for flag in [
                "PROFANITY_DETECTED", "VOICEPRINT_MISMATCH", "MULTI_FACE",
                "TAB_BLUR_THRESHOLD_EXCEEDED", "CLIPBOARD_PASTE_THRESHOLD_EXCEEDED",
                "CLIPBOARD_COPY_THRESHOLD_EXCEEDED", "ANSWER_REUSE_DETECTED"
            ]
        )
        
        # Look for termination messages in recent history
        termination_keywords = TERMINATION_KEYWORDS
        
        # Check last few messages for termination reason
        has_termination_keywords = False
        termination_content = ""
        for msg in reversed(history[-5:]):  # Check last 5 messages
            content = msg.get("content", "")
            if any(keyword in content for keyword in termination_keywords):
                has_termination_keywords = True
                termination_content = content
                break
        
        # If normal completion (no violations, no termination keywords)
        if not has_violations and not has_termination_keywords:
            # Normal completion - show success message
            html_content = f"""
            <div style="background-color: #e8f5e9; border-left: 4px solid #4CAF50; padding: 12px; margin: 8px 0; border-radius: 4px;">
                <div style="color: #2e7d32; font-weight: bold; font-size: 14px;">{STATUS_EXAM_COMPLETED}</div>
                <div style="color: #424242; font-size: 13px;">{INFO_CHECK_CHAT_HISTORY}</div>
            </div>
            """
            return gr_module.update(value=html_content, visible=True)
        
        # Violation-based termination - show termination message
        if termination_content:
            # Found termination message - display it prominently
            clean_content = termination_content.replace('**', '').replace('❌', '').replace('⚠️', '').strip()
            html_content = f"""
            <div style="background-color: #ffebee; border-left: 4px solid #f44336; padding: 12px; margin: 8px 0; border-radius: 4px;">
                <div style="color: #c62828; font-weight: bold; font-size: 14px; margin-bottom: 4px;">{STATUS_EXAM_TERMINATED}</div>
                <div style="color: #424242; font-size: 13px;">{clean_content}</div>
            </div>
            """
            return gr_module.update(value=html_content, visible=True)
        
        # Fallback: Generic termination message if no specific message found
        html_content = f"""
        <div style="background-color: #ffebee; border-left: 4px solid #f44336; padding: 12px; margin: 8px 0; border-radius: 4px;">
            <div style="color: #c62828; font-weight: bold; font-size: 14px;">{STATUS_EXAM_TERMINATED}</div>
            <div style="color: #424242; font-size: 13px;">{INFO_CHECK_CHAT_HISTORY}</div>
        </div>
        """
        return gr_module.update(value=html_content, visible=True)
    
    # Check if processing is happening (by checking last history message)
    processing_status = ""
    history = s.get("history", [])
    if history:
        last_msg = history[-1].get("content", "")
        if PROCESSING_AUDIO_RESPONSE_MSG in last_msg:
            processing_status = UI_STATUS_GENERATING_QUESTION
        elif PROCESSING_FOLLOWUP_MSG in last_msg:
            processing_status = UI_STATUS_ASKING_FOLLOWUP
        elif PROCESSING_ASSESSMENT_MSG in last_msg:
            processing_status = UI_STATUS_GENERATING_ASSESSMENT
        elif PROCESSING_AUDIO_MSG in last_msg:
            processing_status = UI_STATUS_PROCESSING_AUDIO
    
    # Return HTML with loading animation only (no text) if processing, otherwise empty/hidden
    if processing_status:
        # HTML with CSS animation for loading bar (no text, just animation)
        html_content = """
        <div style="position: relative; width: 100%; height: 4px; background: #f0f0f0; border-radius: 2px; overflow: hidden;">
            <div style="position: absolute; bottom: 0; left: 0; right: 0; height: 100%; background: linear-gradient(90deg, transparent, #4CAF50, transparent); background-size: 200% 100%; animation: wave 1.5s linear infinite;"></div>
        </div>
        <style>
            @keyframes wave {
                0% { background-position: -200% 0; }
                100% { background-position: 200% 0; }
            }
        </style>
        """
        return gr_module.update(value=html_content, visible=True)
    else:
        return gr_module.update(value="", visible=False)


def _calculate_connection_status(s: Dict[str, Any], gr_module):  # Gradio module passed as dependency
    """
    Calculate connection status for real-time display.
    
    Phase 2.2.3: Enhanced to show cleaner connection status (queue info moved to separate indicator).
    
    Args:
        s: State dictionary
        gr_module: Gradio module (passed as dependency for version compatibility)
        
    Returns:
        Gradio update object with connection status
    """
    s = ensure_state(s)
    network_status = s.get("network_status", "online")
    
    if network_status == "online":
        return gr_module.update(value="🌐 **Online**", visible=True)
    elif network_status == "offline":
        return gr_module.update(value="📴 **Offline**", visible=True)
    else:  # checking
        return gr_module.update(value="🔄 **Checking connection...**", visible=True)


def _calculate_queue_status(s: Dict[str, Any], gr_module):  # Gradio module passed as dependency
    """
    Calculate queue status for real-time display.
    
    Phase 2.2.3: Queue status indicator showing queued answers count.
    
    Args:
        s: State dictionary
        gr_module: Gradio module (passed as dependency for version compatibility)
        
    Returns:
        Gradio update object with queue status
    """
    s = ensure_state(s)
    queue_info = get_queue_status(s)
    
    queued_count = queue_info.get("queued_count", 0)
    network_status = queue_info.get("network_status", "online")
    
    if queued_count > 0:
        if network_status == "offline":
            return gr_module.update(value=f"📬 **{queued_count} queued** (offline)", visible=True)
        else:
            return gr_module.update(value=f"📬 **{queued_count} queued**", visible=True)
    else:
        # Hide queue status when no items queued
        return gr_module.update(value="", visible=False)


def _stream_proctor(
    frame: Any,
    sdict: Dict[str, Any],
    gr_module,  # Gradio module passed as dependency
    dependencies: Dict[str, Any],
) -> tuple:
    """
    Stream handler for proctor webcam.
    
    Args:
        frame: Webcam frame
        sdict: State dictionary
        gr_module: Gradio module (passed as dependency for version compatibility)
        dependencies: Dictionary with dependencies:
            - MAX_SESSION_DURATION_SEC: Maximum session duration
            - _HAS_PROCTOR: Whether proctor is available
            - mp: MediaPipe instance
            - _proctor_end_updates: Function to get proctor end updates
            - _calculate_timeout_status: Function to calculate timeout status
            - _calculate_progress: Function to calculate progress
            - _calculate_connection_status: Function to calculate connection status
            - _calculate_processing_status: Function to calculate processing status
            - _calculate_queue_status: Function to calculate queue status
            - handle_start_exam: Function to handle exam start
            
    Returns:
        Tuple of state and Gradio update objects
    """
    from exam.file_utils import _paths_for_session
    
    sdict = ensure_state(sdict)
    
    # Extract handle_start_exam early for logging
    handle_start_exam = dependencies.get("handle_start_exam")
    webcam_enabled = sdict.get("webcam_enabled", False)
    exam_started = sdict.get("exam_started", False)
    
    # Print for Railway visibility - confirm function is being called
    # Commented out for clarity - too verbose
    # if webcam_enabled:
    #     print(f"[STREAM_PROCTOR] Called: webcam_enabled={webcam_enabled}, has_handler={handle_start_exam is not None}, frame={'present' if frame is not None else 'None'}", flush=True)
    
    # Extract dependencies
    MAX_SESSION_DURATION_SEC = dependencies.get("MAX_SESSION_DURATION_SEC")
    _HAS_PROCTOR = dependencies.get("_HAS_PROCTOR", False)
    mp = dependencies.get("mp")
    _proctor_end_updates = dependencies.get("_proctor_end_updates")
    
    # Extract dependencies used in _calculate_progress calls (DRY: extract once, use many times)
    MAX_ANSWER_TIMEOUT_SEC = dependencies.get("MAX_ANSWER_TIMEOUT_SEC", 60)
    get_n_questions_fn = dependencies.get("get_n_questions", get_n_questions)
    get_followups_max_fn = dependencies.get("get_followups_max", get_followups_max)
    get_max_answer_timeout_sec_fn = dependencies.get("get_max_answer_timeout_sec", get_max_answer_timeout_sec)
    
    # Create wrapper functions that include gr_module
    def _calculate_timeout_status_wrapper(s, get_max_answer_timeout_sec_fn_param=None):
        # Use parameter if provided, otherwise use extracted function
        timeout_fn = get_max_answer_timeout_sec_fn_param if get_max_answer_timeout_sec_fn_param is not None else get_max_answer_timeout_sec_fn
        return _calculate_timeout_status(s, gr_module, timeout_fn)
    def _calculate_progress_wrapper(s, MAX_ANSWER_TIMEOUT_SEC_param, get_n_questions_fn_param=None, get_followups_max_fn_param=None):
        # Use parameters if provided, otherwise use extracted functions
        n_questions_fn = get_n_questions_fn_param if get_n_questions_fn_param is not None else get_n_questions_fn
        followups_max_fn = get_followups_max_fn_param if get_followups_max_fn_param is not None else get_followups_max_fn
        return _calculate_progress(s, gr_module, MAX_ANSWER_TIMEOUT_SEC_param, n_questions_fn, followups_max_fn)
    def _calculate_connection_status_wrapper(s):
        return _calculate_connection_status(s, gr_module)
    def _calculate_processing_status_wrapper(s):
        return _calculate_processing_status(s, gr_module)
    def _calculate_queue_status_wrapper(s):
        return _calculate_queue_status(s, gr_module)
    
    _calculate_timeout_status_fn = dependencies.get("_calculate_timeout_status", _calculate_timeout_status_wrapper)
    _calculate_progress_fn = dependencies.get("_calculate_progress", _calculate_progress_wrapper)
    _calculate_connection_status_fn = dependencies.get("_calculate_connection_status", _calculate_connection_status_wrapper)
    _calculate_processing_status_fn = dependencies.get("_calculate_processing_status", _calculate_processing_status_wrapper)
    _calculate_queue_status_fn = dependencies.get("_calculate_queue_status", _calculate_queue_status_wrapper)
    # handle_start_exam already extracted above for early logging
    
    # GUARDRAIL: Session Timeout Check (maximum total exam duration)
    # DETERMINISTIC: Use time_provider instead of time.time() (Principle #5)
    session_start = sdict.get("session_start_time", 0)
    if session_start and MAX_SESSION_DURATION_SEC:
        time_provider = get_default_time_provider()
        session_elapsed = time_provider.time() - session_start
        if session_elapsed > MAX_SESSION_DURATION_SEC:
            sdict.setdefault("flags", []).append("SESSION_TIMEOUT")
            sdict["phase"] = "complete"
            save_state_to_disk(sdict)
            # Clear auto-saved state to prevent resume
            try:
                p = _paths_for_session(sdict)
                if os.path.exists(p["STATE_PATH"]):
                    os.remove(p["STATE_PATH"])
            except Exception:
                pass
            # Get proctor end updates
            proctor_cam_upd, proctor_status_upd = _proctor_end_updates(sdict, gr_module)
            # Calculate connection and progress updates
            connection_upd = _calculate_connection_status_fn(sdict, gr_module)
            progress_upd = _calculate_progress_fn(sdict, gr_module, MAX_ANSWER_TIMEOUT_SEC, get_n_questions_fn, get_followups_max_fn)
            # Add termination message to chat history (only if not already added)
            timeout_message = "⚠️ **Session timeout:** Maximum exam duration exceeded. Exam session ended."
            history = sdict.get("history", [])
            # Check if message already exists in history to prevent duplicates
            message_exists = any(
                isinstance(msg, dict) and msg.get("content") == timeout_message
                for msg in history
            )
            if not message_exists:
                sdict.setdefault("history", []).append({
                    "role": "assistant",
                    "content": timeout_message
                })
            # Return with exam terminated
            timeout_upd = _calculate_timeout_status_fn(sdict)
            # Return tuple: (state, proctor_cam, proctor_status, connection_status, chatbot, mic, examiner_audio, progress_info, timeout_countdown, unified_status)
            # Note: examiner_audio expects None or audio file path, not chat history
            # Preserve existing audio (session timeout doesn't need new audio)
            last_audio = sdict.get("current", {}).get("last_examiner_audio")
            audio_update = gr_module.update(value=last_audio) if last_audio else gr_module.update()
            queue_upd = _calculate_queue_status_fn(sdict, gr_module)
            return sdict, proctor_cam_upd, proctor_status_upd, connection_upd, gr_module.update(value=sdict.get("history", [])), gr_module.update(), audio_update, progress_upd, timeout_upd, _calculate_processing_status_fn(sdict, gr_module), queue_upd
    
    # GUARDRAIL: Per-Question Timeout Check (automatic termination when time expires)
    # DETERMINISTIC: Use time_provider instead of time.time() (Principle #5)
    q_time = sdict.get("current", {}).get("q_time")
    if q_time and sdict.get("phase") not in ("complete", "idle", "armed"):
        time_provider = get_default_time_provider()
        elapsed = time_provider.time() - q_time
        max_timeout = get_max_answer_timeout_sec_fn(sdict)  # Pass state to get value from state dict if context var unavailable
        if elapsed >= max_timeout:
            # Timeout expired - terminate exam automatically
            sdict.setdefault("flags", []).append("ANSWER_TIMEOUT")
            sdict["phase"] = "complete"
            save_state_to_disk(sdict)
            # Clear auto-saved state to prevent resume
            try:
                p = _paths_for_session(sdict)
                if os.path.exists(p["STATE_PATH"]):
                    os.remove(p["STATE_PATH"])
            except Exception:
                pass
            # Get proctor end updates
            proctor_cam_upd, proctor_status_upd = _proctor_end_updates(sdict, gr_module)
            # Calculate connection and progress updates
            connection_upd = _calculate_connection_status_fn(sdict, gr_module)
            progress_upd = _calculate_progress_fn(sdict, gr_module, MAX_ANSWER_TIMEOUT_SEC, get_n_questions_fn, get_followups_max_fn)
            timeout_upd = _calculate_timeout_status_fn(sdict)
            # Add timeout message to history
            sdict.setdefault("history", []).append({
                "role": "assistant",
                "content": TIMEOUT_ERROR_MESSAGE
            })
            # Return tuple: (state, proctor_cam, proctor_status, connection_status, chatbot, mic, examiner_audio, progress_info, timeout_countdown, unified_status)
            # Note: examiner_audio expects None or audio file path, not chat history
            # Preserve existing audio (per-question timeout doesn't need new audio)
            last_audio = sdict.get("current", {}).get("last_examiner_audio")
            audio_update = gr_module.update(value=last_audio) if last_audio else gr_module.update()
            queue_upd = _calculate_queue_status_fn(sdict, gr_module)
            return sdict, proctor_cam_upd, proctor_status_upd, connection_upd, gr_module.update(value=sdict.get("history", [])), gr_module.update(), audio_update, progress_upd, timeout_upd, _calculate_processing_status_fn(sdict, gr_module), queue_upd
    
    # Auto-save state every 30 seconds (for audit trail only)
    auto_save_state(sdict)
    
    # Update network status periodically
    network_status = update_network_status(sdict)
    connection_upd = _calculate_connection_status_fn(sdict, gr_module)
    
    # Only process frames if webcam is enabled
    if not sdict.get("webcam_enabled", False):
        progress_upd = _calculate_progress_fn(sdict, gr_module, MAX_ANSWER_TIMEOUT_SEC, get_n_questions_fn, get_followups_max_fn)
        timeout_upd = _calculate_timeout_status_fn(sdict)
        queue_upd = _calculate_queue_status_fn(sdict, gr_module)
        return sdict, gr_module.update(), gr_module.update(value="💤 Inactive"), connection_upd, gr_module.update(), gr_module.update(), gr_module.update(), progress_upd, timeout_upd, _calculate_processing_status_fn(sdict, gr_module), queue_upd
    
    # Initialize proctor state if needed
    if sdict.get("proctor_state") is None:
        sdict["proctor_state"] = ProctorState()
    st = sdict["proctor_state"]
    
    # Start proctor if not started
    if not st.enabled and _HAS_PROCTOR:
        st.start(_HAS_PROCTOR, mp)
    
    # OBSERVABILITY: Log MediaPipe availability for troubleshooting (Principle #13)
    if not _HAS_PROCTOR:
        logger.warning(
            "mediapipe_availability_check",
            session_id=sdict.get("session_id", "unknown"),
            has_proctor=_HAS_PROCTOR,
            mediapipe_present=mp is not None,
            message="MediaPipe not available - using basic frame counting"
        )
    
    # Handle case where frame hasn't arrived yet
    if frame is None:
        progress_upd = _calculate_progress_fn(sdict, gr_module, MAX_ANSWER_TIMEOUT_SEC, get_n_questions_fn, get_followups_max_fn)
        connection_upd = _calculate_connection_status_fn(sdict, gr_module)
        if _HAS_PROCTOR:
            timeout_upd = _calculate_timeout_status_fn(sdict)
            queue_upd = _calculate_queue_status_fn(sdict, gr_module)
            return sdict, gr_module.update(), gr_module.update(value="🎥 Active (local only) - Waiting for frame..."), connection_upd, gr_module.update(), gr_module.update(), gr_module.update(), progress_upd, timeout_upd, _calculate_processing_status_fn(sdict, gr_module), queue_upd
        else:
            # FIX: Show basic stats even without MediaPipe
            timeout_upd = _calculate_timeout_status_fn(sdict)
            queue_upd = _calculate_queue_status_fn(sdict, gr_module)
            return sdict, gr_module.update(), gr_module.update(value="💤 Inactive - No frame"), connection_upd, gr_module.update(), gr_module.update(), gr_module.update(), progress_upd, timeout_upd, _calculate_processing_status_fn(sdict, gr_module), queue_upd
    
    # FIX: If MediaPipe unavailable, use manual frame counting for basic stats
    if not _HAS_PROCTOR:
        # Use manual frame counting for basic stats
        if "manual_frame_count" not in sdict:
            sdict["manual_frame_count"] = 0
        sdict["manual_frame_count"] += 1
        frames = sdict["manual_frame_count"]
        
        # Build basic status without MediaPipe
        status_parts = ["🎥"]
        status_parts.append(f"{frames}f")
        if sdict.get("exam_started", False):
            status_parts.append("✅ Active")
        else:
            status_parts.append("⏳ Waiting")
        
        proctor_status_text = "  ".join(status_parts)
        # Continue with normal flow - update connection status, progress, etc.
        connection_upd = _calculate_connection_status_fn(sdict, gr_module)
        progress_upd = _calculate_progress_fn(sdict, gr_module, MAX_ANSWER_TIMEOUT_SEC, get_n_questions_fn, get_followups_max_fn)
        timeout_upd = _calculate_timeout_status_fn(sdict)
        queue_upd = _calculate_queue_status_fn(sdict, gr_module)
        
        # Return with basic stats displayed
        return sdict, gr_module.update(), gr_module.update(value=proctor_status_text), connection_upd, gr_module.update(value=sdict.get("history", [])), gr_module.update(), gr_module.update(), progress_upd, timeout_upd, _calculate_processing_status_fn(sdict, gr_module), queue_upd
    
    # Analyze frame
    st.answering = sdict.get("phase") in ("awaiting_main_answer", "awaiting_followup_answer")
    summary, _ = proctor_analyze_frame(frame, st, _HAS_PROCTOR)
    sdict["proctor_summary"] = summary
    
    # Check for critical violations (MULTI_FACE) - immediate termination
    if sdict.get("phase") not in ("complete", "idle", "armed"):
        from exam.file_utils import _paths_for_session
        flag_counts = getattr(st, "flag_counts", {})
        if flag_counts.get("MULTI_FACE", 0) > 0 and "MULTI_FACE" not in sdict.get("flags", []):
            # Critical violation - immediate termination
            from exam.config import CRITICAL_VIOLATIONS
            sdict.setdefault("flags", []).append("MULTI_FACE")
            sdict["phase"] = "complete"
            save_state_to_disk(sdict)
            # Clear auto-saved state to prevent resume
            try:
                p = _paths_for_session(sdict)
                if os.path.exists(p["STATE_PATH"]):
                    os.remove(p["STATE_PATH"])
            except Exception:
                pass
            
            # Get proctor end updates
            proctor_cam_upd, proctor_status_upd = _proctor_end_updates(sdict, gr_module)
            connection_upd = _calculate_connection_status_fn(sdict, gr_module)
            progress_upd = _calculate_progress_fn(sdict, gr_module, MAX_ANSWER_TIMEOUT_SEC, get_n_questions_fn, get_followups_max_fn)
            timeout_upd = _calculate_timeout_status_fn(sdict)
            
            # Add termination message to chat history
            termination_msg = format_termination_message("MULTI_FACE")
            sdict.setdefault("history", []).append({
                "role": "assistant",
                "content": termination_msg
            })
            
            # Return tuple: (state, proctor_cam, proctor_status, connection_status, chatbot, mic, examiner_audio, progress_info, timeout_countdown, unified_status)
            # Note: examiner_audio expects None or audio file path, not chat history
            # Preserve existing audio (error case doesn't need new audio)
            last_audio = sdict.get("current", {}).get("last_examiner_audio")
            audio_update = gr_module.update(value=last_audio) if last_audio else gr_module.update()
            queue_upd = _calculate_queue_status_fn(sdict, gr_module)
            return sdict, proctor_cam_upd, proctor_status_upd, connection_upd, gr_module.update(value=sdict.get("history", [])), gr_module.update(), audio_update, progress_upd, timeout_upd, _calculate_processing_status_fn(sdict, gr_module), queue_upd
    
    # Create status text with stats
    status = summary.get("status", "unknown")
    frames = summary.get("frames", 0)
    face_ratio = summary.get("face_present_ratio", 0.0)
    away_ratio = summary.get("away_ratio", 0.0)
    multi_ratio = summary.get("multi_face_ratio", 0.0)
    avg_yaw = summary.get("avg_yaw_deg", 0.0)
    avg_pitch = summary.get("avg_pitch_deg", 0.0)
    
    # Real-time feedback warnings (non-blocking)
    # DETERMINISTIC: Use time_provider instead of time.time() (Principle #5)
    feedback_warnings = []
    time_provider = get_default_time_provider()
    current_time = time_provider.time()
    
    # Check if looking away and show warning
    if st.answering and away_ratio > 0.1:  # If away ratio > 10%
        # Only show warning if not shown recently (avoid spam)
        if (st.last_feedback_warning != "away" or 
            st.feedback_warning_time is None or 
            current_time - st.feedback_warning_time > 2.0):  # Show every 2 seconds max
            feedback_warnings.append("⚠️ Looking away detected")
            st.last_feedback_warning = "away"
            st.feedback_warning_time = current_time
    
    # Check if multiple faces detected
    if st.answering and multi_ratio > 0.02:  # If multi-face ratio > 2%
        if (st.last_feedback_warning != "multi" or 
            st.feedback_warning_time is None or 
            current_time - st.feedback_warning_time > 2.0):
            feedback_warnings.append("⚠️ Multiple faces detected")
            st.last_feedback_warning = "multi"
            st.feedback_warning_time = current_time
    
    # Check break duration
    if st.answering and st.break_duration > 0:
        allow_break_duration = PROCTOR_CONFIG.get("allow_break_duration", 5)
        if st.break_duration > allow_break_duration:
            if (st.last_feedback_warning != "break" or 
                st.feedback_warning_time is None or 
                current_time - st.feedback_warning_time > 2.0):
                feedback_warnings.append(f"⚠️ Break duration: {int(st.break_duration)}s")
                st.last_feedback_warning = "break"
                st.feedback_warning_time = current_time
    
    # Build compact status text with icons (cleaner, more compact)
    status_parts = []
    
    # Add status icon
    if status == "present":
        status_parts.append("✅")
    elif status == "present_away":
        status_parts.append("⚠️")
    else:
        status_parts.append("💤")
    
    # Add face detection (only if significant)
    if face_ratio > 0.9:
        status_parts.append(f"✅ {face_ratio*100:.0f}%")
    elif face_ratio > 0.5:
        status_parts.append(f"⚠️ {face_ratio*100:.0f}%")
    
    # Add away detection (only if significant)
    if away_ratio > 0.1:
        status_parts.append(f"⚠️ {away_ratio*100:.0f}%")
    
    # Add multi-face (only if detected)
    if multi_ratio > 0.02:
        status_parts.append(f"👥 {multi_ratio*100:.0f}%")
    
    # Add gaze (only if significant deviation)
    if abs(avg_yaw) > 5 or abs(avg_pitch) > 5:
        status_parts.append(f"📐 {avg_yaw:.0f}°/{avg_pitch:.0f}°")
    
    # Add frames count (compact)
    if frames > 0:
        status_parts.append(f"{frames}f")
    
    # Add feedback warnings if any
    if feedback_warnings:
        status_parts.insert(1, " | ".join(feedback_warnings))
    
    # Use compact separator (double space instead of |)
    proctor_status_text = "  ".join(status_parts) if status_parts else "💤 Inactive"
    
    # FIX: If MediaPipe unavailable but we have manual frame count, show basic stats
    if not _HAS_PROCTOR and not status_parts and frame is not None:
        manual_frames = sdict.get("manual_frame_count", 0)
        if manual_frames > 0:
            proctor_status_text = f"🎥 {manual_frames}f  ⏳ Basic mode (MediaPipe unavailable)"
    
    # Auto-trigger exam when webcam stats are available and exam hasn't started
    # Note: webcam_enabled and exam_started already extracted at the top of the function
    has_handle_start_exam = handle_start_exam is not None
    is_callable = callable(handle_start_exam) if handle_start_exam else False
    
    # IMPORTANT: If MediaPipe is not available, manually count frames for exam start detection
    # This allows the exam to start on Railway even if MediaPipe is not installed
    if not _HAS_PROCTOR and frame is not None and webcam_enabled:
        # Manually track frame count for exam start detection
        if "manual_frame_count" not in sdict:
            sdict["manual_frame_count"] = 0
        sdict["manual_frame_count"] += 1
        # Use manual count if MediaPipe frames are 0
        if frames == 0:
            frames = sdict["manual_frame_count"]
            # Commented out for clarity - too verbose
            # print(f"[MANUAL_FRAME_COUNT] MediaPipe unavailable, using manual count: {frames}", flush=True)
    
    # Re-check exam_started after manual frame counting (in case state changed)
    exam_started = sdict.get("exam_started", False)
    
    # Debug logging for Railway deployment issues (print for Railway visibility)
    if webcam_enabled and not exam_started:
        log_msg = f"[EXAM_START_CHECK] webcam={webcam_enabled}, exam_started={exam_started}, frames={frames}, _HAS_PROCTOR={_HAS_PROCTOR}, has_handler={has_handle_start_exam}, callable={is_callable}"
        print(log_msg, flush=True)  # Print for Railway visibility (flush ensures immediate output)
        logger.info(
            "webcam_exam_start_check",
            session_id=sdict.get("session_id", "unknown"),
            webcam_enabled=webcam_enabled,
            exam_started=exam_started,
            frames=frames,
            _HAS_PROCTOR=_HAS_PROCTOR,
            has_handle_start_exam=has_handle_start_exam,
            is_callable=is_callable,
            handle_start_exam_type=type(handle_start_exam).__name__ if handle_start_exam else None,
            message=log_msg
        )
    
    if (webcam_enabled and 
        not exam_started and 
        frames > 0 and 
        handle_start_exam and 
        is_callable):  # Webcam active with frames detected
        log_msg = f"[EXAM_AUTO_START] Starting exam: frames={frames}, handler available"
        print(log_msg, flush=True)  # Print for Railway visibility
        logger.info(
            "auto_starting_exam",
            session_id=sdict.get("session_id", "unknown"),
            frames=frames,
            message=log_msg
        )
        sdict["exam_started"] = True
        # Trigger exam start
        # handle_start_exam may be a wrapper (accepts 1 arg) or raw handler (accepts 3 args)
        # Check function signature to determine how to call it
        import inspect
        try:
            sig = inspect.signature(handle_start_exam)
            param_count = len(sig.parameters)
            logger.debug(
                "handle_start_exam_signature",
                session_id=sdict.get("session_id", "unknown"),
                param_count=param_count,
                message=f"handle_start_exam signature check: {param_count} parameters"
            )
            if param_count == 1:
                # Wrapper function - call with just state
                logger.debug(
                    "calling_handle_start_exam_wrapper",
                    session_id=sdict.get("session_id", "unknown"),
                    message="Calling handle_start_exam as wrapper (1 parameter)"
                )
                s_result, cam_upd, cam_status_upd, chatbot_update, mic_update, audio = handle_start_exam(sdict)
            else:
                # Raw handler - call with all parameters
                logger.debug(
                    "calling_handle_start_exam_raw",
                    session_id=sdict.get("session_id", "unknown"),
                    message="Calling handle_start_exam as raw handler (3 parameters)"
                )
                s_result, cam_upd, cam_status_upd, chatbot_update, mic_update, audio = handle_start_exam(sdict, gr_module, dependencies)
        except (TypeError, ValueError) as sig_error:
            # Fallback: try wrapper first, then raw handler
            logger.warning(
                "handle_start_exam_signature_error",
                session_id=sdict.get("session_id", "unknown"),
                error_type=type(sig_error).__name__,
                error_message=str(sig_error)[:200],
                message="Signature check failed, trying fallback approach"
            )
            try:
                logger.debug(
                    "calling_handle_start_exam_fallback_wrapper",
                    session_id=sdict.get("session_id", "unknown"),
                    message="Fallback: calling handle_start_exam as wrapper"
                )
                s_result, cam_upd, cam_status_upd, chatbot_update, mic_update, audio = handle_start_exam(sdict)
            except TypeError:
                logger.debug(
                    "calling_handle_start_exam_fallback_raw",
                    session_id=sdict.get("session_id", "unknown"),
                    message="Fallback: calling handle_start_exam as raw handler"
                )
                s_result, cam_upd, cam_status_upd, chatbot_update, mic_update, audio = handle_start_exam(sdict, gr_module, dependencies)
        except Exception as start_exam_error:
            # Log any other exceptions during exam start
            logger.error(
                "handle_start_exam_failed",
                session_id=sdict.get("session_id", "unknown"),
                error_type=type(start_exam_error).__name__,
                error_message=str(start_exam_error)[:500],
                message=f"handle_start_exam failed: {type(start_exam_error).__name__}: {str(start_exam_error)[:500]}"
            )
            # Re-raise to be handled by outer exception handler
            raise
        progress_upd = _calculate_progress_fn(s_result, gr_module, MAX_ANSWER_TIMEOUT_SEC, get_n_questions_fn, get_followups_max_fn)
        connection_upd = _calculate_connection_status_fn(s_result, gr_module)
        timeout_upd = _calculate_timeout_status_fn(s_result)
        # Extract status message from state (stored by handle_start_exam)
        status_value = s_result.get("current", {}).get("last_status_message", "")
        if not status_value:
            # Fallback: default message if not found
            status_value = STATUS_QUESTION_ASKED
        # Store audio path in state so it persists across _stream_proctor calls
        if audio:
            s_result["current"]["last_examiner_audio"] = audio
        # Return audio wrapped in gr.update() to ensure proper Gradio handling
        audio_update = gr_module.update(value=audio) if audio else gr_module.update()
        queue_upd = _calculate_queue_status_fn(s_result, gr_module)
        logger.info(
            "exam_auto_started_successfully",
            session_id=sdict.get("session_id", "unknown"),
            has_audio=audio is not None,
            message="Exam auto-started successfully"
        )
        return s_result, cam_upd, cam_status_upd, connection_upd, chatbot_update, mic_update, audio_update, progress_upd, timeout_upd, _calculate_processing_status_fn(s_result, gr_module), queue_upd
    
    # Log why exam didn't start (for debugging Railway issues)
    if webcam_enabled and frames > 0 and not exam_started:
        reason = "missing_handler" if not has_handle_start_exam else ("not_callable" if not is_callable else "unknown")
        log_msg = f"[EXAM_NOT_STARTED] webcam={webcam_enabled}, exam_started={exam_started}, frames={frames}, has_handler={has_handle_start_exam}, callable={is_callable}, reason={reason}"
        print(log_msg, flush=True)  # Print for Railway visibility
        logger.warning(
            "exam_not_started_reason",
            session_id=sdict.get("session_id", "unknown"),
            webcam_enabled=webcam_enabled,
            exam_started=exam_started,
            frames=frames,
            has_handle_start_exam=has_handle_start_exam,
            is_callable=is_callable,
            reason=reason,
            message=log_msg
        )
    
    # Calculate progress info
    progress_upd = _calculate_progress_fn(sdict, gr_module, MAX_ANSWER_TIMEOUT_SEC, get_n_questions_fn, get_followups_max_fn)
    connection_upd = _calculate_connection_status_fn(sdict, gr_module)
    timeout_upd = _calculate_timeout_status_fn(sdict)
    
    # Update mic state based on timer - mic should only be enabled when timer countdown is active
    mic_interactive = _calculate_mic_interactive_state(sdict, gr_module)
    
    # Return tuple: (state, proctor_cam, proctor_status, connection_status, chatbot, mic, examiner_audio, progress_info, timeout_countdown, unified_status)
    # Preserve existing examiner audio if available, otherwise return None
    last_audio = sdict.get("current", {}).get("last_examiner_audio")
    audio_update = gr_module.update(value=last_audio) if last_audio else gr_module.update()
    queue_upd = _calculate_queue_status_fn(sdict, gr_module)
    return sdict, gr_module.update(), gr_module.update(value=proctor_status_text), connection_upd, gr_module.update(value=sdict.get("history", [])), gr_module.update(value=None, interactive=mic_interactive), audio_update, progress_upd, timeout_upd, _calculate_processing_status_fn(sdict, gr_module), queue_upd


def get_step_indicator_html(current_step: int, total_steps: int = 6) -> str:
    """
    Generate HTML for compact step indicator progress bar.
    
    Args:
        current_step: Current step number (1-6)
        total_steps: Total number of steps (default: 6)
        
    Returns:
        HTML string for step indicator with progress bar
        
    Example:
        Step 1: 16.67% width (Professor's Link)
        Step 2: 33.33% width (Verification)
        Step 3: 50% width (Consent)
        Step 4: 66.67% width (Student ID)
        Step 5: 83.33% width (Webcam Consent)
        Step 6: 100% width (Exam Active)
    """
    progress_percent = (current_step / total_steps) * 100
    step_text = f"Step {current_step}/{total_steps}"
    
    return f"""
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
        <div style="flex: 1; background: #e0e0e0; height: 8px; border-radius: 4px; overflow: hidden;">
            <div style="background: #4CAF50; height: 100%; width: {progress_percent:.2f}%; border-radius: 4px; transition: width 0.3s;"></div>
        </div>
        <span style="font-size: 12px; color: #666; white-space: nowrap;">{step_text}</span>
    </div>
    """


__all__ = [
    "_calculate_timeout_status",
    "_calculate_mic_interactive_state",
    "_calculate_progress",
    "_calculate_processing_status",
    "_calculate_connection_status",
    "_calculate_queue_status",
    "_stream_proctor",
    "get_step_indicator_html",
]

