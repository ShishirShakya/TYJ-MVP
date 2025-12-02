"""
API Mode Adapters for routing OpenAI calls through FastAPI backend.

This module provides adapter functions that route OpenAI API calls through
the FastAPI backend when API mode is enabled, with automatic fallback to
direct OpenAI calls if the API is unavailable.

DEPENDENCY INVERSION: These adapters allow the exam flow to work with either
API mode or standalone mode transparently (Principle #26).
"""

import os
from typing import Dict, Any, Optional, Tuple, List
from openai import OpenAI
import structlog

from exam.api_client import get_api_client, ExamAPIClient
from exam.context_vars import get_course_id, get_exam_id

logger = structlog.get_logger(__name__)


def generate_question_via_api_or_direct(
    s: Dict[str, Any],
    ctx_text: str,
    client: OpenAI,
    api_client: Optional[ExamAPIClient] = None
) -> str:
    """
    Generate question via API if available, otherwise use direct OpenAI call.
    
    Phase 2: Now uses direct API endpoint for question generation.
    
    Args:
        s: State dictionary
        ctx_text: Context chunk text for question generation
        client: OpenAI client (for fallback)
        api_client: Optional API client (if None, will try to get it)
        
    Returns:
        Generated question text
    """
    # Get API client if not provided
    if api_client is None:
        api_client = get_api_client()
    
    # Try API mode first if available
    if api_client:
        try:
            session_id = s.get("session_id", "unknown")
            
            # Extract previous questions from state
            previous_questions_meta = s.get("questions_meta", [])
            previous_questions = [
                q_meta.get("question_text", "")
                for q_meta in previous_questions_meta
                if q_meta.get("question_text")
            ]
            
            # Call API to generate question directly
            question = api_client.generate_question_direct(
                context_text=ctx_text,
                previous_questions=previous_questions,
                session_id=session_id
            )
            
            logger.info(
                "question_generated_via_api",
                session_id=session_id,
                question_length=len(question),
                message="Question generated via API"
            )
            
            return question
            
        except Exception as e:
            logger.warning(
                "api_question_generation_failed",
                session_id=s.get("session_id", "unknown"),
                error=str(e)[:200],
                message="API question generation failed, falling back to direct OpenAI call"
            )
            # Fall through to direct OpenAI call
    
    # Fallback to direct OpenAI call
    from exam.ai.question_generator import _gen_main_question_with_ctx
    return _gen_main_question_with_ctx(s, ctx_text, client=client)


def grade_answer_via_api_or_direct(
    s: Dict[str, Any],
    messages: List[Dict[str, str]],
    client: OpenAI,
    api_client: Optional[ExamAPIClient] = None,
    chat_model: str = "gpt-4o-mini"
) -> Any:
    """
    Grade answer via API if available, otherwise use direct OpenAI call.
    
    Phase 2: Now uses direct API endpoint for answer grading.
    
    Args:
        s: State dictionary
        messages: Chat messages for grading
        client: OpenAI client (for fallback)
        api_client: Optional API client (if None, will try to get it)
        chat_model: Model to use for grading
        
    Returns:
        OpenAI completion response object (for backward compatibility)
        Note: When using API, this creates a mock response object with the parsed results
    """
    # Get API client if not provided
    if api_client is None:
        api_client = get_api_client()
    
    # Try API mode first if available
    if api_client:
        try:
            session_id = s.get("session_id", "unknown")
            
            # Call API to grade answer directly
            scores_dict, feedback_text, overall_score = api_client.grade_answer_direct(
                messages=messages,
                chat_model=chat_model,
                session_id=session_id
            )
            
            logger.info(
                "answer_graded_via_api",
                session_id=session_id,
                overall_score=overall_score,
                message="Answer graded via API"
            )
            
            # Create a mock OpenAI response object for backward compatibility
            # This allows the grading flow to work with the parsed results
            class MockChoice:
                def __init__(self, content):
                    self.message = type('obj', (object,), {'content': content})()
            
            class MockResponse:
                def __init__(self, feedback_text, scores_dict):
                    self.choices = [MockChoice(feedback_text)]
                    # Store parsed scores for later use
                    self._scores_dict = scores_dict
                    self._feedback_text = feedback_text
            
            return MockResponse(feedback_text, scores_dict)
            
        except Exception as e:
            logger.warning(
                "api_grading_failed",
                session_id=s.get("session_id", "unknown"),
                error=str(e)[:200],
                message="API grading failed, falling back to direct OpenAI call"
            )
            # Fall through to direct OpenAI call
    
    # Fallback to direct OpenAI call
    from exam.utils import with_retry
    from shared.circuit_breaker import get_default_circuit_breaker_manager
    
    circuit_breaker_manager = get_default_circuit_breaker_manager()
    circuit_breaker = circuit_breaker_manager.get_breaker("openai_chat") if circuit_breaker_manager else None
    
    return with_retry(
        client.chat.completions.create,
        circuit_breaker=circuit_breaker,
        service_name="openai_chat",
        model=chat_model,
        messages=messages,
        temperature=0.2,
        max_tokens=500
    )


def transcribe_audio_via_api_or_direct(
    audio_path: str,
    s: Dict[str, Any],
    client: OpenAI,
    api_client: Optional[ExamAPIClient] = None
) -> str:
    """
    Transcribe audio via API if available, otherwise use direct OpenAI call.
    
    Args:
        audio_path: Path to audio file
        s: State dictionary
        client: OpenAI client (for fallback)
        api_client: Optional API client (if None, will try to get it)
        
    Returns:
        Transcribed text
    """
    # Get API client if not provided
    if api_client is None:
        api_client = get_api_client()
    
    # Try API mode first if available
    if api_client:
        try:
            session_id = s.get("session_id", "unknown")
            
            # Call API to process audio (includes transcription)
            transcript, features = api_client.process_audio(
                session_id=session_id,
                audio_path=audio_path
            )
            
            logger.info(
                "audio_transcribed_via_api",
                session_id=session_id,
                transcript_length=len(transcript),
                message="Audio transcribed via API"
            )
            
            return transcript
            
        except Exception as e:
            logger.warning(
                "api_transcription_failed",
                session_id=s.get("session_id", "unknown"),
                error=str(e)[:200],
                message="API transcription failed, falling back to direct OpenAI call"
            )
            # Fall through to direct OpenAI call
    
    # Fallback to direct OpenAI call
    from exam.audio.stt import transcribe
    return transcribe(audio_path, client, s)


def generate_followup_question_via_api_or_direct(
    s: Dict[str, Any],
    last_answer: str,
    client: OpenAI,
    api_client: Optional[ExamAPIClient] = None
) -> str:
    """
    Generate follow-up question via API if available, otherwise use direct OpenAI call.
    
    Phase 3.2: Now uses API endpoint for follow-up question generation.
    
    Args:
        s: State dictionary
        last_answer: Student's last answer
        client: OpenAI client (for fallback)
        api_client: Optional API client (if None, will try to get it)
        
    Returns:
        Generated follow-up question text
    """
    # Get API client if not provided
    if api_client is None:
        api_client = get_api_client()
    
    # Try API mode first if available
    if api_client:
        try:
            session_id = s.get("session_id", "unknown")
            
            # Extract main question and context from state
            main_question = s.get("current", {}).get("main_question", "")
            context_text = s.get("current", {}).get("ctx")
            
            # Extract previous follow-ups from state
            previous_followups = []
            # Check if there are any follow-up questions in history
            history = s.get("history", [])
            for msg in history:
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    # Simple heuristic: if it's a question and not the main question
                    if "?" in content and content != main_question:
                        previous_followups.append(content)
            
            # Call API to generate follow-up question directly
            question = api_client.generate_followup_question_direct(
                main_question=main_question,
                student_answer=last_answer,
                context_text=context_text,
                previous_followups=previous_followups[-2:] if previous_followups else [],  # Only last 2
                session_id=session_id
            )
            
            logger.info(
                "followup_question_generated_via_api",
                session_id=session_id,
                question_length=len(question),
                message="Follow-up question generated via API"
            )
            
            return question
            
        except Exception as e:
            logger.warning(
                "api_followup_generation_failed",
                session_id=s.get("session_id", "unknown"),
                error=str(e)[:200],
                message="API follow-up question generation failed, falling back to direct OpenAI call"
            )
            # Fall through to direct OpenAI call
    
    # Fallback to direct OpenAI call
    from exam.ai.question_generator import _gen_followup
    return _gen_followup(s, last_answer, client=client)


def generate_tts_via_api_or_direct(
    text: str,
    client: OpenAI,
    s: Optional[Dict[str, Any]] = None,
    api_client: Optional[ExamAPIClient] = None,
    progress: Optional[callable] = None
) -> str:
    """
    Generate TTS audio via API if available, otherwise use direct OpenAI call.
    
    Phase 3.2: Now uses API endpoint for TTS generation.
    
    Args:
        text: Text to convert to speech
        client: OpenAI client (for fallback)
        s: Optional state dictionary
        api_client: Optional API client (if None, will try to get it)
        progress: Optional progress callback
        
    Returns:
        Path to generated audio file
    """
    # Get API client if not provided
    if api_client is None:
        api_client = get_api_client()
    
    # Try API mode first if available
    if api_client:
        try:
            session_id = s.get("session_id", "unknown") if s else "unknown"
            
            # Call API to generate TTS
            audio_path = api_client.generate_tts(
                text=text,
                session_id=session_id
            )
            
            logger.info(
                "tts_generated_via_api",
                session_id=session_id,
                text_length=len(text),
                audio_path=audio_path,
                message="TTS generated via API"
            )
            
            # Track temp file in state if available
            if s is not None:
                s.setdefault("_tmp_files", []).append(audio_path)
            
            if progress:
                progress(1.0)
            
            return audio_path
            
        except Exception as e:
            logger.warning(
                "api_tts_failed",
                session_id=s.get("session_id", "unknown") if s else "unknown",
                error=str(e)[:200],
                message="API TTS generation failed, falling back to direct OpenAI call"
            )
            # Fall through to direct OpenAI call
    
    # Fallback to direct OpenAI call
    from exam.audio.tts import tts_to_mp3
    return tts_to_mp3(text, client, s, progress=progress)

