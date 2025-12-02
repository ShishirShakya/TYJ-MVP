"""
UI event handlers for exam interface.

This module contains event handler functions for Gradio UI components:
- Professor link parsing
- Security event handling
- Consent and verification handlers
- Student ID verification
- Webcam consent handling
- Exam start handler
- Microphone recording wrapper
- File integrity checkbox handler
- Proctor end updates

Note: This module uses dependency injection for Gradio and business logic
functions to ensure compatibility across different environments.
"""

import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Callable, Optional, TYPE_CHECKING

# Type hints only - no runtime import
if TYPE_CHECKING:
    import gradio as gr

from exam.state import ensure_state
from exam.proctor import ProctorState
from shared.logging_config import get_logger
from shared.constants import (
    ERROR_PDF_VALIDATION_FAILED,
    ERROR_CANNOT_START_EXAM,
    ERROR_PDF_LOADING_FAILED,
    PDF_ERROR_SUFFIX_RELOAD,
    PDF_ERROR_SUFFIX_CHECK_URL,
    format_error_with_solution,
    PROCTOR_ENDED,
)
from exam.ui.helpers import (
    _calculate_timeout_status,
    _calculate_progress,
    _calculate_processing_status,
    _calculate_connection_status,
    get_step_indicator_html,
)

# OBSERVABILITY: Get logger for structured logging (Principle #13)
logger = get_logger()


def _proctor_end_updates(s: Dict[str, Any], gr_module) -> tuple:
    """
    Hide camera + end message when phase is complete.
    
    Args:
        s: State dictionary
        gr_module: Gradio module (passed as dependency for version compatibility)
        
    Returns:
        Tuple of (camera_update, status_update) Gradio update objects
    """
    if s.get("phase") == "complete":
        st = s.get("proctor_state")
        if isinstance(st, ProctorState):
            try:
                st.stop()
            except Exception:
                pass
        return gr_module.update(visible=False), gr_module.update(value=PROCTOR_ENDED)
    return gr_module.update(), gr_module.update()


def handle_security_event(
    event_type: str,
    current_state: Dict[str, Any],
    gr_module,
    log_security_event_fn: Callable,
) -> Dict[str, Any]:
    """
    Handle security events from JavaScript (tab blur, clipboard usage).
    
    Args:
        event_type: Type of security event (TAB_BLUR, TAB_FOCUS, CLIPBOARD_COPY, CLIPBOARD_PASTE)
        current_state: Current state dictionary
        gr_module: Gradio module (passed as dependency for version compatibility)
        log_security_event_fn: Function to log security events
        
    Returns:
        Updated state dictionary
    """
    current_state = ensure_state(current_state)
    
    # Log security event
    event_detail = {
        "source": "javascript",
        "timestamp": time.time()
    }
    current_state = log_security_event_fn(current_state, event_type, event_detail)
    
    # Update tab focus or clipboard events
    if event_type == "TAB_BLUR":
        current_state.setdefault("tab_focus_events", []).append({
            "ts_iso": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
            "type": "blur"
        })
    elif event_type == "TAB_FOCUS":
        current_state.setdefault("tab_focus_events", []).append({
            "ts_iso": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
            "type": "focus"
        })
    elif event_type in ("CLIPBOARD_COPY", "CLIPBOARD_PASTE"):
        current_state.setdefault("clipboard_events", []).append({
            "ts_iso": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
            "type": event_type
        })
    
    return current_state


def handle_parse_and_show_chatbot(
    url: str,
    current_state: Dict[str, Any],
    gr_module,
    dependencies: Dict[str, Any],
) -> tuple:
    """
    Handle parsing professor's link and showing chatbot with verification status.
    
    Args:
        url: Professor's link URL
        current_state: Current state dictionary
        gr_module: Gradio module (passed as dependency for version compatibility)
        dependencies: Dictionary with dependencies:
            - parse_professor_link_and_setup: Function to parse professor link
            - ensure_state: Function to ensure state
            - validate_chunks_available: Function to validate chunks
            - get_chunks: Function to get chunks
            - get_n_questions: Function to get number of questions
            - get_followups_max: Function to get max followups
            - get_max_answer_timeout_sec: Function to get max answer timeout
            
    Returns:
        Tuple of Gradio update objects
    """
    parse_professor_link_and_setup = dependencies.get("parse_professor_link_and_setup")
    ensure_state_fn = dependencies.get("ensure_state", ensure_state)
    validate_chunks_available = dependencies.get("validate_chunks_available")
    get_chunks = dependencies.get("get_chunks")
    get_n_questions = dependencies.get("get_n_questions")
    get_followups_max = dependencies.get("get_followups_max")
    get_max_answer_timeout_sec = dependencies.get("get_max_answer_timeout_sec")
    
    current_state = ensure_state_fn(current_state)
    success, status_msg, state_updates = parse_professor_link_and_setup(url)
    
    if success:
        for key, value in state_updates.items():
            current_state[key] = value
        current_state.update({
            "phase": "idle",
            "asked_main": 0,
            "history": [],
            "consent": False,
            "ready_for_question": False
        })
        
        course_id = state_updates.get("course_id", "UNKNOWN")
        exam_id = state_updates.get("exam_id", "UNKNOWN")
        section_id = state_updates.get("section_id", "UNKNOWN")
        
        # Calculate max duration dynamically based on parsed exam configuration
        num_questions = state_updates.get("limit", get_n_questions() if get_n_questions else 1)
        followups_max = state_updates.get("followups_max", get_followups_max() if get_followups_max else 1)
        # Get timeout from state_updates first, then fallback to function
        max_timeout = state_updates.get("time_per_question") if state_updates.get("time_per_question") else (get_max_answer_timeout_sec(current_state) if get_max_answer_timeout_sec else 60)
        max_duration_sec = (max_timeout + 30 + 10) * (num_questions + (num_questions * followups_max))
        max_duration_min = max_duration_sec / 60
        answer_timeout_min = max_timeout / 60
        
        # CHECK: Only validate if PDF was loaded successfully
        pdf_loaded = state_updates.get("pdf_loaded", False)
        chunks_validated = state_updates.get("chunks_validated", False)
        
        if not pdf_loaded or not chunks_validated:
            # PDF loading failed - show the actual download/loading error
            verification_text = (
                f"### **Course ID:** `{course_id}` | **Exam ID:** `{exam_id}` | **Section:** `{section_id}`\n\n"
                + f"**❌ {ERROR_PDF_LOADING_FAILED}**\n\n{status_msg}\n\n"
                + f"{PDF_ERROR_SUFFIX_CHECK_URL}"
            )
            
            # Update step in state
            current_state["current_step"] = "verification"
            
            return (
                current_state,
                current_state.get("history", []),  # chatbot - show error history
                "",  # professor_link_input - clear
                gr_module.update(interactive=False),  # parse_link_btn
                gr_module.update(visible=False),  # professor_link_section - hide previous
                gr_module.update(visible=True),  # verification_section - show it
                gr_module.update(value=verification_text),  # verification_status - show error
                gr_module.update(visible=False),  # consent_section - don't show
                gr_module.update(visible=False),  # student_id_section
                gr_module.update(visible=False),  # webcam_consent_section
                gr_module.update(visible=False),  # exam_layout - don't show
                gr_module.update(value=get_step_indicator_html(2))  # step_indicator
            )
        
        # PDF loaded successfully - validate chunks
        is_valid, error_msg, valid_count = validate_chunks_available()
        
        if not is_valid:
            # PDF loaded but validation failed
            verification_text = (
                f"### **Course ID:** `{course_id}` | **Exam ID:** `{exam_id}` | **Section:** `{section_id}`\n\n"
                f"**❌ PDF Validation Failed:** {error_msg}\n\n"
                f"Please reload the PDF from the Settings tab."
            )
            
            # Update step in state
            current_state["current_step"] = "verification"
            
            return (
                current_state,
                current_state.get("history", []),  # chatbot - show error history
                "",  # professor_link_input - clear
                gr_module.update(interactive=False),  # parse_link_btn
                gr_module.update(visible=False),  # professor_link_section - hide previous
                gr_module.update(visible=True),  # verification_section - show it
                gr_module.update(value=verification_text),  # verification_status - show error
                gr_module.update(visible=False),  # consent_section - don't show
                gr_module.update(visible=False),  # student_id_section
                gr_module.update(visible=False),  # webcam_consent_section
                gr_module.update(visible=False),  # exam_layout - don't show
                gr_module.update(value=get_step_indicator_html(2))  # step_indicator
            )
        
        # PDF validated successfully - proceed with normal flow
        total_chunks = len(get_chunks()) if get_chunks else 0
        verification_text = (
            f"### **Course ID:** `{course_id}` | **Exam ID:** `{exam_id}` | **Section:** `{section_id}` | "
            f"**Max Duration:** `{max_duration_min:.1f} minutes` | "
            f"**Answer Timeout:** `{max_timeout} seconds per question`\n\n"
            f"**✅ PDF Validated:** {valid_count}/{total_chunks} valid chunks available."
        )
        
        # Update step in state - show verification first, then consent will show after user acknowledges
        current_state["current_step"] = "verification"
        
        return (
            current_state,
            [],  # chatbot - clear
            "",  # professor_link_input - clear
            gr_module.update(interactive=False),  # parse_link_btn
            gr_module.update(visible=False),  # professor_link_section - hide previous
            gr_module.update(visible=True),  # verification_section - show it
            gr_module.update(value=verification_text),  # verification_status - show success
            gr_module.update(visible=True),  # consent_section - show it (next step, but verification still visible for context)
            gr_module.update(visible=False),  # student_id_section
            gr_module.update(visible=False),  # webcam_consent_section
            gr_module.update(visible=False),  # exam_layout - don't show yet
            gr_module.update(value=get_step_indicator_html(2))  # step_indicator
        )
    else:
        # Show error message to student in verification_section
        error_message = f"**⚠️ Setup Failed:** {status_msg}"
        # Keep on step 1 if error
        current_state["current_step"] = "professor_link"
        return (
            current_state,
            current_state.get("history", []),  # chatbot - keep history
            url,  # professor_link_input - keep URL
            gr_module.update(interactive=True),  # parse_link_btn - keep enabled
            gr_module.update(visible=True),  # professor_link_section - keep visible
            gr_module.update(visible=True),  # verification_section - show it
            gr_module.update(value=error_message),  # verification_status - show error
            gr_module.update(visible=False),  # consent_section - don't show
            gr_module.update(visible=False),  # student_id_section
            gr_module.update(visible=False),  # webcam_consent_section
            gr_module.update(visible=False),  # exam_layout - don't show
            gr_module.update(value=get_step_indicator_html(1))  # step_indicator
        )


def handle_consent_checkbox(
    checked: bool,
    current_state: Dict[str, Any],
    gr_module,
) -> tuple:
    """
    Handle consent checkbox change - show/hide consent and student ID sections.
    
    Args:
        checked: Whether checkbox is checked
        current_state: Current state dictionary
        gr_module: Gradio module (passed as dependency for version compatibility)
        
    Returns:
        Tuple of (consent_section_update, student_id_section_update, step_indicator_update)
    """
    if checked:
        current_state["current_step"] = "student_id"
        step = 4
    else:
        current_state["current_step"] = "consent"
        step = 3
    
    return (
        gr_module.update(visible=not checked),  # Hide consent section when checked
        gr_module.update(visible=checked),  # Show student ID section when checked
        gr_module.update(value=get_step_indicator_html(step)),  # step_indicator
        gr_module.update(visible=not checked)  # Hide verification section when consent is checked (sequential)
    )


def handle_student_id_verify(
    checked: bool,
    student_id_value: str,
    current_state: Dict[str, Any],
    gr_module,
    ensure_state_fn: Optional[Callable] = None,
) -> tuple:
    """
    Show webcam consent section after Student ID verification.
    
    Args:
        checked: Whether checkbox is checked
        student_id_value: Student ID input value
        current_state: Current state dictionary
        gr_module: Gradio module (passed as dependency for version compatibility)
        ensure_state_fn: Optional function to ensure state
        
    Returns:
        Tuple of Gradio update objects
    """
    if ensure_state_fn:
        current_state = ensure_state_fn(current_state)
    else:
        current_state = ensure_state(current_state)
    
    if checked and student_id_value and student_id_value.strip():
        student_id_clean = student_id_value.strip()
        
        # ENFORCE: Student ID must be numeric only
        if not student_id_clean.isdigit():
            current_state["student_id_verified"] = False
            current_state["current_step"] = "student_id"
            error_msg = "❌ **Student ID must be numeric (integer) only.** Please enter a valid numeric Student ID."
            return (
                current_state,
                gr_module.update(interactive=True),  # Keep input editable
                gr_module.update(value=False, interactive=True),  # Uncheck checkbox
                gr_module.update(visible=True),  # Keep Student ID section visible
                gr_module.update(visible=False),  # Don't show webcam consent section
                gr_module.update(visible=False),  # Don't show exam layout
                gr_module.update(value=error_msg, visible=True),  # Show error message
                gr_module.update(value=get_step_indicator_html(4))  # step_indicator
            )
        
        current_state["student_id"] = student_id_clean
        current_state["student_id_verified"] = True
        current_state["current_step"] = "webcam_consent"
        
        return (
            current_state,
            gr_module.update(value=student_id_clean, interactive=False),  # student_id_input - disable
            gr_module.update(value=True, interactive=False),  # student_id_verify_checkbox - disable
            gr_module.update(visible=False),  # student_id_section - hide previous
            gr_module.update(visible=True),  # webcam_consent_section - show
            gr_module.update(visible=False),  # exam_layout - don't show yet
            gr_module.update(value="", visible=False),  # student_id_status - clear
            gr_module.update(value=get_step_indicator_html(5))  # step_indicator
        )
    else:
        # Checkbox unchecked: Keep status message visible if it was showing an error
        current_state["student_id_verified"] = False
        current_state["current_step"] = "student_id"
        return (
            current_state,
            gr_module.update(interactive=True),  # student_id_input - keep editable
            gr_module.update(value=False, interactive=True),  # student_id_verify_checkbox - keep editable
            gr_module.update(visible=True),  # student_id_section - keep visible
            gr_module.update(visible=False),  # webcam_consent_section - don't show
            gr_module.update(visible=False),  # exam_layout - don't show
            gr_module.update(),  # student_id_status - keep as-is
            gr_module.update(value=get_step_indicator_html(4))  # step_indicator
        )


def handle_webcam_consent_checkbox(
    checked: bool,
    current_state: Dict[str, Any],
    gr_module,
    dependencies: Dict[str, Any],
) -> tuple:
    """
    Show exam layout after webcam consent is acknowledged and start webcam, with PDF validation.
    
    Args:
        checked: Whether checkbox is checked
        current_state: Current state dictionary
        gr_module: Gradio module (passed as dependency for version compatibility)
        dependencies: Dictionary with dependencies:
            - ensure_state: Function to ensure state
            - validate_chunks_available: Function to validate chunks
            - ProctorState: ProctorState class
            - _HAS_PROCTOR: Whether proctor is available
            - mp: MediaPipe instance
            
    Returns:
        Tuple of (state, webcam_consent_section_update, exam_layout_update)
    """
    ensure_state_fn = dependencies.get("ensure_state", ensure_state)
    validate_chunks_available = dependencies.get("validate_chunks_available")
    ProctorState = dependencies.get("ProctorState")
    _HAS_PROCTOR = dependencies.get("_HAS_PROCTOR", False)
    mp = dependencies.get("mp")
    
    current_state = ensure_state_fn(current_state)
    
    if checked:
        # VALIDATION: Check if PDF is loaded and validated before showing exam layout
        is_valid, error_msg, valid_count = validate_chunks_available()
        
        if not is_valid:
            # PDF validation failed - show error and prevent exam layout
            # OBSERVABILITY: Use structured logging (Principle #13)
            logger.warning(
                "pdf_validation_failed_webcam_consent",
                error_msg=error_msg[:200],  # Truncate for safety
                message="PDF validation failed in webcam consent"
            )
            error_display = f"### ❌ PDF Validation Failed\n\n{error_msg}\n\nPlease reload the PDF from the Settings tab."
            
            # Ensure webcam_enabled is explicitly False when validation fails
            current_state["webcam_enabled"] = False
            current_state["webcam_consent_acknowledged"] = False
            
            return (
                current_state,
                gr_module.update(visible=True),  # Keep webcam consent section visible
                gr_module.update(value=error_display, visible=True),  # Show error in exam_layout
                gr_module.update(value=get_step_indicator_html(5))  # step_indicator - Step 5 (Webcam Consent)
            )
        
        # PDF validated - proceed with normal flow
        # Initialize proctor state and start webcam
        if current_state.get("proctor_state") is None and ProctorState:
            current_state["proctor_state"] = ProctorState()
        if _HAS_PROCTOR and current_state.get("proctor_state"):
            current_state["proctor_state"].start(_HAS_PROCTOR, mp)
        current_state["webcam_enabled"] = True
        current_state["webcam_consent_acknowledged"] = True
        current_state["current_step"] = "exam_active"
        
        return (
            current_state,
            gr_module.update(visible=False),  # Hide webcam consent section - hide previous
            gr_module.update(visible=True),  # Show exam layout
            gr_module.update(value=get_step_indicator_html(6))  # step_indicator
        )
    else:
        # Checkbox unchecked: Keep webcam consent section visible
        current_state["webcam_consent_acknowledged"] = False
        current_state["current_step"] = "webcam_consent"
        return (
            current_state,
            gr_module.update(visible=True),  # Keep webcam consent section visible
            gr_module.update(visible=False),  # Don't show exam layout
            gr_module.update(value=get_step_indicator_html(5))  # step_indicator
        )


def handle_start_exam(
    current_state: Dict[str, Any],
    gr_module,
    dependencies: Dict[str, Any],
) -> tuple:
    """
    Start exam with PDF validation - immediately ask first question and enable Record button.
    
    Args:
        current_state: Current state dictionary
        gr_module: Gradio module (passed as dependency for version compatibility)
        dependencies: Dictionary with dependencies:
            - ensure_state: Function to ensure state
            - validate_chunks_available: Function to validate chunks
            - ask_main_question: Function to ask main question
            
    Returns:
        Tuple of (state, proctor_cam_update, proctor_status_update, chatbot_update, mic_update, audio)
    """
    ensure_state_fn = dependencies.get("ensure_state", ensure_state)
    validate_chunks_available = dependencies.get("validate_chunks_available")
    ask_main_question_func = dependencies.get("ask_main_question")
    client = dependencies.get("client")
    
    current_state = ensure_state_fn(current_state)
    
    # VALIDATION: Check if PDF is loaded and validated before starting exam
    is_valid, error_msg, valid_count = validate_chunks_available()
    
    if not is_valid:
        # PDF validation failed - prevent exam start
        # OBSERVABILITY: Use structured logging (Principle #13)
        logger.warning(
            "pdf_validation_failed_start_exam",
            error_msg=error_msg[:200],  # Truncate for safety
            message="PDF validation failed in handle_start_exam"
        )
        error_message = format_error_with_solution(f"❌ {ERROR_CANNOT_START_EXAM} {error_msg}", PDF_ERROR_SUFFIX_RELOAD)
        
        return (
            current_state,
            gr_module.update(),  # proctor_cam - no change
            gr_module.update(value=error_message),  # proctor_status - show error
            gr_module.update(value=error_message),  # chatbot - show error
            gr_module.update(visible=False, interactive=False),  # mic - disable
            None  # audio - no audio
        )
    
    # PDF validated - proceed with normal exam start
    current_state["consent"] = True
    current_state["phase"] = "armed"
    current_state["exam_started"] = True
    
    # Set session start time if not already set
    if not current_state.get("session_start_time"):
        current_state["session_start_time"] = time.time()
    
    # Immediately ask first question
    s_result, audio, status_msg, mic_upd, chatbot_update, cam_upd, cam_status_upd, timeout_upd = ask_main_question_func(current_state, gr_module, client, dependencies)
    
    # Extract status message value (which includes chunk info) from gr.update() object
    if isinstance(status_msg, dict) and 'value' in status_msg:
        status_value = status_msg['value']
    elif hasattr(status_msg, 'value'):
        status_value = status_msg.value
    else:
        # Fallback: default message
        from shared.constants import STATUS_QUESTION_ASKED
        status_value = STATUS_QUESTION_ASKED
    
    # Store status message in state for _stream_proctor to use
    s_result["current"]["last_status_message"] = status_value
    
    # Mic should only be enabled when timer countdown starts (elapsed >= 0)
    # Since timer starts after audio finishes, mic will be disabled until then
    from exam.ui.helpers import _calculate_mic_interactive_state
    mic_interactive = _calculate_mic_interactive_state(s_result, gr_module)
    
    return (
        s_result,  # Updated state
        cam_upd,  # Proctor camera update
        gr_module.update(value=status_value),  # Proctor status update with chunk info
        chatbot_update,  # Question in chatbot
        gr_module.update(visible=True, interactive=mic_interactive),  # Show Record button, enable only if timer started
        audio  # TTS audio file for Examiner component
    )


def handle_mic_wrapper(
    audio_path: str,
    current_state: Dict[str, Any],
    status_md: Any,
    gr_module,
    dependencies: Dict[str, Any],
    progress: Optional[Any] = None,
) -> tuple:
    """
    Wrapper for handle_mic - processes answer recording.
    
    Args:
        audio_path: Path to recorded audio file
        current_state: Current state dictionary
        gr_module: Gradio module (passed as dependency for version compatibility)
        dependencies: Dictionary with dependencies:
            - ensure_state: Function to ensure state
            - handle_mic: Function to handle microphone recording
            - _calculate_processing_status: Function to calculate processing status
            
    Returns:
        Tuple of Gradio update objects
    """
    ensure_state_fn = dependencies.get("ensure_state", ensure_state)
    handle_mic_func = dependencies.get("handle_mic")
    _calculate_processing_status_fn = dependencies.get("_calculate_processing_status", _calculate_processing_status)
    client = dependencies.get("client")
    
    current_state = ensure_state_fn(current_state)
    
    # Process answer recording directly (first question is auto-triggered by webcam)
    s, audio, status_upd, mic_upd, chatbot_history, cam_upd, cam_status_upd, finish_upd, timeout_upd = handle_mic_func(
        audio_path, current_state, gr_module, client, dependencies, progress=progress
    )
    
    # Return student's recorded audio path for audio_out, TTS audio for examiner_audio
    # Use processing status instead of static status messages
    processing_status_upd = _calculate_processing_status_fn(s, gr_module)
    
    return (
        s,  # Updated state
        audio_path,  # audio_out - student's recorded audio
        processing_status_upd,  # unified_status - processing status
        mic_upd,  # mic - microphone component update
        chatbot_history,  # chatbot - chat history
        cam_upd,  # proctor_cam - camera update
        cam_status_upd,  # proctor_status - status update
        finish_upd,  # finish_btn - finish button update
        audio,  # examiner_audio - TTS audio
        timeout_upd  # timeout_countdown - timeout update
    )


def _after_finish_ui(
    s: Dict[str, Any],
    file_path: str,
    status_msg: Any,
    gr_module,
    dependencies: Dict[str, Any],
) -> tuple:
    """
    Update UI after exam completion.
    
    Args:
        s: State dictionary
        file_path: Path to encrypted file
        status_msg: Status message (unused but kept for compatibility)
        gr_module: Gradio module (passed as dependency for version compatibility)
        dependencies: Dictionary with dependencies:
            - ensure_state: Function to ensure state
            - _calculate_processing_status: Function to calculate processing status
            
    Returns:
        Tuple of Gradio update objects
    """
    ensure_state_fn = dependencies.get("ensure_state", ensure_state)
    _calculate_processing_status_fn = dependencies.get("_calculate_processing_status", _calculate_processing_status)
    
    s = ensure_state_fn(s)
    
    # Store file path in state for later use when checkbox is checked
    s["encrypted_file_path"] = file_path
    
    return (
        gr_module.update(visible=False),  # proctor_cam - hide camera
        gr_module.update(value="📷 Proctoring ended."),  # proctor_status
        gr_module.update(value=file_path, visible=False),  # file_out - hide initially
        _calculate_processing_status_fn(s, gr_module),  # unified_status - processing status
        gr_module.update(visible=True)  # file_integrity_checkbox - show checkbox
    )


def handle_file_integrity_checkbox(
    checked: bool,
    current_state: Dict[str, Any],
    gr_module,
    ensure_state_fn: Optional[Callable] = None,
) -> tuple:
    """
    Show file download only when checkbox is checked.
    Finish button remains disabled regardless of checkbox state.
    
    Args:
        checked: Whether checkbox is checked
        current_state: Current state dictionary
        gr_module: Gradio module (passed as dependency for version compatibility)
        ensure_state_fn: Optional function to ensure state
        
    Returns:
        Tuple of (state, file_out_update, finish_btn_update)
    """
    if ensure_state_fn:
        current_state = ensure_state_fn(current_state)
    else:
        current_state = ensure_state(current_state)
    
    file_path = current_state.get("encrypted_file_path", None)
    
    if checked and file_path:
        # Checkbox is checked - show the file, but keep finish button disabled
        return (
            current_state,
            gr_module.update(value=file_path, visible=True),  # file_out - show download
            gr_module.update(interactive=False)  # finish_btn - keep disabled
        )
    else:
        # Checkbox is unchecked - hide the file, keep finish button disabled
        return (
            current_state,
            gr_module.update(value="", visible=False),  # file_out - hide download
            gr_module.update(interactive=False)  # finish_btn - keep disabled
        )


__all__ = [
    "_proctor_end_updates",
    "handle_security_event",
    "handle_parse_and_show_chatbot",
    "handle_consent_checkbox",
    "handle_student_id_verify",
    "handle_webcam_consent_checkbox",
    "handle_start_exam",
    "handle_mic_wrapper",
    "_after_finish_ui",
    "handle_file_integrity_checkbox",
]

