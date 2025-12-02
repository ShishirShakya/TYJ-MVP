"""
Integration tests for Phase 3 API endpoints.

Phase 3.6: Comprehensive integration tests for TTS and follow-up question endpoints.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import os
import tempfile
from exam.api_client import ExamAPIClient
from exam.api_mode_adapters import generate_tts_via_api_or_direct, generate_followup_question_via_api_or_direct
from exam.state.core import ensure_state
from openai import OpenAI


@pytest.fixture
def mock_api_client():
    """Fixture for mock API client."""
    with patch('exam.api_client.ExamAPIClient', autospec=True) as MockClient:
        mock_client_instance = MockClient.return_value
        mock_client_instance.api_url = "http://mock-api.com"
        mock_client_instance.api_key = "mock-key"
        yield mock_client_instance


@pytest.fixture
def mock_openai_client():
    """Fixture for mock OpenAI client."""
    with patch('openai.OpenAI', autospec=True) as MockOpenAI:
        mock_instance = MockOpenAI.return_value
        # Mock TTS response
        mock_tts_response = MagicMock()
        mock_tts_response.content = b"fake audio data"
        mock_instance.audio.speech.create.return_value = mock_tts_response
        yield mock_instance


class TestPhase3APIEndpoints:
    """Integration tests for Phase 3 API endpoints."""
    
    def test_generate_tts_via_api_success(self, mock_api_client, mock_openai_client):
        """Test TTS generation via API."""
        mock_api_client.generate_tts.return_value = "/tmp/test_audio.mp3"
        
        s = ensure_state({"session_id": "test_session"})
        text = "Test question"
        
        audio_path = generate_tts_via_api_or_direct(
            text, mock_openai_client, s, api_client=mock_api_client
        )
        
        assert audio_path == "/tmp/test_audio.mp3"
        mock_api_client.generate_tts.assert_called_once_with(
            text=text,
            session_id="test_session",
            model=None,
            voice=None
        )
        mock_openai_client.audio.speech.create.assert_not_called()
    
    def test_generate_tts_via_api_fallback(self, mock_api_client, mock_openai_client):
        """Test TTS generation falls back to direct OpenAI if API fails."""
        mock_api_client.generate_tts.side_effect = Exception("API Down")
        
        # Mock direct TTS call
        with patch('exam.audio.tts.tts_to_mp3') as mock_tts:
            mock_tts.return_value = "/tmp/fallback_audio.mp3"
            
            s = ensure_state({"session_id": "test_session"})
            text = "Test question"
            
            audio_path = generate_tts_via_api_or_direct(
                text, mock_openai_client, s, api_client=mock_api_client
            )
            
            assert audio_path == "/tmp/fallback_audio.mp3"
            mock_api_client.generate_tts.assert_called_once()
            mock_tts.assert_called_once()
    
    def test_generate_followup_via_api_success(self, mock_api_client, mock_openai_client):
        """Test follow-up question generation via API."""
        mock_api_client.generate_followup_question_direct.return_value = "Follow-up question?"
        
        s = ensure_state({
            "session_id": "test_session",
            "current": {
                "main_question": "Main question?",
                "ctx": "Context text"
            }
        })
        last_answer = "Student answer"
        
        question = generate_followup_question_via_api_or_direct(
            s, last_answer, mock_openai_client, api_client=mock_api_client
        )
        
        assert question == "Follow-up question?"
        mock_api_client.generate_followup_question_direct.assert_called_once()
    
    def test_generate_followup_via_api_fallback(self, mock_api_client, mock_openai_client):
        """Test follow-up question generation falls back to direct OpenAI if API fails."""
        mock_api_client.generate_followup_question_direct.side_effect = Exception("API Down")
        
        # Mock direct follow-up generation
        with patch('exam.ai.question_generator._gen_followup') as mock_gen:
            mock_gen.return_value = "Direct follow-up?"
            
            s = ensure_state({
                "session_id": "test_session",
                "current": {
                    "main_question": "Main question?",
                    "ctx": "Context text"
                }
            })
            last_answer = "Student answer"
            
            question = generate_followup_question_via_api_or_direct(
                s, last_answer, mock_openai_client, api_client=mock_api_client
            )
            
            assert question == "Direct follow-up?"
            mock_api_client.generate_followup_question_direct.assert_called_once()
            mock_gen.assert_called_once()

