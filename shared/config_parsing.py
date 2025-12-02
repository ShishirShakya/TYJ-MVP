"""
Configuration parsing utilities for VivaAI Secure Exam Proctoring System.

This module provides functions for parsing professor's exam configuration URLs
and validating configuration parameters. Used by both exam.ipynb and dash.ipynb.
"""

from typing import Tuple, Dict, Any, Optional, Callable
from datetime import datetime, timezone
from shared.url_encoding import decode_config_from_url


def validate_config_params(
    config: Dict[str, Any],
    require_pdf: bool = True,
    validate_time_per_question: bool = True
) -> Tuple[bool, str]:
    """
    Validate configuration parameters extracted from URL.
    
    Args:
        config: Configuration dictionary from decode_config_from_url()
        require_pdf: If True, PDF URL is required. If False, PDF is optional.
        validate_time_per_question: If True, validate time_per_question (45-90 seconds).
    
    Returns:
        (is_valid: bool, error_message: str)
        - is_valid: True if all validations pass, False otherwise
        - error_message: Empty string if valid, error message if invalid
    """
    # Extract parameters
    pdf_url = config.get("pdf_url", "")
    num_questions = config.get("num_questions", 1)
    min_followups = config.get("min_followups", 0)
    max_followups = config.get("max_followups", min_followups)
    time_per_question = config.get("time_per_question", 60)
    start_date_str = config.get("start_date", "")
    end_date_str = config.get("end_date", "")
    
    # Validate num_questions
    if num_questions < 1 or num_questions > 50:
        return False, "❌ Number of questions must be between 1 and 50."
    
    # Validate min_followups
    if min_followups < 0 or min_followups > 10:
        return False, "❌ Min follow-ups must be between 0 and 10."
    
    # Validate max_followups
    if max_followups < min_followups or max_followups > 10:
        return False, "❌ Max follow-ups must be between min follow-ups and 10."
    
    # Validate time_per_question (optional validation)
    if validate_time_per_question:
        if time_per_question < 45 or time_per_question > 90:
            return False, "❌ Time per question must be between 45 and 90 seconds."
    
    # Validate PDF URL (if required)
    if require_pdf and not pdf_url:
        return False, "❌ PDF URL is required. Please provide a valid PDF link."
    
    # Validate dates if provided
    current_time = datetime.now(timezone.utc)
    
    if start_date_str:
        try:
            # Try parsing ISO format with timezone or without
            if start_date_str.endswith('Z'):
                start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
            elif '+' in start_date_str or '-' in start_date_str[-6:]:
                start_date = datetime.fromisoformat(start_date_str)
            else:
                start_date = datetime.fromisoformat(start_date_str).replace(tzinfo=timezone.utc)
            
            # Check if current time is before start date
            if current_time < start_date:
                return False, f"❌ Exam not yet started. Start date: {start_date_str}"
        except Exception as e:
            return False, f"❌ Invalid start date format: {start_date_str}. Use ISO format (YYYY-MM-DDTHH:MM:SS)."
    
    if end_date_str:
        try:
            # Try parsing ISO format with timezone or without
            if end_date_str.endswith('Z'):
                end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            elif '+' in end_date_str or '-' in end_date_str[-6:]:
                end_date = datetime.fromisoformat(end_date_str)
            else:
                end_date = datetime.fromisoformat(end_date_str).replace(tzinfo=timezone.utc)
            
            # Check if current time is after end date
            if current_time > end_date:
                return False, f"❌ Due date has passed. End date: {end_date_str}"
        except Exception as e:
            return False, f"❌ Invalid end date format: {end_date_str}. Use ISO format (YYYY-MM-DDTHH:MM:SS)."
    
    # All validations passed
    return True, ""


def parse_passphrase_from_url(url: str) -> Tuple[bool, str, str]:
    """
    Extract only decryption passphrase from professor's link URL.
    
    This is used in Instructor tab to extract passphrase without full exam setup.
    
    Args:
        url: Professor's exam configuration URL
    
    Returns:
        (success: bool, status_message: str, passphrase: str)
        - success: True if passphrase extracted successfully, False otherwise
        - status_message: Human-readable status message
        - passphrase: Extracted passphrase (empty string if extraction failed)
    """
    try:
        if not url or not url.strip():
            return False, "❌ Please provide a professor's link.", ""
        
        # Decode URL using existing function
        config = decode_config_from_url(url.strip())
        
        if config is None:
            return False, "❌ Invalid URL format. Expected format: base_url?pdf_url=...&course_id=...&exam_id=...&passphrase=... (new format) or base_url?pdf_url=...&config=... (old format)", ""
        
        # Extract only decryption passphrase
        passphrase = config.get("decryption", "")
        
        if not passphrase:
            return False, "❌ Decryption passphrase not found in URL.", ""
        
        return True, "✅ Passphrase extracted successfully.", passphrase
        
    except Exception as e:
        return False, f"❌ Error parsing passphrase from URL: {str(e)}", ""


def parse_professor_link_and_setup(
    url: str,
    require_pdf: bool = True,
    load_pdf: bool = False,
    set_exam_context: bool = False,
    default_decryption: str = "",
    # Optional callbacks for exam-specific operations
    load_pdf_callback: Optional[Callable[[str], Tuple[str, str]]] = None,
    validate_chunks_callback: Optional[Callable[[], Tuple[bool, str, int]]] = None,
    set_context_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    set_globals_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    calculate_session_duration_callback: Optional[Callable[[], None]] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Parse professor's link URL and set up examination configuration.
    
    This function is used by both exam.ipynb and dash.ipynb with different modes:
    - Exam mode: require_pdf=True, load_pdf=True, set_exam_context=True
    - Dash mode: require_pdf=False, load_pdf=False, set_exam_context=False
    
    Args:
        url: Professor's exam configuration URL
        require_pdf: If True, PDF URL is required (exam mode). If False, PDF is optional (dash mode).
        load_pdf: If True, load and validate PDF (exam mode). If False, skip PDF loading (dash mode).
        set_exam_context: If True, set exam context variables via callback (exam mode). If False, skip (dash mode).
        default_decryption: Default decryption passphrase if not in URL ("" for exam, "sonic" for dash).
        load_pdf_callback: Optional callback function(url) -> (status_msg, sha256_display) for loading PDF
        validate_chunks_callback: Optional callback function() -> (is_valid, error_msg, valid_count) for validating chunks
        set_context_callback: Optional callback function(config_dict) for setting context variables
        set_globals_callback: Optional callback function(config_dict) for setting global variables
        calculate_session_duration_callback: Optional callback function() for recalculating session duration
    
    Returns:
        (success: bool, status_message: str, state_updates: dict)
        - success: True if parsing and setup successful, False otherwise
        - status_message: Human-readable status message
        - state_updates: Dictionary with parsed configuration values
    """
    try:
        if not url or not url.strip():
            return False, "❌ Please provide a professor's link.", {}
        
        # Decode URL
        config = decode_config_from_url(url.strip())
        
        if config is None:
            return False, "❌ Invalid URL format. Expected format: base_url?pdf_url=...&course_id=...&exam_id=...&passphrase=... (new format) or base_url?pdf_url=...&config=... (old format)", {}
        
        # Extract parameters
        pdf_url = config.get("pdf_url", "")
        course_id = config.get("course_id", "UNKNOWN")
        exam_id = config.get("exam_id", "UNKNOWN")
        num_questions = config.get("num_questions", 1)
        min_followups = config.get("min_followups", 0)
        max_followups = config.get("max_followups", min_followups)  # Default to min if not provided
        time_per_question = config.get("time_per_question", 60)
        section_id = config.get("section_id", "UNKNOWN")
        decryption = config.get("decryption", default_decryption)
        start_date_str = config.get("start_date", "")
        end_date_str = config.get("end_date", "")
        
        # Validate parameters using shared validation function
        is_valid, validation_error = validate_config_params(
            config,
            require_pdf=require_pdf,
            validate_time_per_question=set_exam_context  # Only validate time_per_question in exam mode
        )
        
        if not is_valid:
            return False, validation_error, {}
        
        # Set context variables (if callback provided - exam mode only)
        # NOTE: time_per_question (external/URL name) is converted to max_answer_timeout_sec_ctx (internal/SSOT)
        # See exam/context_vars.py for naming convention documentation
        if set_exam_context and set_context_callback:
            set_context_callback({
                "course_id": course_id,
                "exam_id": exam_id,
                "num_questions": num_questions,
                "min_followups": min_followups,
                "max_followups": max_followups,
                "passphrase": decryption,
                "time_per_question": time_per_question  # External name → converted to max_answer_timeout_sec_ctx internally
            })
        
        # Set global variables (if callback provided - exam mode only)
        if set_exam_context and set_globals_callback:
            set_globals_callback({
                "course_id": course_id,
                "exam_id": exam_id,
                "num_questions": num_questions,
                "min_followups": min_followups,
                "max_followups": max_followups,
                "passphrase": decryption,
                "time_per_question": time_per_question
            })
        
        # Recalculate session duration (if callback provided - exam mode only)
        if set_exam_context and calculate_session_duration_callback:
            calculate_session_duration_callback()
        
        # Load PDF if requested (exam mode only)
        pdf_status_msg = ""
        sha256_display = ""
        pdf_loaded = False
        chunks_validated = False
        valid_chunks_count = 0
        
        if load_pdf and load_pdf_callback:
            try:
                pdf_status_msg, sha256_display = load_pdf_callback(pdf_url)
                if "✅" in pdf_status_msg or "success" in pdf_status_msg.lower():
                    pdf_loaded = True
                    
                    # Validate chunks if callback provided
                    if validate_chunks_callback:
                        is_valid, error_msg, valid_count = validate_chunks_callback()
                        if not is_valid:
                            # PDF loaded but validation failed
                            pdf_loaded = False
                            pdf_status_msg = f"❌ {error_msg}"
                        else:
                            # PDF loaded and validated successfully
                            chunks_validated = True
                            valid_chunks_count = valid_count
                            pdf_status_msg = f"✅ PDF loaded and validated: {valid_count} valid chunks available."
            except Exception as e:
                pdf_status_msg = f"⚠️ Error loading PDF: {str(e)}"
                pdf_loaded = False
                chunks_validated = False
        
        # Build status message
        if load_pdf:
            # Exam mode: Include PDF loading status
            if pdf_loaded and chunks_validated:
                status = "✅ Exam configured successfully. Ready to begin."
            else:
                status = f"⚠️ Exam configured, but PDF could not be loaded or validated: {pdf_status_msg if pdf_status_msg else 'Please check the PDF URL.'}"
        else:
            # Dash mode: Simple success message
            status = "✅ Exam configuration parsed successfully. Ready to decrypt files."
        
        # Create state updates dictionary
        state_updates = {
            "course_id": course_id,
            "exam_id": exam_id,
            "section_id": section_id,
            "passphrase": decryption,
            "pdf_url": pdf_url,
            "time_per_question": time_per_question,
            "start_date": start_date_str,
            "end_date": end_date_str
        }
        
        # Add exam-specific fields if in exam mode
        if set_exam_context:
            state_updates.update({
                "limit": num_questions,
                "followups_min": min_followups,
                "followups_max": max_followups,
                "pdf_loaded": pdf_loaded,
                "chunks_validated": chunks_validated,
                "valid_chunks_count": valid_chunks_count
            })
        
        return True, status, state_updates
        
    except Exception as e:
        return False, f"❌ Error parsing professor's link: {str(e)}", {}

