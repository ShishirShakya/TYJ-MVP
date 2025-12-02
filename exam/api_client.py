"""
API Client for communicating with FastAPI backend.

This module provides a client interface for exam.py to communicate with the
FastAPI backend when EXAM_API_MODE is enabled.

DEPENDENCY INVERSION: This module acts as an adapter between exam.py and the
FastAPI backend, allowing both to evolve independently (Principle #26).
"""

import os
import requests
import json
from typing import Dict, Any, Optional, Tuple, List
from pathlib import Path
import structlog

from shared.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    get_default_circuit_breaker_manager
)

logger = structlog.get_logger(__name__)


class ExamAPIClient:
    """
    Client for communicating with VivaAI Assessment API.
    
    This client handles:
    - Question generation
    - Answer grading
    - Audio processing
    - Proctoring analysis
    - Error handling and retries
    """
    
    def __init__(self, api_url: str, api_key: str, timeout: int = 30):
        """
        Initialize API client.
        
        Args:
            api_url: Base URL of the API (e.g., "http://localhost:8000")
            api_key: API key for authentication
            timeout: Request timeout in seconds (default: 30)
        """
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-Key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        
        # Phase 2.2.1: Initialize circuit breaker for API calls
        # Use default circuit breaker manager if available, otherwise create one
        try:
            manager = get_default_circuit_breaker_manager()
            self.circuit_breaker = manager.get_breaker("api_client")
            if self.circuit_breaker is None:
                # Create new circuit breaker if not in manager
                self.circuit_breaker = CircuitBreaker(
                    "api_client",
                    config=CircuitBreakerConfig(
                        failure_threshold=5,
                        success_threshold=2,
                        timeout_seconds=60.0,
                        expected_exception=(requests.RequestException, ValueError)
                    )
                )
                manager.add_breaker("api_client", self.circuit_breaker)
        except Exception:
            # Fallback: create standalone circuit breaker
            self.circuit_breaker = CircuitBreaker(
                "api_client",
                config=CircuitBreakerConfig(
                    failure_threshold=5,
                    success_threshold=2,
                    timeout_seconds=60.0,
                    expected_exception=(requests.RequestException, ValueError)
                )
            )
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make HTTP request to API endpoint with retry logic and circuit breaker protection.
        
        Phase 2.2.1: Circuit breaker integrated to prevent cascading failures.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (e.g., "/api/v1/assessments/generate-question")
            data: Request data (for JSON requests)
            files: Files to upload (for multipart requests)
            max_retries: Maximum number of retry attempts (default: 3)
            retry_delay: Base delay between retries in seconds (default: 1.0)
            **kwargs: Additional arguments for requests
            
        Returns:
            Response JSON as dictionary
            
        Raises:
            CircuitBreakerOpenError: If circuit breaker is open
            requests.RequestException: If request fails
            ValueError: If response is invalid after all retries
        """
        import time
        import random
        
        # Phase 2.2.1: Wrap request logic with circuit breaker
        def _execute_request():
            """Inner function to execute the actual HTTP request."""
            url = f"{self.api_url}{endpoint}"
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    if files:
                        # Multipart request (for file uploads)
                        response = self.session.request(
                            method,
                            url,
                            data=data,
                            files=files,
                            timeout=self.timeout,
                            **kwargs
                        )
                    else:
                        # JSON request
                        response = self.session.request(
                            method,
                            url,
                            json=data,
                            timeout=self.timeout,
                            **kwargs
                        )
                    
                    # Check for errors
                    response.raise_for_status()
                    
                    # Parse JSON response
                    return response.json()
                    
                except requests.exceptions.Timeout as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        # Exponential backoff: delay * 2^attempt
                        delay = retry_delay * (2 ** attempt)
                        logger.warning(
                            "api_request_timeout_retry",
                            endpoint=endpoint,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            delay=delay,
                            message=f"API request timed out, retrying in {delay}s"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(
                            "api_request_timeout",
                            endpoint=endpoint,
                            timeout=self.timeout,
                            attempts=max_retries,
                            message="API request timed out after all retries"
                        )
                        raise ValueError(f"API request to {endpoint} timed out after {self.timeout}s (attempted {max_retries} times)")
                        
                except requests.exceptions.HTTPError as e:
                    # Don't retry on 4xx errors (client errors) except 429 (rate limit)
                    status_code = e.response.status_code if e.response else 0
                    
                    # Extract error message to check for authentication errors
                    error_msg = "Unknown error"
                    try:
                        if e.response:
                            error_data = e.response.json()
                            error_msg = error_data.get("detail", str(e))
                        else:
                            error_msg = str(e)
                    except:
                        error_msg = str(e)
                    
                    # Don't retry on authentication/authorization errors (401, 403) or invalid API key
                    is_auth_error = (
                        status_code in (401, 403) or 
                        status_code == 0 or  # Connection/auth issues often return 0
                        "invalid api key" in error_msg.lower() or
                        "authentication" in error_msg.lower() or
                        "unauthorized" in error_msg.lower()
                    )
                    
                    if (status_code >= 400 and status_code < 500 and status_code != 429) or is_auth_error:
                        # Client error or auth error - don't retry
                        logger.error(
                            "api_request_failed",
                            endpoint=endpoint,
                            status_code=status_code,
                            error=error_msg,
                            message="API request failed (client/auth error, not retrying)"
                        )
                        raise ValueError(f"API request failed: {error_msg}")
                    
                    # Retry on 429 (rate limit) and 5xx errors
                    last_exception = e
                    if attempt < max_retries - 1:
                        # Exponential backoff with longer delay for rate limits
                        delay = retry_delay * (2 ** attempt)
                        if status_code == 429:
                            delay *= 2  # Longer delay for rate limits
                        
                        logger.warning(
                            "api_request_failed_retry",
                            endpoint=endpoint,
                            status_code=status_code,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            delay=delay,
                            message=f"API request failed with {status_code}, retrying in {delay}s"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        error_msg = "Unknown error"
                        try:
                            error_data = e.response.json()
                            error_msg = error_data.get("detail", str(e))
                        except:
                            error_msg = str(e)
                        
                        logger.error(
                            "api_request_failed",
                            endpoint=endpoint,
                            status_code=status_code,
                            error=error_msg,
                            attempts=max_retries,
                            message="API request failed after all retries"
                        )
                        raise ValueError(f"API request failed: {error_msg}")
                        
                except requests.exceptions.RequestException as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        # Exponential backoff for network errors
                        delay = retry_delay * (2 ** attempt)
                        logger.warning(
                            "api_request_error_retry",
                            endpoint=endpoint,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            delay=delay,
                            error=str(e)[:200],
                            message=f"API request error, retrying in {delay}s"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(
                            "api_request_error",
                            endpoint=endpoint,
                            error=str(e),
                            attempts=max_retries,
                            message="API request error after all retries"
                        )
                        raise ValueError(f"API request error: {str(e)}")
            
            # Should never reach here, but just in case
            if last_exception:
                raise ValueError(f"API request failed after {max_retries} attempts: {str(last_exception)}")
        
        # Phase 2.2.1: Execute request through circuit breaker
        try:
            return self.circuit_breaker.call(_execute_request)
        except CircuitBreakerOpenError as e:
            # Circuit breaker is open - log and re-raise
            logger.warning(
                "circuit_breaker_open",
                endpoint=endpoint,
                circuit_state=self.circuit_breaker.get_state().value,
                message="Circuit breaker is open, rejecting API request"
            )
            raise
    
    def generate_question(
        self,
        session_id: str,
        course_id: str,
        exam_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, str]:
        """
        Generate a question for the student (full flow endpoint).
        
        Args:
            session_id: Student session ID
            course_id: Course identifier
            exam_id: Exam identifier
            context: Optional additional context
            
        Returns:
            Tuple of (question_text, question_id)
        """
        data = {
            "session_id": session_id,
            "course_id": course_id,
            "exam_id": exam_id,
            "context": context or {}
        }
        
        response = self._make_request(
            "POST",
            "/api/v1/assessments/generate-question",
            data=data
        )
        
        return response["question"], response["question_id"]
    
    def generate_question_direct(
        self,
        context_text: str,
        previous_questions: Optional[List[str]] = None,
        session_id: Optional[str] = None
    ) -> str:
        """
        Generate a question directly from context (low-level OpenAI wrapper).
        
        Phase 2: Direct question generation endpoint for internal use.
        
        Args:
            context_text: Context chunk text for question generation
            previous_questions: List of previous questions to avoid duplicates
            session_id: Optional session ID for logging
            
        Returns:
            Generated question text
        """
        data = {
            "context_text": context_text,
            "previous_questions": previous_questions or [],
            "session_id": session_id
        }
        
        response = self._make_request(
            "POST",
            "/api/v1/assessments/generate-question-direct",
            data=data
        )
        
        return response["question"]
    
    def grade_answer(
        self,
        session_id: str,
        answer: str,
        question_id: str,
        audio_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Grade a student's answer (full flow endpoint).
        
        Args:
            session_id: Student session ID
            answer: Student's answer text
            question_id: Question identifier
            audio_path: Optional path to audio recording
            
        Returns:
            Dictionary with score, feedback, and rubric
        """
        data = {
            "session_id": session_id,
            "answer": answer,
            "question_id": question_id,
            "audio_path": audio_path
        }
        
        response = self._make_request(
            "POST",
            "/api/v1/assessments/grade",
            data=data
        )
        
        return response
    
    def grade_answer_direct(
        self,
        messages: List[Dict[str, str]],
        chat_model: str = "gpt-4o-mini",
        session_id: Optional[str] = None
    ) -> Tuple[Dict[str, int], str, int]:
        """
        Grade an answer directly from messages (low-level OpenAI wrapper).
        
        Phase 2: Direct answer grading endpoint for internal use.
        
        Args:
            messages: Chat messages for grading
            chat_model: Model to use for grading
            session_id: Optional session ID for logging
            
        Returns:
            Tuple of (scores_dict, feedback_text, overall_score)
        """
        data = {
            "messages": messages,
            "chat_model": chat_model,
            "session_id": session_id
        }
        
        response = self._make_request(
            "POST",
            "/api/v1/assessments/grade-answer-direct",
            data=data
        )
        
        return (
            response["scores_dict"],
            response["feedback_text"],
            response["overall_score"]
        )
    
    def process_audio(
        self,
        session_id: str,
        audio_path: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Process audio recording (transcription and feature extraction).
        
        Args:
            session_id: Student session ID
            audio_path: Path to audio file
            
        Returns:
            Tuple of (transcript, features_dict)
        """
        # Read audio file
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise ValueError(f"Audio file not found: {audio_path}")
        
        # Determine content type from file extension
        ext = audio_file.suffix.lower()
        content_type_map = {
            '.wav': 'audio/wav',
            '.mp3': 'audio/mpeg',
            '.m4a': 'audio/mp4',
            '.ogg': 'audio/ogg',
        }
        content_type = content_type_map.get(ext, 'audio/wav')
        
        with open(audio_file, 'rb') as f:
            files = {
                "audio_file": (audio_file.name, f, content_type)
            }
            data = {
                "session_id": session_id
            }
            
            # Remove Content-Type header for multipart requests
            headers = {k: v for k, v in self.session.headers.items() if k.lower() != 'content-type'}
            
            response = self.session.post(
                f"{self.api_url}/api/v1/assessments/process-audio",
                data=data,
                files=files,
                headers=headers,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            result = response.json()
        
        return result["transcript"], result["features"]
    
    def analyze_proctor(
        self,
        session_id: str,
        frame_data: str,
        timestamp: float
    ) -> Dict[str, Any]:
        """
        Analyze proctoring frame for violations.
        
        Args:
            session_id: Student session ID
            frame_data: Base64-encoded video frame
            timestamp: Frame timestamp
            
        Returns:
            Dictionary with violations and analysis results
        """
        data = {
            "session_id": session_id,
            "frame_data": frame_data,
            "timestamp": timestamp
        }
        
        response = self._make_request(
            "POST",
            "/api/v1/assessments/analyze-proctor",
            data=data
        )
        
        return response
    
    def health_check(self) -> bool:
        """
        Check if API is healthy and accessible.
        
        Returns:
            True if API is healthy, False otherwise
        """
        try:
            response = self._make_request("GET", "/health")
            return response.get("status") == "healthy"
        except Exception:
            return False
    
    def generate_tts(
        self,
        text: str,
        session_id: str = "unknown",
        model: Optional[str] = None,
        voice: Optional[str] = None
    ) -> str:
        """
        Generate text-to-speech audio (low-level OpenAI wrapper).
        
        Phase 3.2: TTS endpoint for API mode integration.
        
        This method handles audio file transfer from API service to exam service
        by decoding base64-encoded audio data and saving it locally, since the
        API and exam services run in separate containers on Railway.
        
        Args:
            text: Text to convert to speech (max 4096 chars)
            session_id: Session ID for temp file management
            model: Optional TTS model (default: tts-1)
            voice: Optional voice (default: alloy)
            
        Returns:
            Path to generated MP3 file (saved locally)
            
        Raises:
            ValueError: If base64 decode fails and audio_path is not accessible
        """
        import tempfile
        import base64
        
        data = {
            "text": text[:4096],  # Truncate to OpenAI limit
            "session_id": session_id,
            "model": model,
            "voice": voice
        }
        response = self._make_request(
            "POST",
            "/api/v1/assessments/generate-tts",
            data=data
        )
        
        # Get base64 audio from response (preferred method for cross-container access)
        audio_base64 = response.get("audio_base64")
        
        if audio_base64:
            # Decode base64 and save locally
            from exam.file_utils import _paths_for_session
            from exam.state.core import ensure_state
            
            state = ensure_state({"session_id": session_id})
            paths = _paths_for_session(state)
            local_tmp_dir = paths.get("TMP_DIR", tempfile.gettempdir())
            os.makedirs(local_tmp_dir, exist_ok=True)
            
            local_audio_path = tempfile.NamedTemporaryFile(
                delete=False, 
                suffix=".mp3", 
                dir=local_tmp_dir
            ).name
            
            try:
                audio_bytes = base64.b64decode(audio_base64)
                with open(local_audio_path, "wb") as f:
                    f.write(audio_bytes)
                
                logger.info(
                    "tts_audio_saved_locally",
                    session_id=session_id,
                    local_path=local_audio_path,
                    message="TTS audio decoded from base64 and saved locally"
                )
                return local_audio_path
            except Exception as e:
                # If base64 decode fails, raise exception to trigger fallback
                logger.warning(
                    "base64_decode_failed",
                    session_id=session_id,
                    error=str(e)[:200],
                    message="Failed to decode base64 audio"
                )
                raise ValueError(f"Failed to decode base64 audio: {e}")
        
        # Fallback: try to use audio_path (works locally, not on Railway)
        # This provides backward compatibility for local development
        api_audio_path = response.get("audio_path")
        if api_audio_path and os.path.exists(api_audio_path):
            logger.info(
                "tts_audio_path_used",
                session_id=session_id,
                api_path=api_audio_path,
                message="Using API audio path (local development mode)"
            )
            return api_audio_path
        
        # If neither works, raise exception to trigger fallback to direct OpenAI
        logger.error(
            "tts_audio_unavailable",
            session_id=session_id,
            has_base64=bool(audio_base64),
            api_path=api_audio_path,
            message="Cannot access audio file from API - base64 decode failed and path not accessible"
        )
        raise ValueError("Cannot access audio file from API - base64 decode failed and path not accessible")
    
    def generate_followup_question_direct(
        self,
        main_question: str,
        student_answer: str,
        context_text: Optional[str] = None,
        previous_followups: Optional[List[str]] = None,
        session_id: str = "unknown"
    ) -> str:
        """
        Generate follow-up question directly (low-level OpenAI wrapper).
        
        Phase 3.2: Follow-up question endpoint for API mode integration.
        
        Args:
            main_question: The main question text
            student_answer: The student's answer to the main question
            context_text: Optional context chunk text
            previous_followups: Optional list of previous follow-up questions
            session_id: Optional session ID for logging
            
        Returns:
            Generated follow-up question text
        """
        data = {
            "main_question": main_question,
            "student_answer": student_answer,
            "context_text": context_text,
            "previous_followups": previous_followups or [],
            "session_id": session_id
        }
        response = self._make_request(
            "POST",
            "/api/v1/assessments/generate-followup-question-direct",
            data=data
        )
        return response["question"]
    
    def get_circuit_breaker_stats(self) -> Dict[str, Any]:
        """
        Get circuit breaker statistics for monitoring.
        
        Phase 2.2.1: Circuit breaker monitoring.
        
        Returns:
            Dictionary with circuit breaker statistics
        """
        return self.circuit_breaker.get_stats()


def get_api_client() -> Optional[ExamAPIClient]:
    """
    Get API client instance if API mode is enabled.
    
    API mode is enabled automatically if API_BASE_URL is set (uses your existing variable naming).
    Supports both naming conventions:
    - API_BASE_URL + API_KEY (your existing variables)
    - EXAM_API_URL + EXAM_API_KEY (alternative naming)
    
    Returns:
        ExamAPIClient instance if API mode is enabled, None otherwise
    """
    # Check for API_BASE_URL first (your existing variable), then fallback to EXAM_API_URL
    api_url = os.getenv("API_BASE_URL") or os.getenv("EXAM_API_URL")
    if not api_url:
        return None  # API mode disabled - no API URL set
    
    # Get API key (check API_KEY first, then EXAM_API_KEY)
    api_key = os.getenv("API_KEY") or os.getenv("EXAM_API_KEY")
    
    if not api_key:
        logger.warning(
            "api_mode_enabled_but_no_key",
            api_url=api_url,
            message="API_BASE_URL/EXAM_API_URL is set but API_KEY/EXAM_API_KEY is not set"
        )
        return None
    
    return ExamAPIClient(api_url=api_url, api_key=api_key)

