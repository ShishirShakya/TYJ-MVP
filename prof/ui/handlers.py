"""
UI event handlers for prof.ipynb.

This module contains all Gradio event handlers for the professor URL generator UI.
All handlers use dependency injection pattern for testability and reusability.
"""

import os
from typing import Tuple, Dict, Any, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    import gradio as gr

from prof.ui.helpers import (
    combine_date_time,
    format_duration_display,
    format_pdf_status_message,
)
from shared.validation import validate_url


def handle_step1_checkbox_change(
    gr_module,
    dependencies: Dict[str, Any],
    checked: bool,
    state: dict
) -> Tuple:
    """
    Handle Step 1 checkbox change - show/hide Step 2.
    
    Args:
        gr_module: Gradio module
        dependencies: Dependencies dictionary (unused but kept for consistency)
        checked: Checkbox checked state
        state: Current state dictionary
        
    Returns:
        Tuple of (step1_accordion_update, step2_accordion_update, state)
    """
    if checked:
        # Close Step 1, show Step 2
        return (
            gr_module.update(open=False, visible=False),  # Step 1 accordion
            gr_module.update(open=True, visible=True),   # Step 2 accordion
            state  # Keep state unchanged
        )
    else:
        # Show Step 1, hide Step 2
        return (
            gr_module.update(open=True, visible=True),   # Step 1 accordion
            gr_module.update(open=False, visible=False),  # Step 2 accordion
            state  # Keep state unchanged
        )


def handle_validate_pdf_and_show_step3(
    gr_module,
    dependencies: Dict[str, Any],
    pdf_url: str,
    state: dict
) -> Tuple:
    """
    Validate PDF, calculate chunks, and show Step 3 on success.
    
    Args:
        gr_module: Gradio module
        dependencies: Dependencies dictionary with:
            - validate_pdf_and_calculate_chunks: Function to validate PDF
            - calculate_max_duration: Function to calculate duration
        pdf_url: PDF URL to validate
        state: Current state dictionary
        
    Returns:
        Tuple of UI updates for step3_pdf_status, step1_accordion, step2_accordion,
        step3_accordion, state, generate_n_questions_input, max_duration_display
    """
    validate_pdf = dependencies["validate_pdf_and_calculate_chunks"]
    calculate_max_duration = dependencies["calculate_max_duration"]
    
    # Use standardized validation
    url_validation = validate_url(pdf_url, url_type="PDF")
    if not url_validation.is_valid:
        return (
            gr_module.update(value=f"### {url_validation.to_formatted_message()}", visible=True),  # step3_pdf_status
            gr_module.update(open=False, visible=False),  # step1_accordion
            gr_module.update(open=False, visible=False),  # step2_accordion
            gr_module.update(open=True, visible=True),  # Step 3 accordion
            state,  # Keep state unchanged
            gr_module.update(),  # Number of Questions (no change)
            gr_module.update(value="⏱️ **Maximum Total Duration:** Calculating...", visible=True)  # Duration display
        )
    
    # Validate PDF and calculate chunks
    result = validate_pdf(pdf_url)
    
    if result.get('error'):
        # Show error message
        return (
            gr_module.update(value=format_pdf_status_message(result), visible=True),  # step3_pdf_status
            gr_module.update(open=False, visible=False),  # step1_accordion
            gr_module.update(open=False, visible=False),  # step2_accordion
            gr_module.update(open=True, visible=True),  # Step 3 accordion
            state,  # Keep state unchanged
            gr_module.update(),  # Number of Questions (no change)
            gr_module.update(value="⏱️ **Maximum Total Duration:** Calculating...", visible=True)  # Duration display
        )
    
    # Success - update state and show Step 3
    new_state = {
        'num_valid_chunks': result['num_valid_chunks'],
        'num_total_chunks': result['num_total_chunks'],
        'file_size_mb': result['file_size_mb']
    }
    
    # Update status message
    status_msg = format_pdf_status_message(result)
    
    # Update Number of Questions max value
    max_questions = max(1, result['num_valid_chunks'])
    
    # Calculate initial duration when Step 3 opens
    _, initial_duration_min = calculate_max_duration(1, 0, 1, 60)
    initial_duration_display = f"⏱️ **Maximum Total Duration:** {initial_duration_min:.1f} minutes"
    
    return (
        gr_module.update(value=status_msg, visible=True),  # step3_pdf_status
        gr_module.update(open=False, visible=False),  # step1_accordion
        gr_module.update(open=False, visible=False),  # step2_accordion
        gr_module.update(open=True, visible=True),  # Step 3 accordion
        new_state,  # Update state
        gr_module.update(maximum=max_questions),  # Update Number of Questions max
        gr_module.update(value=initial_duration_display, visible=True)  # Initial duration display
    )


def handle_calculate_duration_and_show_generate(
    gr_module,
    dependencies: Dict[str, Any],
    num_questions: int,
    min_followups: int,
    max_followups: int,
    time_per_question: int,
    state: dict
) -> Tuple:
    """
    Calculate duration and show Generate URL when fields are valid.
    
    Args:
        gr_module: Gradio module
        dependencies: Dependencies dictionary with:
            - calculate_max_duration: Function to calculate duration
        num_questions: Number of questions
        min_followups: Minimum follow-ups
        max_followups: Maximum follow-ups
        time_per_question: Time per question in seconds
        state: Current state dictionary
        
    Returns:
        Tuple of (max_duration_display_update, step3_generate_accordion_update, state)
    """
    calculate_max_duration = dependencies["calculate_max_duration"]
    
    try:
        num_questions_val = int(num_questions) if num_questions else 1
        min_followups_val = int(min_followups) if min_followups else 0
        max_followups_val = int(max_followups) if max_followups else min_followups_val
        time_per_question_val = int(time_per_question) if time_per_question else 60
        
        # Validate
        if num_questions_val < 1:
            return (
                gr_module.update(value="⏱️ **Maximum Total Duration:** Please enter valid number of questions.", visible=True),
                gr_module.update(open=False, visible=False),  # Generate URL accordion
                state  # Keep state unchanged
            )
        
        if max_followups_val < min_followups_val:
            return (
                gr_module.update(value="⏱️ **Maximum Total Duration:** Max follow-ups must be ≥ min follow-ups.", visible=True),
                gr_module.update(open=False, visible=False),  # Generate URL accordion
                state  # Keep state unchanged
            )
        
        # Calculate duration
        duration_display = format_duration_display(
            num_questions_val, min_followups_val, max_followups_val, time_per_question_val
        )
        
        return (
            gr_module.update(value=duration_display, visible=True),  # Max duration display
            gr_module.update(open=True, visible=True),  # Generate URL accordion
            state  # Keep state unchanged
        )
    except Exception:
        return (
            gr_module.update(value="⏱️ **Maximum Total Duration:** Calculating...", visible=True),
            gr_module.update(open=False, visible=False),  # Generate URL accordion
            state  # Keep state unchanged
        )


def handle_generate_url(
    gr_module,
    dependencies: Dict[str, Any],
    pdf_url: str,
    base_url: str,
    course_id: str,
    exam_id: str,
    section_id: str,
    num_questions: int,
    min_followups: int,
    max_followups: int,
    time_per_question: int,
    start_date: str,
    start_time: str,
    end_date: str,
    end_time: str,
    state: dict
):
    """
    Generate URL with encoded parameters after validating all steps.
    
    Args:
        gr_module: Gradio module
        dependencies: Dependencies dictionary with:
            - encode_config_to_url: Function to encode config to URL
            - generate_secure_passphrase: Function to generate passphrase
            - combine_date_time: Function to combine date and time
        pdf_url: PDF URL
        base_url: Base URL for exam
        course_id: Course identifier
        exam_id: Exam identifier
        section_id: Section identifier
        num_questions: Number of questions
        min_followups: Minimum follow-ups
        max_followups: Maximum follow-ups
        time_per_question: Time per question in seconds
        start_date: Start date string
        start_time: Start time string
        end_date: End date string
        end_time: End time string
        state: Current state dictionary
        
    Yields:
        Generator that yields tuples of (url, status_update, button1_update, button2_update, state)
    """
    encode_config_to_url = dependencies["encode_config_to_url"]
    generate_secure_passphrase = dependencies["generate_secure_passphrase"]
    combine_date_time = dependencies["combine_date_time"]
    
    try:
        # Return loading state immediately
        yield "", gr_module.update(value="⏳ Validating PDF URL...", visible=True), gr_module.update(interactive=False), gr_module.update(interactive=False), state
        
        # Use standardized validation
        pdf_url_validation = validate_url(pdf_url, url_type="PDF")
        if not pdf_url_validation.is_valid:
            return "", gr_module.update(value=f"### {pdf_url_validation.to_formatted_message()}", visible=True), gr_module.update(interactive=True), gr_module.update(interactive=False), state
        
        # Validate state has chunk data
        if not state or state.get('num_valid_chunks', 0) == 0:
            from shared.error_formatter import format_user_error
            error_msg = format_user_error(
                "VALIDATION_ERROR",
                "Please validate PDF first (Step 1)",
                "Complete Step 1 to validate the PDF and calculate chunks before generating URL"
            )
            return "", gr_module.update(value=f"### {error_msg}", visible=True), gr_module.update(interactive=True), gr_module.update(interactive=False), state
        
        yield "", gr_module.update(value="⏳ Validating configuration...", visible=True), gr_module.update(interactive=False), gr_module.update(interactive=False), state
        
        # Auto-generate secure passphrase (not shown in UI - embedded in URL)
        decryption_passphrase = generate_secure_passphrase()
        
        # Validate base URL - always prefer EXAM_BASE_URL from environment if available
        # If Textbox is empty or has the hardcoded default, use environment variable
        base_url_stripped = base_url.strip() if base_url else ""
        if not base_url_stripped or base_url_stripped == "http://localhost:7860":
            # Re-read from environment to get latest value from .env
            base_url = os.getenv("EXAM_BASE_URL", "http://localhost:7860")
        else:
            # User provided a custom URL in the UI, validate it
            base_url_validation = validate_url(base_url_stripped, url_type="base")
            if not base_url_validation.is_valid:
                return "", gr_module.update(value=f"### {base_url_validation.to_formatted_message()}", visible=True), gr_module.update(interactive=True), gr_module.update(interactive=False), state
            base_url = base_url_stripped
        
        # Validate followups
        min_followups_val = int(min_followups) if min_followups else 0
        max_followups_val = int(max_followups) if max_followups else min_followups_val
        time_per_question_val = int(time_per_question) if time_per_question else 60
        
        if max_followups_val < min_followups_val:
            return "", gr_module.update(value="❌ Max follow-ups must be greater than or equal to min follow-ups.", visible=True), gr_module.update(interactive=True), gr_module.update(interactive=False), state
        
        # Validate num_questions <= num_valid_chunks
        num_questions_val = int(num_questions) if num_questions else 1
        if num_questions_val > state.get('num_valid_chunks', 0):
            return "", gr_module.update(value=f"❌ Number of questions ({num_questions_val}) exceeds maximum available ({state.get('num_valid_chunks', 0)}). Please reduce the number of questions.", visible=True), gr_module.update(interactive=True), gr_module.update(interactive=False), state
        
        # Combine date and time into ISO format
        try:
            start_date_str = combine_date_time(start_date or "", start_time or "")
            end_date_str = combine_date_time(end_date or "", end_time or "")
        except Exception as e:
            return "", gr_module.update(value=f"❌ Error combining date/time: {str(e)}", visible=True), gr_module.update(interactive=True), gr_module.update(interactive=False), state
        
        # Validate dates if provided
        if start_date_str:
            try:
                datetime.fromisoformat(start_date_str)
            except Exception as e:
                return "", gr_module.update(value=f"❌ Invalid start date/time format: {start_date_str}. Error: {str(e)}", visible=True), gr_module.update(interactive=True), gr_module.update(interactive=False), state
        
        if end_date_str:
            try:
                datetime.fromisoformat(end_date_str)
            except Exception as e:
                return "", gr_module.update(value=f"❌ Invalid end date/time format: {end_date_str}. Error: {str(e)}", visible=True), gr_module.update(interactive=True), gr_module.update(interactive=False), state
        
        # All validations passed - generate URL
        yield "", gr_module.update(value="⏳ Generating URL...", visible=True), gr_module.update(interactive=False), gr_module.update(interactive=False), state
        
        # Generate URL (using new v2 format with individual query parameters)
        try:
            encode_config_to_url = dependencies["encode_config_to_url"]
            url = encode_config_to_url(
                base_url.strip(),
                pdf_url.strip(),
                course_id or "UNKNOWN",
                exam_id or "UNKNOWN",
                num_questions_val,
                min_followups_val,
                max_followups_val,
                section_id or "UNKNOWN",
                decryption_passphrase,
                start_date_str,
                end_date_str,
                time_per_question_val
            )
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            yield "", gr_module.update(value=f"❌ Error generating URL: {str(e)}. Details: {error_detail[:200]}", visible=True), gr_module.update(interactive=True), gr_module.update(interactive=False), state
            return
        
        # Success - yield the final result
        success_msg = f"""✅ URL generated successfully!

💡 **The decryption passphrase is automatically embedded in the URL. The Instructor Dashboard can extract it automatically when you paste this URL.**

📤 **To be shared with the student.**"""
        yield url, gr_module.update(value=success_msg, visible=True), gr_module.update(interactive=True), gr_module.update(interactive=True), state
    except Exception as e:
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        return "", gr_module.update(value=f"❌ Unexpected error: {str(e)}", visible=True), gr_module.update(interactive=True), gr_module.update(interactive=False), state


def handle_copy_url_to_clipboard(
    gr_module,
    dependencies: Dict[str, Any],
    url: str
) -> Tuple[str, Any]:
    """
    Copy URL to clipboard and show feedback.
    
    Args:
        gr_module: Gradio module
        dependencies: Dependencies dictionary (unused but kept for consistency)
        url: URL to copy
        
    Returns:
        Tuple of (url, status_update)
    """
    if url and url.strip():
        return url, gr_module.update(value="✅ URL copied to clipboard!", visible=True)
    return url, gr_module.update(value="❌ No URL to copy.", visible=True)

