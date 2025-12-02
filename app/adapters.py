"""
Adapter layer for connecting FastAPI endpoints to exam flow functions.

This module provides:
- State loading from session_id
- Dependency building for exam flow functions
- Response conversion from flow tuples to API responses
- Error handling and sanitization

DEPENDENCY INVERSION: This module acts as an adapter between the FastAPI layer
and the exam flow layer, allowing both to evolve independently (Principle #26).
"""

import os
import json
from typing import Dict, Any, Optional, Tuple
from openai import OpenAI

from exam.state.core import ensure_state
from exam.state.persistence import save_state_to_disk
from exam.file_utils import _paths_for_session
from exam.flow.questions import ask_main_question
from exam.flow.audio import handle_mic
from exam.flow.grading import grade_current_block
from shared.logging_config import get_logger

logger = get_logger()


def load_state_from_session_id(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Load state dictionary from session_id.
    
    Args:
        session_id: Session identifier
        
    Returns:
        State dictionary if found, None otherwise
    """
    try:
        state = {"session_id": session_id}
        paths = _paths_for_session(state)
        
        if not os.path.exists(paths["STATE_PATH"]):
            return None
        
        with open(paths["STATE_PATH"], "r", encoding="utf-8") as f:
            state = json.load(f)
        
        return state
    except Exception as e:
        logger.error(
            "load_state_failed",
            session_id=session_id,
            error_type=type(e).__name__,
            error_message=str(e)[:200]
        )
        return None


def build_flow_dependencies(client: OpenAI) -> Dict[str, Any]:
    """
    Build dependencies dictionary for exam flow functions.
    
    This function collects all dependencies needed by the exam flow functions.
    It's the Single Source of Truth for dependency setup (Principle #2).
    
    Args:
        client: OpenAI client instance
        
    Returns:
        Dictionary with all required dependencies
    """
    # Import dependencies as needed
    from exam.state.core import reset_current_block, get_followup_range
    from exam.state.persistence import save_state_to_disk
    from exam.file_utils import _paths_for_session
    from exam.utils import with_retry, _log_token_usage, _sanitize_for_prompt
    from exam.ai.question_generator import _gen_main_question_with_ctx, _gen_followup
    from exam.ai.grader import _parse_feedback, _calculate_overall_score, msgs_from_state
    from exam.audio.tts import tts_to_mp3
    from exam.audio.stt import transcribe
    from exam.audio.utils import get_audio_duration
    from exam.context_vars import (
        get_chunks, get_max_answer_timeout_sec, get_followups_min, get_followups_max
    )
    from exam.proctor import ProctorState
    from exam.ui.helpers import _calculate_timeout_status
    from exam.ui.handlers import _proctor_end_updates
    from exam.flow.error_handling import _categorize_error
    from exam.config import CHAT_MODEL
    from shared.config.prompts import FEEDBACK_BLOCK_INSTR
    from shared.time_provider import get_default_time_provider
    
    # Try to import optional dependencies
    try:
        from exam.audio.voiceprint import extract_audio_features, compare_voiceprints
        _HAS_LIBROSA = True
    except ImportError:
        extract_audio_features = None
        compare_voiceprints = None
        _HAS_LIBROSA = False
    
    try:
        from exam.audio.stylometry import analyze_speech_stylometry
    except ImportError:
        analyze_speech_stylometry = None
    
    # Build dependencies dictionary
    dependencies = {
        # State management
        "ensure_state": ensure_state,
        "reset_current_block": reset_current_block,
        "get_followup_range": get_followup_range,
        "save_state_to_disk": save_state_to_disk,
        "_paths_for_session": _paths_for_session,
        
        # PDF and chunks
        "get_chunks": get_chunks,
        "validate_chunks_available": lambda: (True, "", len(get_chunks()) if get_chunks() else 0),
        "_validate_context": lambda ctx, chunks=None: (True, ""),
        
        # AI functions
        "_gen_main_question_with_ctx": _gen_main_question_with_ctx,
        "_gen_followup": _gen_followup,
        "_parse_feedback": _parse_feedback,
        "_calculate_overall_score": _calculate_overall_score,
        "msgs_from_state": msgs_from_state,
        "with_retry": with_retry,
        "_log_token_usage": _log_token_usage,
        "_sanitize_for_prompt": _sanitize_for_prompt,
        
        # Audio functions
        "tts_to_mp3": tts_to_mp3,
        "transcribe": transcribe,
        "get_audio_duration": get_audio_duration,
        "extract_audio_features": extract_audio_features if _HAS_LIBROSA else None,
        "compare_voiceprints": compare_voiceprints if _HAS_LIBROSA else None,
        "analyze_speech_stylometry": analyze_speech_stylometry,
        
        # UI helpers
        "_calculate_timeout_status": lambda s: _calculate_timeout_status(s, None, get_max_answer_timeout_sec),
        "_proctor_end_updates": _proctor_end_updates,
        "_categorize_error": _categorize_error,
        
        # Constants
        "CHAT_MODEL": CHAT_MODEL,
        "FEEDBACK_BLOCK_INSTR": FEEDBACK_BLOCK_INSTR,
        
        # Audio processing helpers (simplified for API)
        "update_network_status": lambda s: "online",
        "queue_answer_locally": lambda s, text, audio_path=None, **kwargs: None,
        "_detect_profanity": lambda text: False,
        "_count_meaningful_words": lambda text: len(text.split()),
        "_detect_answer_reuse": lambda s, text: False,
        "_hash_answer": lambda text: hash(text),
        "ask_followup_question": None,  # Will be set if needed
        "grade_current_block": grade_current_block,
        "MAX_SESSION_DURATION_SEC": 3600,
        "MIN_WORDS": 10,
        "MAX_SHORT_ATTEMPTS": 3,
        "SHORT_PROMPT_TTS": "Please provide a more detailed answer.",
        
        # Proctor (optional)
        "ProctorState": ProctorState,
        
        # Time provider for deterministic behavior (Principle #5)
        "time_provider": get_default_time_provider(),
    }
    
    return dependencies


class MockGradioModule:
    """Mock Gradio module for API endpoints (no UI needed)."""
    
    @staticmethod
    def update(**kwargs):
        """Mock gr.update() - returns empty dict."""
        return {}


def call_ask_main_question(
    state: Dict[str, Any],
    client: OpenAI,
    dependencies: Dict[str, Any]
) -> Tuple[Dict[str, Any], str, Optional[str]]:
    """
    Call ask_main_question and extract relevant data for API response.
    
    Args:
        state: State dictionary
        client: OpenAI client
        dependencies: Dependencies dictionary
        
    Returns:
        Tuple of (updated_state, question_text, question_id)
    """
    gr_module = MockGradioModule()
    
    try:
        result = ask_main_question(
            s=state,
            gr_module=gr_module,
            client=client,
            dependencies=dependencies
        )
        
        # Extract state (first element)
        updated_state = result[0] if result else state
        
        # Extract question from history (last assistant message)
        history = updated_state.get("history", [])
        question_text = ""
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                question_text = msg.get("content", "")
                break
        
        # Generate question_id from current block
        question_id = f"q_{updated_state.get('current_block', 0)}"
        
        return updated_state, question_text, question_id
    except Exception as e:
        logger.error(
            "ask_main_question_failed",
            session_id=state.get("session_id"),
            error_type=type(e).__name__,
            error_message=str(e)[:200]
        )
        raise


def call_grade_current_block(
    state: Dict[str, Any],
    client: OpenAI,
    dependencies: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Call grade_current_block and extract relevant data for API response.
    
    Args:
        state: State dictionary
        client: OpenAI client
        dependencies: Dependencies dictionary
        
    Returns:
        Tuple of (updated_state, grading_result)
        grading_result contains: score, feedback, rubric
    """
    gr_module = MockGradioModule()
    
    try:
        result = grade_current_block(
            s=state,
            gr_module=gr_module,
            client=client,
            dependencies=dependencies
        )
        
        # Extract state (first element)
        updated_state = result[0] if result else state
        
        # Extract rubric scores from state
        rubrics = updated_state.get("rubrics", [])
        latest_rubric = rubrics[-1] if rubrics else {}
        
        # FERPA COMPLIANCE: Hide numeric grades from students during exam
        # Only return qualitative assessment (Excellent/Satisfactory/Not-Satisfactory) + feedback text
        # Numeric scores are stored in state and will be included in encrypted export (.enc file)
        overall_score = latest_rubric.get("Overall", 0)
        feedback_text = latest_rubric.get("Feedback", "")
        
        # Use centralized helper to get qualitative assessment
        from shared.constants import get_qualitative_assessment, format_assessment_message, clean_feedback_text, clean_feedback_summary
        qualitative = get_qualitative_assessment(overall_score)
        
        # SECURITY FIX: Clean feedback_text before formatting to remove any leaked
        # qualitative words (Not-Satisfactory, Satisfactory, Excellent) and numeric scores
        feedback_text_cleaned = clean_feedback_text(feedback_text)
        
        # Format assessment message
        feedback_formatted = format_assessment_message(qualitative, feedback_text_cleaned)
        
        # SECURITY FIX: Apply safety net to strip any leaked scores or qualitative words
        # Handles both plain and markdown formats
        feedback_formatted = clean_feedback_summary(feedback_formatted)
        
        # Build grading result with qualitative assessment only (no numeric scores)
        grading_result = {
            "score": 0.0,  # Don't expose numeric score - use qualitative assessment instead
            "feedback": feedback_formatted,
            "rubric": [
                {
                    "criterion": "Overall Assessment",
                    "score": 0.0,  # Don't expose numeric score
                    "feedback": feedback_formatted
                }
            ]
        }
        
        return updated_state, grading_result
    except Exception as e:
        logger.error(
            "grade_current_block_failed",
            session_id=state.get("session_id"),
            error_type=type(e).__name__,
            error_message=str(e)[:200]
        )
        raise


def call_handle_mic(
    state: Dict[str, Any],
    audio_path: str,
    client: OpenAI,
    dependencies: Dict[str, Any]
) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
    """
    Call handle_mic and extract relevant data for API response.
    
    Args:
        state: State dictionary
        audio_path: Path to audio file
        client: OpenAI client
        dependencies: Dependencies dictionary
        
    Returns:
        Tuple of (updated_state, transcript, features)
    """
    gr_module = MockGradioModule()
    
    try:
        result = handle_mic(
            audio_path=audio_path,
            s=state,
            gr_module=gr_module,
            client=client,
            dependencies=dependencies
        )
        
        # Extract state (first element)
        updated_state = result[0] if result else state
        
        # Extract transcript from multiple sources (fallback chain)
        transcript = ""
        
        # Try 1: Get from answers_tslog_all (most reliable - timestamped log)
        answers = updated_state.get("answers_tslog_all", [])
        if answers:
            transcript = answers[-1].get("text", "")
        
        # Try 2: Get from current answers (if answers_tslog_all is empty)
        if not transcript:
            current_answers = updated_state.get("current", {}).get("answers", [])
            if current_answers:
                transcript = current_answers[-1] if isinstance(current_answers[-1], str) else ""
        
        # Try 3: Get from history (last user message)
        if not transcript:
            history = updated_state.get("history", [])
            for msg in reversed(history):
                if isinstance(msg, dict) and msg.get("role") == "user":
                    content = msg.get("content", "")
                    # Skip processing messages
                    if content and "🎤 Processing" not in content and "📴 Offline" not in content:
                        transcript = content
                        break
        
        # Log if transcript is still empty
        if not transcript:
            logger.warning(
                "transcript_not_found",
                session_id=state.get("session_id"),
                has_answers_tslog=bool(answers),
                has_current_answers=bool(updated_state.get("current", {}).get("answers")),
                history_length=len(updated_state.get("history", [])),
                message="Could not extract transcript from state"
            )
        
        # Extract audio features (simplified)
        features = {
            "duration": updated_state.get("last_audio_duration", 0),
            "voiceprint_match": 1.0,  # Placeholder
            "stylometry_score": 1.0,  # Placeholder
        }
        
        return updated_state, transcript, features
    except Exception as e:
        logger.error(
            "handle_mic_failed",
            session_id=state.get("session_id"),
            error_type=type(e).__name__,
            error_message=str(e)[:200]
        )
        raise

