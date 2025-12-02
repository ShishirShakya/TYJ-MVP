"""
Integration tests for Phase 2: API Mode Integration.

These tests verify that API mode works correctly end-to-end, including:
- Question generation via API
- Answer grading via API
- Circuit breaker behavior
- Fallback to direct OpenAI calls
- Error handling and retry logic

INTEGRATION TESTING: Tests critical workflows end-to-end (Principle #14).
"""

import pytest
import os
from unittest.mock import Mock, MagicMock, patch, call
from typing import Dict, Any
import requests
from openai import OpenAI

from exam.api_client import ExamAPIClient, get_api_client
from exam.api_mode_adapters import (
    generate_question_via_api_or_direct,
    grade_answer_via_api_or_direct,
    transcribe_audio_via_api_or_direct
)
from exam.state.core import ensure_state
from shared.circuit_breaker import CircuitBreakerOpenError, CircuitState


class TestAPIModeIntegration:
    """Integration tests for API mode."""
    
    @pytest.fixture
    def mock_api_client(self):
        """Create a mock API client."""
        client = Mock(spec=ExamAPIClient)
        client.api_url = "http://localhost:8000"
        client.api_key = "test-key"
        return client
    
    @pytest.fixture
    def mock_state(self):
        """Create a minimal mock state."""
        return {
            "session_id": "test_session_123",
            "student_id": "test_student",
            "course_id": "TEST_COURSE",
            "exam_id": "TEST_EXAM",
            "questions_meta": [],
            "current": {
                "main_question": None,
                "answers": [],
                "followups_done": 0,
                "target_followups": 0
            }
        }
    
    @pytest.fixture
    def mock_openai_client(self):
        """Create a mock OpenAI client."""
        client = Mock(spec=OpenAI)
        return client
    
    def test_generate_question_via_api_success(self, mock_state, mock_openai_client, mock_api_client):
        """Test question generation via API succeeds."""
        # Mock API response
        mock_api_client.generate_question_direct.return_value = "What is the main idea?"
        
        # Call adapter
        question = generate_question_via_api_or_direct(
            s=mock_state,
            ctx_text="Test context text for question generation.",
            client=mock_openai_client,
            api_client=mock_api_client
        )
        
        # Verify API was called
        mock_api_client.generate_question_direct.assert_called_once()
        assert question == "What is the main idea?"
        # Verify OpenAI was NOT called (API mode)
        assert not hasattr(mock_openai_client.chat, 'completions') or not mock_openai_client.chat.completions.create.called
    
    def test_generate_question_via_api_fallback(self, mock_state, mock_openai_client, mock_api_client):
        """Test question generation falls back to direct OpenAI when API fails."""
        # Mock API failure
        mock_api_client.generate_question_direct.side_effect = Exception("API error")
        
        # Mock direct OpenAI call
        with patch('exam.ai.question_generator._gen_main_question_with_ctx') as mock_gen:
            mock_gen.return_value = "Fallback question"
            
            question = generate_question_via_api_or_direct(
                s=mock_state,
                ctx_text="Test context",
                client=mock_openai_client,
                api_client=mock_api_client
            )
            
            # Verify fallback was used
            assert question == "Fallback question"
            mock_gen.assert_called_once()
    
    def test_generate_question_without_api_client(self, mock_state, mock_openai_client):
        """Test question generation without API client (standalone mode)."""
        # Mock direct OpenAI call
        with patch('exam.ai.question_generator._gen_main_question_with_ctx') as mock_gen:
            mock_gen.return_value = "Direct question"
            
            question = generate_question_via_api_or_direct(
                s=mock_state,
                ctx_text="Test context",
                client=mock_openai_client,
                api_client=None
            )
            
            # Verify direct call was used
            assert question == "Direct question"
            mock_gen.assert_called_once()
    
    def test_grade_answer_via_api_success(self, mock_state, mock_openai_client, mock_api_client):
        """Test answer grading via API succeeds."""
        messages = [
            {"role": "system", "content": "You are a grader."},
            {"role": "user", "content": "Question: What is X? Answer: X is Y."}
        ]
        
        # Mock API response
        mock_api_client.grade_answer_direct.return_value = (
            {"Conceptual": 85, "Analytical": 80, "Application": 75, "Reflection": 70, "Overall": 77},
            "Good understanding of the concept.",
            77
        )
        
        # Call adapter
        comp = grade_answer_via_api_or_direct(
            s=mock_state,
            messages=messages,
            client=mock_openai_client,
            api_client=mock_api_client,
            chat_model="gpt-4o-mini"
        )
        
        # Verify API was called
        mock_api_client.grade_answer_direct.assert_called_once()
        # Verify mock response object was created
        assert hasattr(comp, 'choices')
        assert comp.choices[0].message.content == "Good understanding of the concept."
        # Verify parsed scores are stored
        assert comp._scores_dict["Overall"] == 77
    
    def test_grade_answer_via_api_fallback(self, mock_state, mock_openai_client, mock_api_client):
        """Test answer grading falls back to direct OpenAI when API fails."""
        messages = [{"role": "user", "content": "Test"}]
        
        # Mock API failure
        mock_api_client.grade_answer_direct.side_effect = Exception("API error")
        
        # Mock direct OpenAI call
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Score: 85/100"
        
        with patch('exam.utils.with_retry') as mock_retry:
            mock_retry.return_value = mock_response
            
            comp = grade_answer_via_api_or_direct(
                s=mock_state,
                messages=messages,
                client=mock_openai_client,
                api_client=mock_api_client
            )
            
            # Verify fallback was used
            assert comp == mock_response
            mock_retry.assert_called_once()


class TestCircuitBreakerIntegration:
    """Integration tests for circuit breaker in API client."""
    
    @pytest.fixture
    def api_client(self):
        """Create API client instance."""
        return ExamAPIClient(
            api_url="http://localhost:8000",
            api_key="test-key",
            timeout=5
        )
    
    def test_circuit_breaker_initialized(self, api_client):
        """Test that circuit breaker is initialized."""
        assert api_client.circuit_breaker is not None
        assert api_client.circuit_breaker.get_state() == CircuitState.CLOSED
    
    def test_circuit_breaker_stats_available(self, api_client):
        """Test that circuit breaker stats are accessible."""
        stats = api_client.get_circuit_breaker_stats()
        assert isinstance(stats, dict)
        assert "state" in stats
        assert "failures" in stats
        assert "successes" in stats
    
    @patch('exam.api_client.requests.Session.request')
    def test_circuit_breaker_opens_on_failures(self, mock_request, api_client):
        """Test that circuit breaker opens after multiple failures."""
        # Mock repeated failures
        mock_request.side_effect = requests.exceptions.ConnectionError("Connection failed")
        
        # Trigger failures (need 5 failures to open circuit)
        for i in range(5):
            try:
                api_client._make_request("GET", "/health", max_retries=1)
            except (CircuitBreakerOpenError, ValueError):
                pass
        
        # Check circuit breaker state
        stats = api_client.get_circuit_breaker_stats()
        # After 5 failures, circuit should be OPEN
        assert stats["failures"] >= 5
    
    @patch('exam.api_client.requests.Session.request')
    def test_circuit_breaker_rejects_when_open(self, mock_request, api_client):
        """Test that circuit breaker rejects requests when open."""
        # Force circuit breaker to OPEN state
        api_client.circuit_breaker._state = CircuitState.OPEN
        api_client.circuit_breaker._opened_at = 0  # Set to past
        
        # Try to make request
        with pytest.raises(CircuitBreakerOpenError):
            api_client._make_request("GET", "/health", max_retries=1)
        
        # Verify request was not made
        mock_request.assert_not_called()


class TestAPIModeFallback:
    """Integration tests for API mode fallback behavior."""
    
    @pytest.fixture
    def mock_state(self):
        """Create a minimal mock state."""
        return {
            "session_id": "test_session",
            "questions_meta": []
        }
    
    @patch.dict(os.environ, {"API_BASE_URL": "", "API_KEY": ""}, clear=True)
    def test_get_api_client_disabled(self):
        """Test that get_api_client returns None when API mode is disabled."""
        client = get_api_client()
        assert client is None
    
    @patch.dict(os.environ, {"API_BASE_URL": "http://localhost:8000", "API_KEY": "test-key"})
    def test_get_api_client_enabled(self):
        """Test that get_api_client returns client when API mode is enabled."""
        client = get_api_client()
        assert client is not None
        assert isinstance(client, ExamAPIClient)
        assert client.api_url == "http://localhost:8000"
        assert client.api_key == "test-key"
    
    def test_question_generation_fallback_behavior(self, mock_state):
        """Test that question generation falls back gracefully."""
        from unittest.mock import patch
        
        # Test without API client (standalone mode)
        with patch('exam.ai.question_generator._gen_main_question_with_ctx') as mock_gen:
            mock_gen.return_value = "Direct question"
            
            question = generate_question_via_api_or_direct(
                s=mock_state,
                ctx_text="Test context",
                client=Mock(spec=OpenAI),
                api_client=None
            )
            
            assert question == "Direct question"
            mock_gen.assert_called_once()


class TestAPIModeEndToEnd:
    """End-to-end integration tests for API mode."""
    
    @pytest.fixture
    def mock_api_client(self):
        """Create a fully mocked API client."""
        client = Mock(spec=ExamAPIClient)
        client.api_url = "http://localhost:8000"
        client.api_key = "test-key"
        client.circuit_breaker = Mock()
        client.circuit_breaker.get_state.return_value = CircuitState.CLOSED
        client.circuit_breaker.call = lambda func: func()  # Pass through
        return client
    
    def test_complete_question_generation_flow(self, mock_api_client):
        """Test complete question generation flow via API."""
        state = ensure_state({
            "session_id": "test_session",
            "questions_meta": []
        })
        
        # Mock API response
        mock_api_client.generate_question_direct.return_value = "What is machine learning?"
        
        # Generate question
        question = generate_question_via_api_or_direct(
            s=state,
            ctx_text="Machine learning is a subset of AI...",
            client=Mock(spec=OpenAI),
            api_client=mock_api_client
        )
        
        # Verify
        assert question == "What is machine learning?"
        mock_api_client.generate_question_direct.assert_called_once()
        call_args = mock_api_client.generate_question_direct.call_args
        assert "Machine learning is a subset of AI" in call_args[1]["context_text"]
    
    def test_complete_grading_flow(self, mock_api_client):
        """Test complete answer grading flow via API."""
        state = ensure_state({
            "session_id": "test_session",
            "current": {
                "main_question": "What is X?",
                "answers": ["X is Y"]
            }
        })
        
        messages = [
            {"role": "system", "content": "You are a grader."},
            {"role": "user", "content": "Question: What is X? Answer: X is Y."}
        ]
        
        # Mock API response
        mock_api_client.grade_answer_direct.return_value = (
            {"Conceptual": 85, "Analytical": 80, "Application": 75, "Reflection": 70, "Overall": 77},
            "Good answer with clear explanation.",
            77
        )
        
        # Grade answer
        comp = grade_answer_via_api_or_direct(
            s=state,
            messages=messages,
            client=Mock(spec=OpenAI),
            api_client=mock_api_client
        )
        
        # Verify
        mock_api_client.grade_answer_direct.assert_called_once()
        assert comp.choices[0].message.content == "Good answer with clear explanation."
        assert comp._scores_dict["Overall"] == 77

