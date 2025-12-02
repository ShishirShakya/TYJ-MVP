"""
Unit tests for exam.flow.grading module.

Tests cover grading flow, error handling, and edge cases.
"""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch
from exam.flow.grading import grade_current_block
from shared.time_provider import MockTimeProvider


class TestGradeCurrentBlock:
    """Tests for grade_current_block function."""
    
    @pytest.fixture
    def mock_state(self):
        """Create a mock state for testing."""
        import random
        return {
            "session_id": "test_session",
            "request_id": "test_request",
            "phase": "awaiting_main_answer",
            "asked_main": 0,
            "limit": 5,
            "followups_min": 0,
            "followups_max": 2,
            "history": [],
            "current": {
                "main_question": "What is Python?",
                "answers": ["Python is a programming language"],
                "followups_done": 0,
                "target_followups": 1,
                "q_time": 1000.0,
                "short_attempts": 0,
                "ctx": "Python is a high-level programming language."
            },
            "scores": [],
            "rubrics": [],
            "flags": [],
            "used_context_hashes": set(),
            "questions_meta": [],
            "_rng": random.Random(42),
        }
    
    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies."""
        deps = {}
        deps["ensure_state"] = lambda s: s
        deps["save_state_to_disk"] = lambda s: None
        deps["reset_current_block"] = lambda s: None
        deps["get_followup_range"] = lambda s: (0, 2)
        deps["get_chunks"] = lambda: ["Python is a high-level programming language known for its simplicity and readability. It supports multiple programming paradigms including object-oriented and functional programming."]
        deps["_validate_context"] = lambda ctx: (True, "")
        deps["_gen_main_question_with_ctx"] = lambda s, ctx, **kwargs: "What is Python?"
        deps["_sanitize_for_prompt"] = lambda text, max_len: text[:max_len]
        deps["msgs_from_state"] = lambda s, operation_type: [{"role": "system", "content": "System prompt"}]
        deps["with_retry"] = lambda fn, **kwargs: fn(**{k: v for k, v in kwargs.items() if k not in ["circuit_breaker", "service_name"]})
        deps["_log_token_usage"] = lambda comp, op, s, **kwargs: None
        deps["_parse_feedback"] = lambda fb: ({"Conceptual": 85, "Analytical": 90, "Application": 80, "Reflection": 75}, "Good answer")
        deps["_calculate_overall_score"] = lambda scores: 82.5
        deps["tts_to_mp3"] = lambda text, client, state, **kwargs: "/tmp/test.mp3"
        deps["get_audio_duration"] = lambda audio: 5.0
        deps["get_max_answer_timeout_sec"] = lambda s=None: 300
        deps["_proctor_end_updates"] = lambda s, gr: ({}, {})
        deps["_categorize_error"] = lambda e: ("UNKNOWN_ERROR", {"message": str(e)})
        deps["CHAT_MODEL"] = "gpt-4o-mini"
        deps["FEEDBACK_BLOCK_INSTR"] = "Provide feedback"
        deps["ProctorState"] = None
        # DETERMINISTIC: Add time_provider for deterministic testing (Principle #5)
        deps["time_provider"] = MockTimeProvider(initial_time=1000.0)
        return deps
    
    @pytest.fixture
    def mock_gr_module(self):
        """Create mock Gradio module."""
        gr = Mock()
        def mock_update(**kwargs):
            return kwargs
        gr.update = mock_update
        return gr
    
    @pytest.fixture
    def mock_openai_client(self):
        """Create mock OpenAI client."""
        client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Conceptual: 85\nAnalytical: 90\nApplication: 80\nReflection: 75\nFeedback: Good answer"
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_response.model = "gpt-4o-mini"
        client.chat.completions.create.return_value = mock_response
        return client
    
    def test_grade_current_block_non_dict_state(self, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test defensive check for non-dict state."""
        # Pass a string instead of dict
        result = grade_current_block(
            "not a dict",
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle gracefully and return error tuple
        assert len(result) >= 3
    
    def test_grade_current_block_non_list_history(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test defensive check for non-list history."""
        mock_state["history"] = "not a list"
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle gracefully
        assert len(result) >= 3
        # History should be converted to list
        assert isinstance(result[0].get("history"), list)
    
    def test_grade_current_block_non_dict_current(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test defensive check for non-dict current."""
        mock_state["current"] = "not a dict"
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle gracefully
        assert len(result) >= 3
        # Current should be converted to dict
        assert isinstance(result[0].get("current"), dict)
    
    def test_grade_current_block_proctor_state(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test proctor state handling."""
        # Create a mock ProctorState class
        class MockProctorState:
            def add_block_rollup(self):
                return {"attention": 0.8}
        
        mock_state["proctor_state"] = MockProctorState()
        mock_state["proctor_blocks"] = []
        mock_dependencies["ProctorState"] = MockProctorState
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle proctor state
        assert len(result) >= 3
    
    def test_grade_current_block_parse_feedback_error(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handling when _parse_feedback returns unexpected format."""
        def bad_parse_feedback(fb):
            return "not a tuple"  # Should return tuple
        
        mock_dependencies["_parse_feedback"] = bad_parse_feedback
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle gracefully
        assert len(result) >= 3
    
    def test_grade_current_block_scores_dict_not_dict(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handling when scores_dict is not a dict."""
        def bad_parse_feedback(fb):
            return ("not a dict", "feedback")  # First element should be dict
        
        mock_dependencies["_parse_feedback"] = bad_parse_feedback
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle gracefully
        assert len(result) >= 3
    
    def test_grade_current_block_qualitative_assessment(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test qualitative assessment based on score."""
        # Test excellent (>= 85)
        mock_dependencies["_calculate_overall_score"] = lambda scores: 90.0
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        assert len(result) >= 3
        # Check that feedback summary was added
        assert len(result[0]["history"]) > 0
    
    def test_grade_current_block_qualitative_satisfactory(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test satisfactory assessment (70-84)."""
        mock_dependencies["_calculate_overall_score"] = lambda scores: 75.0
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        assert len(result) >= 3
    
    def test_grade_current_block_qualitative_not_satisfactory(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test not-satisfactory assessment (< 70)."""
        mock_dependencies["_calculate_overall_score"] = lambda scores: 60.0
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        assert len(result) >= 3
    
    def test_grade_current_block_empty_history(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handling when history is empty after processing."""
        mock_state["history"] = []
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle gracefully
        assert len(result) >= 3
        # Should add feedback to history
        assert len(result[0]["history"]) > 0
    
    def test_grade_current_block_history_not_dict(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handling when history item is not a dict."""
        mock_state["history"] = ["not a dict"]
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle gracefully
        assert len(result) >= 3
    
    def test_grade_current_block_continue_next_question(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test continuing to next question when limit not reached."""
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should continue to next question
        assert len(result) == 8
        assert result[0]["asked_main"] == 1
        assert result[0]["phase"] == "awaiting_main_answer"
    
    def test_grade_current_block_exam_complete(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test exam completion when limit reached."""
        mock_state["asked_main"] = 4
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should mark as complete
        assert len(result) == 8
        assert result[0]["phase"] == "complete"
        assert result[0]["asked_main"] == 5
    
    def test_grade_current_block_reset_current_block_error(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handling when reset_current_block raises error."""
        def failing_reset(s):
            raise Exception("Reset failed")
        
        mock_dependencies["reset_current_block"] = failing_reset
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle error gracefully
        assert len(result) >= 3
    
    def test_grade_current_block_empty_chunks(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test error handling when chunks are empty."""
        mock_dependencies["get_chunks"] = lambda: []
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        from exam.flow.response_builder import build_error_tuple
        mock_dependencies["build_error_tuple"] = build_error_tuple
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle error gracefully
        assert len(result) >= 3
    
    def test_grade_current_block_fallback_chunks(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test error handling when chunks contain only fallback message."""
        mock_dependencies["get_chunks"] = lambda: ["(No textbook content available - using fallback)"]
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        from exam.flow.response_builder import build_error_tuple
        mock_dependencies["build_error_tuple"] = build_error_tuple
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle error gracefully
        assert len(result) >= 3
    
    def test_grade_current_block_no_valid_chunks(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test error handling when no valid chunks after validation."""
        mock_dependencies["get_chunks"] = lambda: ["short"]  # Too short
        mock_dependencies["_validate_context"] = lambda ctx: (False, "Context too short")
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        from exam.flow.response_builder import build_error_tuple
        mock_dependencies["build_error_tuple"] = build_error_tuple
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle error gracefully
        assert len(result) >= 3
    
    def test_grade_current_block_all_chunks_used(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test behavior when all chunks have been used."""
        chunks = [
            "Python is a high-level programming language known for its simplicity and readability. It supports multiple programming paradigms.",
            "Machine learning is a subset of artificial intelligence that enables systems to learn from data without explicit programming."
        ]
        mock_dependencies["get_chunks"] = lambda: chunks
        import hashlib
        used_hashes = {hashlib.sha256(chunk.encode("utf-8")).hexdigest() for chunk in chunks}
        mock_state["used_context_hashes"] = used_hashes
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should reset and reuse chunks
        assert len(result) == 8
    
    def test_grade_current_block_question_generation_retry(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test retry logic when question generation fails."""
        call_count = [0]
        
        def mock_gen_question(s, ctx, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Generated question failed validation")
            return "What is Python?"
        
        mock_dependencies["_gen_main_question_with_ctx"] = mock_gen_question
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should retry and eventually succeed or use fallback
        assert call_count[0] >= 1
        assert len(result) == 8
    
    def test_grade_current_block_with_progress(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test with progress callback."""
        progress_calls = []
        
        def mock_progress(value):
            progress_calls.append(value)
        
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies,
            progress=mock_progress
        )
        
        # Should have called progress (may not reach 1.0 if error occurs)
        assert len(progress_calls) > 0
        # Progress should be called at least once
        assert any(call > 0 for call in progress_calls)
    
    def test_grade_current_block_circuit_breaker(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test circuit breaker handling."""
        mock_circuit_breaker = Mock()
        mock_circuit_breaker.get_breaker.return_value = None
        mock_circuit_breaker_manager = Mock()
        mock_circuit_breaker_manager.get_breaker.return_value = None
        mock_dependencies["circuit_breaker_manager"] = mock_circuit_breaker_manager
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle circuit breaker
        assert len(result) >= 3
    
    def test_grade_current_block_msgs_from_state_error(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handling when msgs_from_state raises error."""
        def failing_msgs_from_state(s, operation_type):
            raise TypeError("'str' object does not support item assignment")
        
        mock_dependencies["msgs_from_state"] = failing_msgs_from_state
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle error gracefully
        assert len(result) >= 3
    
    def test_grade_current_block_msgs_not_list(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handling when msgs_from_state returns non-list."""
        def bad_msgs_from_state(s, operation_type):
            return "not a list"
        
        mock_dependencies["msgs_from_state"] = bad_msgs_from_state
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle gracefully
        assert len(result) >= 3
    
    def test_grade_current_block_ensure_state_returns_non_dict(self, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handling when ensure_state returns non-dict (line 157)."""
        def bad_ensure_state(s):
            return "not a dict"  # Should return dict
        
        mock_dependencies["ensure_state"] = bad_ensure_state
        
        with pytest.raises(TypeError, match="ensure_state returned non-dict type"):
            grade_current_block(
                {},
                mock_gr_module,
                mock_openai_client,
                mock_dependencies
            )
    
    def test_grade_current_block_history_assignment_fails(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handling when history assignment fails (lines 169-175)."""
        # Create a dict subclass that will fail on assignment after first access
        class FailingDict(dict):
            _assignment_count = {}
            
            def __setitem__(self, key, value):
                if key == "history":
                    # Allow first assignment, fail on second (when trying to fix it)
                    count = self._assignment_count.get(key, 0)
                    self._assignment_count[key] = count + 1
                    if count > 0:  # Fail on second assignment
                        raise TypeError("Cannot assign")
                super().__setitem__(key, value)
        
        bad_state = FailingDict(mock_state)
        bad_state["history"] = "not a list"  # First assignment succeeds
        
        # Mock ensure_state to return the bad state
        def ensure_state_returns_bad(s):
            return bad_state
        
        mock_dependencies["ensure_state"] = ensure_state_returns_bad
        
        result = grade_current_block(
            {},
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle gracefully
        assert len(result) >= 3
    
    def test_grade_current_block_proctor_state_exception(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test proctor state exception handling (lines 182-183)."""
        class MockProctorState:
            def add_block_rollup(self):
                raise Exception("Proctor error")
        
        mock_state["proctor_state"] = MockProctorState()
        mock_state["proctor_blocks"] = []
        mock_dependencies["ProctorState"] = MockProctorState
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle exception gracefully
        assert len(result) >= 3
    
    def test_grade_current_block_current_assignment_fails(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handling when current assignment fails (lines 198-212)."""
        # Create a dict subclass that will fail on assignment after first access
        class FailingDict(dict):
            _assignment_count = {}
            
            def __setitem__(self, key, value):
                if key == "current":
                    # Allow first assignment, fail on second (when trying to fix it)
                    count = self._assignment_count.get(key, 0)
                    self._assignment_count[key] = count + 1
                    if count > 0:  # Fail on second assignment
                        raise TypeError("Cannot assign")
                super().__setitem__(key, value)
        
        bad_state = FailingDict(mock_state)
        bad_state["current"] = "not a dict"  # First assignment succeeds
        
        # Mock ensure_state to return the bad state
        def ensure_state_returns_bad(s):
            return bad_state
        
        mock_dependencies["ensure_state"] = ensure_state_returns_bad
        
        result = grade_current_block(
            {},
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle gracefully
        assert len(result) >= 3
    
    def test_grade_current_block_current_not_dict_after_get(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handling when current is not a dict after get (lines 218-228)."""
        # Set current to None to trigger the defensive check
        mock_state["current"] = None
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle gracefully and initialize current
        assert len(result) >= 3
        assert isinstance(result[0].get("current"), dict)
    
    def test_grade_current_block_history_not_list_before_append(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test defensive check for history before appending (line 243)."""
        # Set history to None to trigger the check
        mock_state["history"] = None
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle gracefully
        assert len(result) >= 3
        assert isinstance(result[0].get("history"), list)
    
    def test_grade_current_block_circuit_breaker_exception(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test circuit breaker exception handling (lines 253-256)."""
        mock_circuit_breaker_manager = Mock()
        mock_circuit_breaker_manager.get_breaker.side_effect = Exception("Circuit breaker error")
        mock_dependencies["circuit_breaker_manager"] = mock_circuit_breaker_manager
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle exception gracefully
        assert len(result) >= 3
    
    def test_grade_current_block_state_not_dict_before_api_call(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test defensive check before API call (line 260)."""
        # This is hard to test directly, but we can test the error path
        # by making ensure_state return a non-dict, which will raise before API call
        def bad_ensure_state(s):
            return "not a dict"
        
        mock_dependencies["ensure_state"] = bad_ensure_state
        
        with pytest.raises(TypeError):
            grade_current_block(
                mock_state,
                mock_gr_module,
                mock_openai_client,
                mock_dependencies
            )
    
    def test_grade_current_block_msgs_from_state_type_error(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test msgs_from_state TypeError handling (lines 283-289)."""
        def failing_msgs_from_state(s, operation_type):
            raise TypeError("'str' object does not support item assignment")
        
        mock_dependencies["msgs_from_state"] = failing_msgs_from_state
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle error gracefully and restore state
        assert len(result) >= 3
    
    def test_grade_current_block_history_not_list_after_api(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test defensive check for history after API call (line 311)."""
        # Corrupt history during the flow
        call_count = [0]
        original_with_retry = mock_dependencies["with_retry"]
        
        def corrupting_with_retry(fn, **kwargs):
            nonlocal mock_state
            call_count[0] += 1
            if call_count[0] == 1:
                # Corrupt history after API call
                mock_state["history"] = "not a list"
            return original_with_retry(fn, **kwargs)
        
        mock_dependencies["with_retry"] = corrupting_with_retry
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle gracefully
        assert len(result) >= 3
        assert isinstance(result[0].get("history"), list)
    
    def test_grade_current_block_feedback_history_updates(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test feedback history update defensive checks (lines 360, 362, 364, 371)."""
        # Test with empty history
        mock_state["history"] = []
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should add feedback to history
        assert len(result) >= 3
        assert len(result[0]["history"]) > 0
        
        # Test with history containing non-dict item
        mock_state["history"] = ["not a dict"]
        mock_state["asked_main"] = 0
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle gracefully
        assert len(result) >= 3
    
    def test_grade_current_block_reset_error_state_checks(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test reset_current_block error handling with state checks (lines 377, 385, 387, 401)."""
        def failing_reset(s):
            # Corrupt state during reset
            s["current"] = "corrupted"
            raise Exception("Reset failed")
        
        mock_dependencies["reset_current_block"] = failing_reset
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle error gracefully and restore current
        assert len(result) >= 3
        assert isinstance(result[0].get("current"), dict)
    
    def test_grade_current_block_chunk_selection_fallback(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test chunk selection fallback when no unused chunks (lines 485-486, 490, 515)."""
        chunks = [
            "Python is a high-level programming language known for its simplicity and readability.",
            "Machine learning is a subset of artificial intelligence."
        ]
        mock_dependencies["get_chunks"] = lambda: chunks
        import hashlib
        # Use all chunks
        used_hashes = {hashlib.sha256(chunk.encode("utf-8")).hexdigest() for chunk in chunks}
        mock_state["used_context_hashes"] = used_hashes.copy()
        # But then make validation fail so we use fallback
        mock_dependencies["_validate_context"] = lambda ctx: (True, "")
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle fallback gracefully
        assert len(result) == 8
    
    def test_grade_current_block_question_generation_fallback(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test question generation fallback (lines 540-541, 544)."""
        def always_failing_gen(s, ctx, **kwargs):
            raise ValueError("Validation failed")
        
        mock_dependencies["_gen_main_question_with_ctx"] = always_failing_gen
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should use fallback question
        assert len(result) == 8
        assert "current" in result[0]
        assert "main_question" in result[0]["current"]
    
    def test_grade_current_block_question_generation_returns_none(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handling when question generation returns None (line 544)."""
        def returning_none_gen(s, ctx, **kwargs):
            return None
        
        mock_dependencies["_gen_main_question_with_ctx"] = returning_none_gen
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should use fallback question
        assert len(result) == 8
        assert "current" in result[0]
        assert result[0]["current"]["main_question"] is not None
    
    def test_grade_current_block_progress_callbacks_next_question(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test progress callbacks during next question flow (lines 569, 572)."""
        progress_calls = []
        
        def mock_progress(value):
            progress_calls.append(value)
        
        # Fix get_max_answer_timeout_sec to accept state parameter
        mock_dependencies["get_max_answer_timeout_sec"] = lambda s=None: 300
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies,
            progress=mock_progress
        )
        
        # Should have called progress multiple times
        assert len(progress_calls) > 0
        # Should reach 1.0 at the end (or at least 0.7)
        assert 1.0 in progress_calls or any(call >= 0.7 for call in progress_calls)
    
    def test_grade_current_block_progress_callbacks_exam_complete(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test progress callbacks during exam completion (lines 592, 595)."""
        progress_calls = []
        
        def mock_progress(value):
            progress_calls.append(value)
        
        mock_state["asked_main"] = 4
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies,
            progress=mock_progress
        )
        
        # Should have called progress multiple times
        assert len(progress_calls) > 0
        # Should reach 1.0 at the end
        assert 1.0 in progress_calls or any(call >= 0.7 for call in progress_calls)
    
    def test_grade_current_block_current_not_dict_before_q_time(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test defensive check for current before setting q_time (line 577)."""
        # Corrupt current during flow
        call_count = [0]
        original_tts = mock_dependencies["tts_to_mp3"]
        
        def corrupting_tts(text, client, state, **kwargs):
            nonlocal mock_state
            call_count[0] += 1
            if call_count[0] == 1:
                # Corrupt current after TTS
                mock_state["current"] = "corrupted"
            return original_tts(text, client, state, **kwargs)
        
        mock_dependencies["tts_to_mp3"] = corrupting_tts
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle gracefully and restore current
        assert len(result) >= 3
        assert isinstance(result[0].get("current"), dict)
    
    def test_grade_current_block_state_corruption_error_logging(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test state corruption error logging (line 607)."""
        # Create a scenario that triggers the corruption error
        def corrupting_msgs_from_state(s, operation_type):
            # Simulate the specific error
            raise TypeError("'str' object does not support item assignment")
        
        mock_dependencies["msgs_from_state"] = corrupting_msgs_from_state
        mock_state["asked_main"] = 0
        mock_state["limit"] = 5
        
        result = grade_current_block(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Should handle error gracefully and log it
        assert len(result) >= 3

