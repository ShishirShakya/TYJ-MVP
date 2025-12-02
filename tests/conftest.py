"""
Pytest configuration and shared fixtures.

This module provides fixtures for testing while preserving the dependency injection
wiring pattern used throughout the codebase.
"""

import pytest
import uuid
from typing import Dict, Any
from unittest.mock import Mock, MagicMock
from datetime import datetime, timezone

# Import dependency builders to preserve wiring
from exam.state.core import ensure_state


@pytest.fixture
def mock_state() -> Dict[str, Any]:
    """
    Create a minimal mock state dictionary for testing.
    
    Returns:
        Dictionary with required state fields initialized
    """
    return {
        "session_id": str(uuid.uuid4()),
        "student_id": "test_student_123",
        "ip_address": "127.0.0.1",
        "history": [],
        "asked_main": 0,
        "scores": [],
        "rubrics": [],
        "limit": 1,
        "followups_min": 0,
        "followups_max": 1,
        "passphrase": "test_passphrase",
        "course_id": "TEST_COURSE",
        "exam_id": "TEST_EXAM",
        "section_id": "TEST_SECTION",
        "phase": "idle",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "session_start_time": 1000.0,
        "flags": [],
        "consent": False,
        "security_events": [],
        "tab_focus_events": [],
        "clipboard_events": [],
        "last_auto_save_time": 0,
        "network_status": "online",
        "last_network_check": 0,
        "queued_answers": [],
        "network_check_interval": 5,
        "ready_for_question": False,
        "current": {
            "main_question": None,
            "answers": [],
            "followups_done": 0,
            "target_followups": 0,
            "q_time": None,
            "short_attempts": 0,
            "ctx": None
        },
        "answers_tslog_all": [],
        "otet": None,
        "proctor_state": None,
        "proctor_summary": {},
        "proctor_blocks": [],
        "answer_hashes": [],
        "answer_texts": [],
        "used_context_hashes": set(),
        "questions_meta": [],
        "token_usage": [],
    }


@pytest.fixture
def mock_openai_client():
    """
    Create a mock OpenAI client for testing.
    
    Returns:
        Mock OpenAI client with common methods
    """
    client = Mock()
    
    # Mock chat completion response
    mock_response = Mock()
    mock_response.usage = Mock()
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    mock_response.usage.total_tokens = 150
    mock_response.model = "gpt-4o-mini"
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = "Test response"
    
    client.chat.completions.create.return_value = mock_response
    
    # Mock audio transcription
    mock_transcription = Mock()
    mock_transcription.text = "Test transcription"
    client.audio.transcriptions.create.return_value = mock_transcription
    
    # Mock TTS
    mock_audio = b"fake_audio_data"
    client.audio.speech.create.return_value = Mock(content=mock_audio)
    
    return client


@pytest.fixture
def mock_gradio_module():
    """
    Create a mock Gradio module for testing.
    
    Returns:
        Mock Gradio module with common update methods
    """
    gr = Mock()
    gr.update = Mock(return_value={})
    return gr


@pytest.fixture
def mock_dependencies_exam_flow() -> Dict[str, Any]:
    """
    Create a mock dependencies dictionary for exam flow functions.
    
    This preserves the exact structure used in production _build_flow_dependencies().
    
    Returns:
        Dictionary with all dependencies needed by exam flow functions
    """
    from exam.state.core import ensure_state, reset_current_block, get_followup_range
    from exam.state.persistence import save_state_to_disk
    from exam.file_utils import _paths_for_session
    from exam.utils import with_retry, _log_token_usage, _sanitize_for_prompt
    from shared.rate_limiting import RateLimiter, RateLimitConfig
    try:
        from shared.rate_limiting_helpers import check_rate_limit_for_state
    except ImportError:
        # Fallback if module doesn't exist
        def check_rate_limit_for_state(*args, **kwargs):
            return True, None
    from shared.time_provider import MockTimeProvider, RealTimeProvider
    from shared.idempotency import IdempotencyTracker
    from shared.circuit_breaker import CircuitBreakerManager
    
    # Mock functions that aren't easily testable
    mock_get_chunks = Mock(return_value=[])
    mock_validate_chunks = Mock(return_value=(True, "", 0))
    mock_validate_context = Mock(return_value=(True, ""))
    mock_gen_question = Mock(return_value="Test question")
    mock_gen_followup = Mock(return_value="Test followup")
    # _parse_feedback returns tuple: (scores_dict, feedback_text)
    mock_parse_feedback = Mock(return_value=(
        {"Conceptual": 85, "Analytical": 85, "Application": 85, "Reflection": 85, "Overall": 85},
        "Good answer"
    ))
    mock_calculate_score = Mock(return_value=85)
    # msgs_from_state should return a list of messages, and may modify state["history"]
    def mock_msgs_from_state(s, operation_type="feedback"):
        # Defensive check: ensure s is a dict before modifying
        if not isinstance(s, dict):
            # If s is not a dict, return minimal messages without modifying
            # This prevents 'str' object does not support item assignment errors
            return [{"role": "system", "content": "Test system prompt"}]
        # Ensure history is a list (defensive check)
        # Double-check s is still a dict before modifying
        if isinstance(s, dict) and not isinstance(s.get("history"), list):
            try:
                s["history"] = []
            except (TypeError, AttributeError):
                # If s became non-dict or assignment fails, just return messages
                pass
        # Return mock messages list
        return [{"role": "system", "content": "Test system prompt"}]
    mock_tts = Mock(return_value="/tmp/test.mp3")
    mock_transcribe = Mock(return_value="Test transcription")
    mock_get_duration = Mock(return_value=5.0)
    mock_calculate_timeout = Mock(return_value={})
    mock_proctor_updates = Mock(return_value=({}, {}))
    mock_get_max_timeout = Mock(return_value=300)
    mock_categorize_error = Mock(return_value=("UNKNOWN_ERROR", {"message": "Unknown error"}))
    mock_detect_profanity = Mock(return_value=False)
    mock_count_words = Mock(return_value=10)
    mock_detect_reuse = Mock(return_value=False)
    mock_hash_answer = Mock(return_value="hash123")
    mock_update_network = Mock(return_value="online")
    mock_queue_answer = Mock(return_value=False)
    mock_paths = Mock(return_value={"STATE_PATH": "/tmp/test_state.json"})
    
    # Import config constants
    from exam.config import CHAT_MODEL
    from shared.config.prompts import FEEDBACK_BLOCK_INSTR
    
    # Import flow functions for handle_mic dependencies
    from exam.flow.questions import ask_followup_question
    from exam.flow.grading import grade_current_block
    
    # Create wrapper functions that use the same dependencies pattern
    def mock_ask_followup(s, gr_module, client, dependencies, progress=None):
        return ask_followup_question(s, gr_module, client, dependencies, progress)
    
    def mock_grade_block(s, gr_module, client, dependencies, progress=None):
        return grade_current_block(s, gr_module, client, dependencies, progress)
    
    # Rate limiting with permissive config for tests
    test_rate_limiter = RateLimiter("test", RateLimitConfig(
        requests_per_minute=1000,  # Very high for tests
        requests_per_hour=100000,
        burst_size=1000
    ))
    
    # Time provider (mock for deterministic tests)
    test_time_provider = MockTimeProvider(initial_time=1000.0)
    
    # Idempotency tracker
    test_idempotency_tracker = IdempotencyTracker()
    
    # Circuit breaker manager
    test_circuit_breaker_manager = CircuitBreakerManager()
    
    return {
        # State management
        "ensure_state": ensure_state,
        "reset_current_block": reset_current_block,
        "get_followup_range": get_followup_range,
        "save_state_to_disk": Mock(return_value=True),
        "_paths_for_session": _paths_for_session,
        
        # PDF and chunks
        "get_chunks": mock_get_chunks,
        "validate_chunks_available": mock_validate_chunks,
        "_validate_context": mock_validate_context,
        
        # AI functions
        "_gen_main_question_with_ctx": mock_gen_question,
        "_gen_followup": mock_gen_followup,
        "_parse_feedback": mock_parse_feedback,
        "_calculate_overall_score": mock_calculate_score,
        "msgs_from_state": mock_msgs_from_state,
        "with_retry": with_retry,
        "_log_token_usage": _log_token_usage,
        "_sanitize_for_prompt": _sanitize_for_prompt,
        
        # Audio functions
        "tts_to_mp3": mock_tts,
        "transcribe": mock_transcribe,
        "get_audio_duration": mock_get_duration,
        "extract_audio_features": None,
        "compare_voiceprints": None,
        "analyze_speech_stylometry": Mock(return_value={}),
        
        # UI helpers
        "_calculate_timeout_status": mock_calculate_timeout,
        "_proctor_end_updates": mock_proctor_updates,
        "get_max_answer_timeout_sec": mock_get_max_timeout,
        "_categorize_error": mock_categorize_error,
        
        # Answer validation
        "_detect_profanity": mock_detect_profanity,
        "_count_meaningful_words": mock_count_words,
        "_detect_answer_reuse": mock_detect_reuse,
        "_hash_answer": mock_hash_answer,
        
        # Network and persistence
        "update_network_status": mock_update_network,
        "queue_answer_locally": mock_queue_answer,
        "_paths_for_session": mock_paths,
        
        # Flow functions (required by handle_mic)
        "ask_followup_question": mock_ask_followup,
        "grade_current_block": mock_grade_block,
        
        # Constants
        "CHAT_MODEL": CHAT_MODEL,
        "FEEDBACK_BLOCK_INSTR": FEEDBACK_BLOCK_INSTR,
        "MAX_SESSION_DURATION_SEC": 3600,
        "MIN_WORDS": 5,
        "MAX_SHORT_ATTEMPTS": 3,
        "SHORT_PROMPT_TTS": "Please provide a longer answer.",
        
        # Rate limiting
        "rate_limiter": test_rate_limiter,
        "check_rate_limit_for_state": check_rate_limit_for_state,
        
        # Time provider
        "time_provider": test_time_provider,
        
        # Idempotency
        "idempotency_tracker": test_idempotency_tracker,
        
        # Circuit breaker
        "circuit_breaker_manager": test_circuit_breaker_manager,
        
        # Proctor state
        "ProctorState": Mock,
    }


@pytest.fixture
def mock_dependencies_dash() -> Dict[str, Any]:
    """
    Create a mock dependencies dictionary for dash handlers.
    
    This preserves the exact structure used in production _build_dash_dependencies().
    
    Returns:
        Dictionary with all dependencies needed by dash handlers
    """
    from shared.config_parsing import parse_professor_link_and_setup
    
    return {
        "parse_professor_link_and_setup": parse_professor_link_and_setup,
        "batch_csv_summarize": Mock(return_value=[]),
        "instructor_decrypt": Mock(return_value=("", "")),
        "_parse_plaintext_fields": Mock(return_value={}),
        "_parse_rubric_scores": Mock(return_value=[]),
        "_safe_path": Mock(return_value="/tmp/test"),
        "_statistical_normalization": Mock(return_value=[]),
        "_percentile_curving": Mock(return_value=[]),
        "_confidence_adjustment": Mock(return_value=[]),
        "_calculate_confidence_score": Mock(return_value=0.5),
        "_cleanup_expired_cache": Mock(),
        "_is_cache_entry_valid": Mock(return_value=True),
        "_obfuscate_session_id": Mock(return_value="obfuscated"),
        "get_cache_entry": Mock(return_value=None),
        "set_cache_entry": Mock(),
        "convert_csv_to_excel": Mock(return_value=b"excel_data"),
        "get_csv_column_list": Mock(return_value=[]),
        "TRANSCRIPT_CACHE_TIMEOUT_SECONDS": 3600,
    }


@pytest.fixture
def mock_dependencies_prof() -> Dict[str, Any]:
    """
    Create a mock dependencies dictionary for prof handlers.
    
    This preserves the exact structure used in production _build_prof_dependencies().
    
    Returns:
        Dictionary with all dependencies needed by prof handlers
    """
    return {
        "validate_pdf_and_calculate_chunks": Mock(return_value=("", 0)),
        "encode_config_to_url": Mock(return_value="https://test.url"),
        "generate_secure_passphrase": Mock(return_value="test_passphrase"),
        "calculate_max_duration": Mock(return_value=300),
        "combine_date_time": Mock(return_value="2024-01-01T00:00:00"),
        "format_duration_display": Mock(return_value="5 minutes"),
        "format_pdf_status_message": Mock(return_value="✅ Valid PDF"),
    }

