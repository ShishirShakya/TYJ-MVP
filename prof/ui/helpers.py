"""
UI helper functions for prof.ipynb.

This module contains helper functions for UI calculations and formatting.
These are pure functions that don't depend on Gradio directly.
"""

from datetime import datetime, timedelta
from typing import Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    import gradio as gr

from prof.utils import calculate_max_duration


def combine_date_time(date_str: str, time_str: str) -> str:
    """
    Combine date and time strings into ISO format.
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        time_str: Time string in HH:MM format
        
    Returns:
        ISO format string: YYYY-MM-DDTHH:MM:SS
    """
    if not date_str or not date_str.strip():
        return ""
    time_clean = time_str.strip() or "00:00"
    if len(time_clean) == 5:  # HH:MM format
        time_clean += ":00"
    return f"{date_str.strip()}T{time_clean}"


def update_end_date(start_date: str, start_time: str) -> Tuple:
    """
    Auto-update end date to start date + 7 days when start date changes.
    
    Args:
        start_date: Start date string in YYYY-MM-DD format
        start_time: Start time string (unused but kept for signature compatibility)
        
    Returns:
        Tuple of (gr.update for end_date, gr.update for end_time)
    """
    # Import here to avoid circular dependency
    import gradio as gr
    
    if start_date and start_date.strip():
        try:
            # Parse start date
            start_dt = datetime.strptime(start_date.strip(), "%Y-%m-%d")
            # Add 7 days
            end_dt = start_dt + timedelta(days=7)
            # Format as YYYY-MM-DD
            end_date_str = end_dt.strftime("%Y-%m-%d")
            # Keep end time as 23:59
            end_time_str = "23:59"
            return gr.update(value=end_date_str), gr.update(value=end_time_str)
        except Exception:
            pass
    return gr.update(), gr.update()


def format_duration_display(
    num_questions: int, 
    min_followups: int, 
    max_followups: int, 
    time_per_question: int
) -> str:
    """
    Format duration display string.
    
    Args:
        num_questions: Number of questions
        min_followups: Minimum follow-ups per question
        max_followups: Maximum follow-ups per question
        time_per_question: Time per question in seconds
        
    Returns:
        Formatted duration display string
    """
    try:
        _, max_duration_min = calculate_max_duration(
            num_questions, min_followups, max_followups, time_per_question
        )
        return f"⏱️ **Maximum Total Duration:** {max_duration_min:.1f} minutes"
    except Exception:
        return "⏱️ **Maximum Total Duration:** Calculating..."


def format_pdf_status_message(result: dict) -> str:
    """
    Format PDF validation status message.
    
    Args:
        result: Dictionary with validation results from validate_pdf_and_calculate_chunks
        
    Returns:
        Formatted status message string
    """
    if result.get('error'):
        return f"❌ {result['error']}"
    
    return (
        f"✅ PDF validated successfully! (Size: {result['file_size_mb']:.2f}MB) | "
        f"📊 Chunk Analysis: • Total chunks created: {result['num_total_chunks']} • "
        f"Valid chunks: {result['num_valid_chunks']} • Invalid chunks: {result['invalid_count']} | "
        f"Valid chunk generates balanced content from the PDF."
    )

