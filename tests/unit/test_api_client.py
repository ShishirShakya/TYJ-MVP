"""
Unit tests for API client module.

Tests the ExamAPIClient class and related functionality.
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
import requests
from exam.api_client import ExamAPIClient, get_api_client


class TestExamAPIClient:
    """Test cases for ExamAPIClient class."""
    
    def test_init(self):
        """Test API client initialization."""
        client = ExamAPIClient(
            api_url="http://localhost:8000",
            api_key="test-key",
            timeout=30
        )
        
        assert client.api_url == "http://localhost:8000"
        assert client.api_key == "test-key"
        assert client.timeout == 30
        assert "X-API-Key" in client.session.headers
        assert client.session.headers["X-API-Key"] == "test-key"
    
    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is stripped from API URL."""
        client = ExamAPIClient(
            api_url="http://localhost:8000/",
            api_key="test-key"
        )
        assert client.api_url == "http://localhost:8000"
    
    @patch('exam.api_client.requests.Session')
    def test_make_request_success(self, mock_session_class):
        """Test successful API request."""
        # Setup mock response
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok", "data": "test"}
        mock_response.raise_for_status = Mock()
        
        mock_session = Mock()
        mock_session.request.return_value = mock_response
        mock_session.headers = {}
        mock_session_class.return_value = mock_session
        
        client = ExamAPIClient("http://localhost:8000", "test-key")
        result = client._make_request("GET", "/health")
        
        assert result == {"status": "ok", "data": "test"}
        mock_session.request.assert_called_once()
    
    @patch('exam.api_client.requests.Session')
    @patch('time.sleep')  # Mock sleep to speed up tests
    def test_make_request_retry_on_timeout(self, mock_sleep, mock_session_class):
        """Test that API client retries on timeout."""
        mock_session = Mock()
        mock_session.headers = {}
        
        # First two calls timeout, third succeeds
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status = Mock()
        
        mock_session.request.side_effect = [
            requests.exceptions.Timeout("Timeout"),
            requests.exceptions.Timeout("Timeout"),
            mock_response
        ]
        mock_session_class.return_value = mock_session
        
        client = ExamAPIClient("http://localhost:8000", "test-key", timeout=30)
        result = client._make_request("GET", "/health", max_retries=3)
        
        assert result == {"status": "ok"}
        assert mock_session.request.call_count == 3
        assert mock_sleep.call_count == 2  # Should sleep twice before success
    
    @patch('exam.api_client.requests.Session')
    def test_make_request_no_retry_on_4xx(self, mock_session_class):
        """Test that API client doesn't retry on 4xx errors (except 429)."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Bad request"}
        
        mock_session = Mock()
        mock_session.request.return_value = mock_response
        mock_session.headers = {}
        mock_session_class.return_value = mock_session
        
        client = ExamAPIClient("http://localhost:8000", "test-key")
        
        # Create HTTPError
        http_error = requests.exceptions.HTTPError()
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        
        with pytest.raises(ValueError, match="API request failed"):
            client._make_request("GET", "/health", max_retries=3)
        
        # Should only try once (no retries for 4xx)
        assert mock_session.request.call_count == 1
    
    @patch('exam.api_client.requests.Session')
    @patch('time.sleep')  # Mock sleep to speed up tests
    def test_make_request_retry_on_429(self, mock_sleep, mock_session_class):
        """Test that API client retries on 429 (rate limit)."""
        mock_session = Mock()
        mock_session.headers = {}
        
        # First call returns 429, second succeeds
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.json.return_value = {"detail": "Rate limit exceeded"}
        
        mock_response_ok = Mock()
        mock_response_ok.json.return_value = {"status": "ok"}
        mock_response_ok.raise_for_status = Mock()
        
        mock_session.request.side_effect = [
            mock_response_429,
            mock_response_ok
        ]
        mock_session_class.return_value = mock_session
        
        client = ExamAPIClient("http://localhost:8000", "test-key")
        
        # Create HTTPError for 429
        http_error = requests.exceptions.HTTPError()
        http_error.response = mock_response_429
        mock_response_429.raise_for_status.side_effect = http_error
        
        # Second call should succeed
        mock_response_ok.raise_for_status = Mock()
        
        result = client._make_request("GET", "/health", max_retries=3)
        
        assert result == {"status": "ok"}
        assert mock_session.request.call_count == 2
        assert mock_sleep.call_count == 1  # Should sleep once before retry
    
    @patch('exam.api_client.requests.Session')
    def test_generate_question(self, mock_session_class):
        """Test generate_question method."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "question": "What is the main idea?",
            "question_id": "q_1"
        }
        mock_response.raise_for_status = Mock()
        
        mock_session = Mock()
        mock_session.request.return_value = mock_response
        mock_session.headers = {}
        mock_session_class.return_value = mock_session
        
        client = ExamAPIClient("http://localhost:8000", "test-key")
        question, question_id = client.generate_question(
            session_id="test-session",
            course_id="test-course",
            exam_id="test-exam"
        )
        
        assert question == "What is the main idea?"
        assert question_id == "q_1"
    
    @patch('exam.api_client.requests.Session')
    def test_grade_answer(self, mock_session_class):
        """Test grade_answer method."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "score": 0.85,
            "feedback": "Good answer",
            "rubric": [
                {"criterion": "Accuracy", "score": 0.9, "feedback": "Correct"}
            ]
        }
        mock_response.raise_for_status = Mock()
        
        mock_session = Mock()
        mock_session.request.return_value = mock_response
        mock_session.headers = {}
        mock_session_class.return_value = mock_session
        
        client = ExamAPIClient("http://localhost:8000", "test-key")
        result = client.grade_answer(
            session_id="test-session",
            answer="Test answer",
            question_id="q_1"
        )
        
        assert result["score"] == 0.85
        assert result["feedback"] == "Good answer"
        assert len(result["rubric"]) == 1
    
    @patch('exam.api_client.requests.Session')
    @patch('builtins.open', create=True)
    @patch('exam.api_client.Path')
    def test_process_audio(self, mock_path_class, mock_open, mock_session_class):
        """Test process_audio method."""
        # Mock Path to simulate file existence
        mock_audio_file = Mock()
        mock_audio_file.exists.return_value = True
        mock_audio_file.suffix = '.wav'
        mock_audio_file.name = 'audio.wav'
        mock_audio_file.__str__ = lambda x: "/path/to/audio.wav"
        mock_path_class.return_value = mock_audio_file
        
        # Mock file open
        mock_file = Mock()
        mock_file.read.return_value = b"fake audio data"
        mock_open.return_value.__enter__.return_value = mock_file
        mock_open.return_value.__exit__ = Mock(return_value=None)
        
        # Mock session and response
        mock_response = Mock()
        mock_response.json.return_value = {
            "transcript": "This is a test transcript",
            "features": {"duration": 5.0, "word_count": 5}
        }
        mock_response.raise_for_status = Mock()
        
        mock_session = Mock()
        mock_session.post.return_value = mock_response
        mock_session.headers = {"X-API-Key": "test-key", "Content-Type": "application/json"}
        mock_session_class.return_value = mock_session
        
        client = ExamAPIClient("http://localhost:8000", "test-key")
        transcript, features = client.process_audio(
            session_id="test-session",
            audio_path="/path/to/audio.wav"
        )
        
        assert transcript == "This is a test transcript"
        assert features["duration"] == 5.0
        assert features["word_count"] == 5
    
    @patch('exam.api_client.requests.Session')
    def test_health_check_success(self, mock_session_class):
        """Test health_check method when API is healthy."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "healthy"}
        mock_response.raise_for_status = Mock()
        
        mock_session = Mock()
        mock_session.request.return_value = mock_response
        mock_session.headers = {}
        mock_session_class.return_value = mock_session
        
        client = ExamAPIClient("http://localhost:8000", "test-key")
        assert client.health_check() is True
    
    @patch('exam.api_client.requests.Session')
    def test_health_check_failure(self, mock_session_class):
        """Test health_check method when API is unhealthy."""
        mock_session = Mock()
        mock_session.request.side_effect = requests.exceptions.RequestException("Connection error")
        mock_session.headers = {}
        mock_session_class.return_value = mock_session
        
        client = ExamAPIClient("http://localhost:8000", "test-key")
        assert client.health_check() is False


class TestGetAPIClient:
    """Test cases for get_api_client function."""
    
    @patch.dict(os.environ, {"API_BASE_URL": "http://localhost:8000", "API_KEY": "test-key"})
    def test_get_api_client_with_env_vars(self):
        """Test get_api_client when environment variables are set."""
        client = get_api_client()
        assert client is not None
        assert isinstance(client, ExamAPIClient)
        assert client.api_url == "http://localhost:8000"
        assert client.api_key == "test-key"
    
    @patch.dict(os.environ, {"API_BASE_URL": ""}, clear=True)
    def test_get_api_client_without_env_vars(self):
        """Test get_api_client when environment variables are not set."""
        client = get_api_client()
        assert client is None
    
    @patch.dict(os.environ, {"API_BASE_URL": "http://localhost:8000"}, clear=True)
    def test_get_api_client_without_key(self):
        """Test get_api_client when API_BASE_URL is set but API_KEY is not."""
        client = get_api_client()
        assert client is None
    
    @patch.dict(os.environ, {"EXAM_API_URL": "http://localhost:8000", "EXAM_API_KEY": "test-key"})
    def test_get_api_client_with_alt_env_vars(self):
        """Test get_api_client with alternative environment variable names."""
        # Clear API_BASE_URL and API_KEY to test fallback
        with patch.dict(os.environ, {"API_BASE_URL": "", "API_KEY": ""}, clear=False):
            client = get_api_client()
            assert client is not None
            assert isinstance(client, ExamAPIClient)
            assert client.api_url == "http://localhost:8000"
            assert client.api_key == "test-key"

