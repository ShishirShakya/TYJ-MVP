"""
Grading module for exam.ipynb.

This module contains AI-powered grading functions:
- Block grading with rubric scoring
- Feedback parsing and extraction
- Score calculation

FERPA COMPLIANCE:
- Student answers are sent to OpenAI API for grading purposes
- No student_id, session_id, or other PII is included in API calls
- Data is encrypted in transit (HTTPS/TLS)
- Content is sanitized to prevent prompt injection and accidental PII exposure
- Ensure OpenAI agreement covers FERPA compliance (School Official exception or consent)
- Student consent is required before exam begins (handled in exam flow)
"""

import re
from typing import Dict, Any, Optional, Callable

from openai import OpenAI

from exam.utils import _sanitize_for_prompt, _ensure_no_pii_in_content, with_retry, _log_token_usage
from exam.ai.context_manager import msgs_from_state
from exam.config import CHAT_MODEL

# Import centralized prompts (supports encrypted prompts in production)
from shared.config.prompts import SYSTEM_PROMPT, FEEDBACK_BLOCK_INSTR
from shared.constants import (
    PROCESSING_ASSESSMENT_MSG,
    format_assessment_message,
    get_qualitative_assessment,
    format_answer_label,
    FEEDBACK_DEFAULT_TEXT,
)


def _parse_feedback(fb_raw: str) -> tuple[Dict[str, int], str]:
    """
    Parse feedback text and extract scores and feedback text.
    
    **Contract**:
    - **Inputs**: Raw feedback text string from AI
    - **Outputs**: Tuple of (scores_dict, feedback_text)
    - **Invariants**: Scores are always in range [0, 100]
    - **Failure Modes**: Returns default scores (60) if parsing fails
    
    Parses AI-generated feedback text to extract:
    - Dimension scores (Conceptual, Analytical, Application, Reflection, Overall)
    - Feedback text (explanatory text)
    
    Uses regex matching to extract scores and text. If a field is missing,
    uses fallback value of 60 (passing grade).
    
    Args:
        fb_raw: Raw feedback text from AI (expected format: "Feedback: ...\nConceptual: 85\n...")
        
    Returns:
        Tuple of:
        - scores_dict: Dictionary with dimension scores (all 0-100)
        - feedback_text: Extracted feedback text (or fallback if missing)
        
    Example:
        ```python
        fb = "Feedback: Good understanding.\nConceptual: 85\nAnalytical: 80\n..."
        scores, text = _parse_feedback(fb)
        # scores = {"Conceptual": 85, "Analytical": 80, ...}
        # text = "Good understanding."
        ```
    """
    scores_dict = {}
    required_fields = ["Conceptual", "Analytical", "Application", "Reflection", "Overall"]
    
    # Extract all scores with strict regex matching
    # Handle both plain format "Conceptual: 85" and markdown format "**Conceptual:** 85"
    for field in required_fields:
        # Match pattern: "Field: <integer>" or "**Field:** <integer>" (case-insensitive)
        # Try markdown format first (more specific), then plain format
        m_score = re.search(rf"\*{{0,2}}{field}\*{{0,2}}:\s*\*{{0,2}}\s*(\d{{1,3}})", fb_raw, re.IGNORECASE)
        if m_score:
            score_val = int(m_score.group(1))
            # Validate score is in valid range
            scores_dict[field] = max(0, min(100, score_val))
        else:
            # If field not found, use fallback
            scores_dict[field] = 60  # Default fallback
    
    # Extract feedback text (everything between "Feedback:" and next field)
    feedback_text = ""
    m_feedback = re.search(r"Feedback:\s*(.+?)(?=\n\w+:|$)", fb_raw, re.IGNORECASE | re.DOTALL)
    if m_feedback:
        feedback_text = m_feedback.group(1).strip()
    
    # If feedback text is missing, use fallback
    if not feedback_text:
        feedback_text = FEEDBACK_DEFAULT_TEXT
    
    return scores_dict, feedback_text


def _calculate_overall_score(scores_dict: Dict[str, int]) -> int:
    """
    Calculate overall score as average of four dimensions.
    
    **Contract**:
    - **Inputs**: Dictionary with dimension scores
    - **Outputs**: Overall score integer (0-100)
    - **Invariants**: Result is always in range [0, 100]
    - **Failure Modes**: Uses default score (60) for missing dimensions
    
    Calculates overall score as the arithmetic mean of four dimensions:
    - Conceptual
    - Analytical
    - Application
    - Reflection
    
    Missing dimensions default to 60 (passing grade).
    
    Args:
        scores_dict: Dictionary with dimension scores (may be incomplete)
        
    Returns:
        Overall score (0-100), rounded to nearest integer
        
    Example:
        ```python
        scores = {"Conceptual": 85, "Analytical": 80, "Application": 75, "Reflection": 70}
        overall = _calculate_overall_score(scores)  # Returns 77
        ```
    """
    dimension_scores = [
        scores_dict.get("Conceptual", 60),
        scores_dict.get("Analytical", 60),
        scores_dict.get("Application", 60),
        scores_dict.get("Reflection", 60)
    ]
    score = round(sum(dimension_scores) / len(dimension_scores))
    return score


def _extract_scores(fb_raw: str) -> Dict[str, int]:
    """
    Extract all scores from feedback text.
    
    Args:
        fb_raw: Raw feedback text from AI
        
    Returns:
        Dictionary with all scores including calculated Overall
    """
    scores_dict, _ = _parse_feedback(fb_raw)
    
    # Calculate Overall as average of four dimensions for consistency
    overall_score = _calculate_overall_score(scores_dict)
    scores_dict["Overall"] = overall_score
    
    return scores_dict


def grade_current_block(
    s: Dict[str, Any],
    client: OpenAI,
    ensure_state: Callable,
    save_state_to_disk: Callable,
    reset_current_block: Callable,
    get_chunks: Callable,
    progress: Optional[Callable] = None
) -> Dict[str, Any]:
    """
    Grade the current question block and generate feedback.
    
    This function:
    1. Builds a summary of the current question and answers
    2. Calls AI to generate feedback and scores
    3. Parses and validates the feedback
    4. Updates state with scores and feedback
    5. Prepares for next question
    
    Args:
        s: Session state dictionary
        client: OpenAI client instance
        ensure_state: Function to ensure state is initialized
        save_state_to_disk: Function to save state to disk
        reset_current_block: Function to reset current block
        get_chunks: Function to get PDF chunks
        progress: Optional progress callback
        
    Returns:
        Updated state dictionary
    """
    s = ensure_state(s)
    
    try:
        # Snapshot per-block proctor attention
        # Note: ProctorState is now imported from exam.proctor (Phase 5 complete)
        try:
            st = s.get("proctor_state", None)
            if st and hasattr(st, "add_block_rollup"):
                s["proctor_blocks"].append(st.add_block_rollup())
        except Exception:
            pass

        main_q = s["current"]["main_question"] or ""
        answers = s["current"]["answers"][:]
        block_summary = ["MAIN QUESTION:", main_q, "\nSTUDENT ANSWERS:"]
        for i, a in enumerate(answers):
            label = format_answer_label(i)
            block_summary.append(f"- {label}: {a}")
        block_summary_text = "\n".join(block_summary)
        
        # FERPA COMPLIANCE: Ensure no PII in content before sending to OpenAI
        block_summary_text = _ensure_no_pii_in_content(block_summary_text)
        
        # Sanitize block summary to prevent prompt injection
        block_summary_sanitized = _sanitize_for_prompt(block_summary_text, max_len=4000)
        
        # Add processing message to history to trigger progress bar
        s["history"].append({"role": "assistant", "content": PROCESSING_ASSESSMENT_MSG})
        
        # COST OPTIMIZATION: Use operation-specific history for feedback
        # COST OPTIMIZATION: Lower temperature (0.3 -> 0.2)
        if progress:
            progress(0.3)
        
        # GRACEFUL FAILURE: Get circuit breaker from dependencies if available (Principle #16)
        circuit_breaker = None
        if hasattr(grade_current_block, '_circuit_breaker'):
            circuit_breaker = grade_current_block._circuit_breaker
        elif 'circuit_breaker_manager' in globals():
            # Try to get from global manager if available
            try:
                from shared.circuit_breaker import get_default_circuit_breaker_manager
                manager = get_default_circuit_breaker_manager()
                circuit_breaker = manager.get_breaker("openai_chat")
            except Exception:
                pass
        
        comp = with_retry(
            client.chat.completions.create,
            circuit_breaker=circuit_breaker,
            service_name="openai_chat",
            model=CHAT_MODEL,
            messages=msgs_from_state(s, operation_type="feedback") + [{"role": "user", "content": f"{block_summary_sanitized}\n\n{FEEDBACK_BLOCK_INSTR}"}],
            temperature=0.2,  # Reduced from 0.3
            max_tokens=500
        )
        
        if progress:
            progress(0.6)
        
        # COST OPTIMIZATION: Log token usage
        _log_token_usage(comp, "feedback_generation", s, model=CHAT_MODEL)
        fb_raw = comp.choices[0].message.content.strip()
        
        # Parse feedback and extract scores
        scores_dict, feedback_text = _parse_feedback(fb_raw)
        score = _calculate_overall_score(scores_dict)
        scores_dict["Overall"] = score
        
        # Use extracted scores, falling back to overall score for any missing fields
        s["rubrics"].append({
            "Feedback": feedback_text,  # _parse_feedback ensures this is never empty
            "Conceptual": scores_dict.get("Conceptual", score),
            "Analytical": scores_dict.get("Analytical", score),
            "Application": scores_dict.get("Application", score),
            "Reflection": scores_dict.get("Reflection", score),
            "Overall": score
        })
        s["scores"].append(score)
        
        # COST OPTIMIZATION: Store summary instead of full feedback in history
        # This reduces future context size while preserving key information
        # Note: Hide numeric grades from student, show qualitative assessment only
        # Determine qualitative assessment based on overall score (using centralized helper)
        qualitative = get_qualitative_assessment(score)
        feedback_summary = format_assessment_message(qualitative, feedback_text)
        
        # Replace the "Generating assessment..." message with the feedback summary
        # (The message was added earlier to trigger the progress bar)
        s["history"][-1] = {"role": "assistant", "content": feedback_summary}
        s["asked_main"] += 1
        
        save_state_to_disk(s)
        
        # Note: The rest of the function (preparing next question) will be handled
        # by the calling code in exam.ipynb for now, until we extract state management
        
        if progress:
            progress(1.0)
            
    except Exception as e:
        # Error handling - log and continue
        error_msg = f"Error grading block: {str(e)}"
        s["history"].append({"role": "assistant", "content": error_msg})
        if progress:
            progress(1.0)
    
    return s

