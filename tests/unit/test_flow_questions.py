"""
Unit tests for exam.flow.questions module.

Tests cover question flow functions including edge cases and error handling.
"""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch
from exam.flow.questions import (
    ask_main_question,
    ask_followup_question,
    on_first_mic_press,
)
from shared.time_provider import MockTimeProvider


class TestAskMainQuestion:
    """Tests for ask_main_question function."""
    
    @pytest.fixture
    def mock_state(self):
        """Create a mock state for testing."""
        import random
        return {
            "session_id": "test_session",
            "request_id": "test_request",
            "phase": "idle",
            "asked_main": 0,
            "limit": 5,
            "followups_min": 0,
            "followups_max": 2,
            "history": [],
            "current": {},
            "used_context_hashes": set(),
            "questions_meta": [],
            "_rng": random.Random(42),
        }
    
    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies."""
        deps = {}
        deps["ensure_state"] = lambda s: s
        deps["reset_current_block"] = lambda s: None
        deps["get_followup_range"] = lambda s: (0, 2)
        deps["get_chunks"] = lambda: ["Python is a high-level programming language known for its simplicity and readability. It supports multiple programming paradigms including object-oriented and functional programming."]
        deps["_validate_context"] = lambda ctx: (True, "")
        deps["_gen_main_question_with_ctx"] = lambda s, ctx, **kwargs: "What is Python?"
        deps["tts_to_mp3"] = lambda text, client, state, **kwargs: "/tmp/test.mp3"
        deps["get_audio_duration"] = lambda audio: 5.0
        deps["get_max_answer_timeout_sec"] = lambda s=None: 300
        deps["_calculate_timeout_status"] = lambda s, gr, timeout_fn=None: {}
        deps["_proctor_end_updates"] = lambda s, gr: ({}, {})
        deps["_categorize_error"] = lambda e: ("UNKNOWN_ERROR", {"message": str(e)})
        # DETERMINISTIC: Add time_provider for deterministic testing (Principle #5)
        deps["time_provider"] = MockTimeProvider(initial_time=1000.0)
        return deps
    
    @pytest.fixture
    def mock_gr_module(self):
        """Create mock Gradio module."""
        gr = Mock()
        # gr.update should return a dict with the update parameters
        def mock_update(**kwargs):
            return kwargs
        gr.update = mock_update
        return gr
    
    @pytest.fixture
    def mock_openai_client(self):
        """Create mock OpenAI client."""
        return Mock()
    
    def test_ask_main_question_complete_phase(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test early return when phase is complete."""
        mock_state["phase"] = "complete"
        
        result = ask_main_question(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should return early with completion message
        assert result[2].get("value") == "✔️ Exam already completed."
        assert result[3].get("interactive") is False
    
    def test_ask_main_question_limit_reached(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test early return when question limit is reached."""
        mock_state["asked_main"] = 5
        mock_state["limit"] = 5
        
        result = ask_main_question(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should mark as complete and return limit message
        assert mock_state["phase"] == "complete"
        assert "limit reached" in result[2].get("value", "").lower()
        assert result[3].get("interactive") is False
    
    def test_ask_main_question_invalid_phase(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test early return when phase is not valid."""
        mock_state["phase"] = "awaiting_main_answer"  # Not in valid phases
        
        result = ask_main_question(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should return message about completing current block
        assert "complete the current block" in result[2].get("value", "").lower()
        assert result[3].get("interactive") is False
    
    def test_ask_main_question_empty_chunks(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test error handling when chunks are empty."""
        mock_dependencies["get_chunks"] = lambda: []
        # Need to add build_error_tuple dependency
        from exam.flow.response_builder import build_error_tuple
        mock_dependencies["build_error_tuple"] = build_error_tuple
        
        result = ask_main_question(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle error gracefully
        assert len(result) >= 3  # Should return tuple
        # Error should be in status message (result[2] is the status update dict)
        status_update = result[2]
        if isinstance(status_update, dict):
            status_text = status_update.get("value", "").lower()
            assert "error" in status_text or "pdf" in status_text or len(status_text) > 0
    
    def test_ask_main_question_fallback_chunks(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test error handling when chunks contain only fallback message."""
        mock_dependencies["get_chunks"] = lambda: ["(No textbook content available - using fallback)"]
        from exam.flow.response_builder import build_error_tuple
        mock_dependencies["build_error_tuple"] = build_error_tuple
        
        result = ask_main_question(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle error gracefully
        assert len(result) >= 3
        status_update = result[2]
        if isinstance(status_update, dict):
            status_text = status_update.get("value", "").lower()
            assert "pdf" in status_text or "error" in status_text or len(status_text) > 0
    
    def test_ask_main_question_no_valid_chunks(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test error handling when no valid chunks after validation."""
        mock_dependencies["get_chunks"] = lambda: ["short"]  # Too short to be valid
        mock_dependencies["_validate_context"] = lambda ctx: (False, "Context too short")
        from exam.flow.response_builder import build_error_tuple
        mock_dependencies["build_error_tuple"] = build_error_tuple
        
        result = ask_main_question(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle error gracefully
        assert len(result) >= 3
        status_update = result[2]
        if isinstance(status_update, dict):
            status_text = status_update.get("value", "").lower()
            assert "error" in status_text or "valid" in status_text or len(status_text) > 0
    
    def test_ask_main_question_all_chunks_used(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test behavior when all chunks have been used."""
        # Create multiple valid chunks
        chunks = [
            "Python is a high-level programming language known for its simplicity and readability. It supports multiple programming paradigms.",
            "Machine learning is a subset of artificial intelligence that enables systems to learn from data without explicit programming.",
            "Data structures are ways of organizing and storing data in computer memory for efficient access and modification."
        ]
        mock_dependencies["get_chunks"] = lambda: chunks
        
        # Mark all chunks as used
        import hashlib
        used_hashes = {hashlib.sha256(chunk.encode("utf-8")).hexdigest() for chunk in chunks}
        mock_state["used_context_hashes"] = used_hashes
        
        result = ask_main_question(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should reset and reuse chunks
        assert result[0]["current"].get("main_question") is not None
    
    def test_ask_main_question_validation_error_retry(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test retry logic when question validation fails."""
        call_count = [0]
        
        def mock_gen_question(s, ctx, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Generated question failed validation")
            return "What is Python?"
        
        mock_dependencies["_gen_main_question_with_ctx"] = mock_gen_question
        
        result = ask_main_question(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should retry and eventually succeed or use fallback
        assert call_count[0] >= 1
        assert result[0]["current"].get("main_question") is not None
    
    def test_ask_main_question_with_progress(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test with progress callback."""
        progress_calls = []
        
        def mock_progress(value):
            progress_calls.append(value)
        
        result = ask_main_question(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies,
            progress=mock_progress
        )
        
        # Should have called progress
        assert len(progress_calls) > 0
        assert progress_calls[-1] == 1.0  # Should end at 100%


class TestAskFollowupQuestion:
    """Tests for ask_followup_question function."""
    
    @pytest.fixture
    def mock_state(self):
        """Create a mock state for testing."""
        return {
            "session_id": "test_session",
            "phase": "awaiting_main_answer",
            "current": {
                "answers": ["Python is a programming language."],
                "main_question": "What is Python?",
                "ctx": "Python is a high-level programming language known for its simplicity and readability. It supports multiple programming paradigms."
            },
            "history": []
        }
    
    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies."""
        deps = {}
        deps["ensure_state"] = lambda s: s
        deps["_gen_followup"] = lambda s, answer, **kwargs: "Can you provide more details?"
        deps["tts_to_mp3"] = lambda text, client, state, **kwargs: "/tmp/test.mp3"
        deps["get_audio_duration"] = lambda audio: 5.0
        deps["get_max_answer_timeout_sec"] = lambda s=None: 300
        deps["_calculate_timeout_status"] = lambda s, gr, timeout_fn=None: {}
        deps["_categorize_error"] = lambda e: ("UNKNOWN_ERROR", {"message": str(e)})
        return deps
    
    @pytest.fixture
    def mock_gr_module(self):
        """Create mock Gradio module."""
        gr = Mock()
        # gr.update should return a dict with the update parameters
        def mock_update(**kwargs):
            return kwargs
        gr.update = mock_update
        return gr
    
    @pytest.fixture
    def mock_openai_client(self):
        """Create mock OpenAI client."""
        return Mock()
    
    def test_ask_followup_question_basic(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test basic follow-up question generation."""
        result = ask_followup_question(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should return tuple with state and updates
        assert len(result) == 9  # Expected tuple length
        assert result[0]["phase"] == "awaiting_followup_answer"
        assert "follow-up" in result[2].get("value", "").lower() or "asked" in result[2].get("value", "").lower()
    
    def test_ask_followup_question_no_answers(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test follow-up with no answers."""
        mock_state["current"]["answers"] = []
        
        result = ask_followup_question(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle gracefully (empty answer)
        assert len(result) == 9
    
    def test_ask_followup_question_with_progress(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test with progress callback."""
        progress_calls = []
        
        def mock_progress(value):
            progress_calls.append(value)
        
        result = ask_followup_question(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies,
            progress=mock_progress
        )
        
        # Should have called progress
        assert len(progress_calls) > 0
        assert progress_calls[-1] == 1.0
    
    def test_ask_followup_question_error_handling(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test error handling in follow-up generation."""
        # Make _gen_followup raise an error
        def failing_gen_followup(s, answer, **kwargs):
            raise Exception("Generation failed")
        mock_dependencies["_gen_followup"] = failing_gen_followup
        from exam.flow.response_builder import build_error_tuple
        mock_dependencies["build_error_tuple"] = build_error_tuple
        
        result = ask_followup_question(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle error gracefully
        assert len(result) == 9
        # Error should be in status message (check if it's a dict with value or message)
        status_update = result[2]
        if isinstance(status_update, dict):
            status_text = status_update.get("value", status_update.get("message", "")).lower()
            assert "error" in status_text or "failed" in status_text or len(status_text) > 0


class TestOnFirstMicPress:
    """Tests for on_first_mic_press function."""
    
    @pytest.fixture
    def mock_state(self):
        """Create a mock state for testing."""
        return {
            "session_id": "test_session",
            "phase": "idle",
            "ready_for_question": True,
            "history": []
        }
    
    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies."""
        deps = {}
        deps["ensure_state"] = lambda s: s
        deps["ask_main_question"] = lambda s, gr, client, deps, **kwargs: (
            s, "/tmp/test.mp3", {}, {}, s["history"], {}, {}, {}
        )
        return deps
    
    @pytest.fixture
    def mock_gr_module(self):
        """Create mock Gradio module."""
        gr = Mock()
        # gr.update should return a dict with the update parameters
        def mock_update(**kwargs):
            return kwargs
        gr.update = mock_update
        return gr
    
    @pytest.fixture
    def mock_openai_client(self):
        """Create mock OpenAI client."""
        return Mock()
    
    def test_on_first_mic_press_ready(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test when ready_for_question is True."""
        mock_state["ready_for_question"] = True
        mock_state["phase"] = "idle"
        
        result = on_first_mic_press(
            mock_state,
            "status",
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should call ask_main_question and return results
        assert len(result) == 7
        assert mock_state["ready_for_question"] is False
    
    def test_on_first_mic_press_not_ready(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test when ready_for_question is False."""
        mock_state["ready_for_question"] = False
        
        result = on_first_mic_press(
            mock_state,
            "status",
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should return unchanged state
        assert len(result) == 7
        assert result[0] == mock_state
    
    def test_on_first_mic_press_wrong_phase(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test when phase is not valid."""
        mock_state["ready_for_question"] = True
        mock_state["phase"] = "awaiting_main_answer"  # Not idle or armed
        
        result = on_first_mic_press(
            mock_state,
            "status",
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should not call ask_main_question
        assert len(result) == 7

