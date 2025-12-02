"""
Unit tests for exam.state.network module.

Tests cover network status checking and offline queue management.
"""

import pytest
import time
import socket
from unittest.mock import Mock, patch
from exam.state.network import (
    check_network_status,
    update_network_status,
    queue_answer_locally,
    process_queued_answers
)


class TestCheckNetworkStatus:
    """Tests for check_network_status function."""
    
    def test_check_network_status_online(self):
        """Test check_network_status when network is available."""
        with patch('socket.create_connection', return_value=Mock()):
            result = check_network_status()
            assert result is True
    
    def test_check_network_status_offline(self):
        """Test check_network_status when network is unavailable."""
        with patch('socket.create_connection', side_effect=socket.error("Connection failed")):
            result = check_network_status()
            assert result is False
    
    def test_check_network_status_custom_endpoints(self):
        """Test check_network_status with custom endpoints."""
        custom_endpoints = [("example.com", 80)]
        with patch('socket.create_connection', return_value=Mock()):
            result = check_network_status(custom_endpoints)
            assert result is True
    
    def test_check_network_status_env_override(self):
        """Test check_network_status with environment variable override (lines 54-63)."""
        with patch('os.getenv', return_value="example.com:80,test.com:443"):
            with patch('socket.create_connection', return_value=Mock()):
                result = check_network_status()
                assert result is True
    
    def test_check_network_status_invalid_env_format(self):
        """Test check_network_status with invalid environment format."""
        with patch('os.getenv', return_value="invalid_format"):
            # Should fall back to defaults and try those
            # If all fail, returns False
            with patch('socket.create_connection', side_effect=socket.error("Connection failed")):
                result = check_network_status()
                assert result is False


class TestUpdateNetworkStatus:
    """Tests for update_network_status function."""
    
    @pytest.fixture
    def mock_state(self):
        """Create a mock state for testing."""
        return {
            "session_id": "test_session",
            "last_network_check": 0,
            "network_check_interval": 5,
            "network_status": "online",
        }
    
    def test_update_network_status_online(self, mock_state):
        """Test update_network_status when network is online."""
        with patch('exam.state.network.check_network_status', return_value=True):
            result = update_network_status(mock_state)
            assert result == "online"
            assert mock_state["network_status"] == "online"
    
    def test_update_network_status_offline(self, mock_state):
        """Test update_network_status when network is offline."""
        with patch('exam.state.network.check_network_status', return_value=False):
            result = update_network_status(mock_state)
            assert result == "offline"
            assert mock_state["network_status"] == "offline"
    
    def test_update_network_status_with_queued_answers(self, mock_state):
        """Test update_network_status when connection restored with queued answers (lines 105-107)."""
        mock_state["queued_answers"] = [{"text": "queued answer"}]
        with patch('exam.state.network.check_network_status', return_value=True):
            result = update_network_status(mock_state)
            assert result == "online"
            # Queued answers should be ready to process
    
    def test_update_network_status_interval_not_met(self, mock_state):
        """Test update_network_status when check interval not met."""
        mock_state["last_network_check"] = time.time() - 2  # Only 2 seconds ago
        mock_state["network_check_interval"] = 5
        
        result = update_network_status(mock_state)
        # Should return current status without checking
        assert result in ["online", "offline", "checking"]


class TestQueueAnswerLocally:
    """Tests for queue_answer_locally function."""
    
    @pytest.fixture
    def mock_state(self):
        """Create a mock state for testing."""
        return {
            "session_id": "test_session",
            "queued_answers": [],
        }
    
    def test_queue_answer_locally_basic(self, mock_state):
        """Test queue_answer_locally basic functionality."""
        with patch('exam.state.network.save_state_to_disk'):
            queue_answer_locally(mock_state, "Test answer", "/tmp/audio.mp3")
            
            assert len(mock_state["queued_answers"]) == 1
            assert mock_state["queued_answers"][0]["text"] == "Test answer"
            assert mock_state["queued_answers"][0]["audio_path"] == "/tmp/audio.mp3"
    
    def test_queue_answer_locally_no_audio(self, mock_state):
        """Test queue_answer_locally without audio path."""
        with patch('exam.state.network.save_state_to_disk'):
            queue_answer_locally(mock_state, "Test answer")
            
            assert len(mock_state["queued_answers"]) == 1
            assert mock_state["queued_answers"][0]["audio_path"] is None


class TestProcessQueuedAnswers:
    """Tests for process_queued_answers function."""
    
    @pytest.fixture
    def mock_state(self):
        """Create a mock state for testing."""
        return {
            "session_id": "test_session",
            "queued_answers": [
                {"text": "Answer 1", "audio_path": "/tmp/audio1.mp3"},
                {"text": "Answer 2", "audio_path": "/tmp/audio2.mp3"},
            ],
        }
    
    def test_process_queued_answers_online(self, mock_state):
        """Test process_queued_answers when network is online (lines 166-170)."""
        with patch('exam.state.network.check_network_status', return_value=True):
            count, queued_list = process_queued_answers(mock_state)
            assert count == 2  # Both answers processed
            assert len(queued_list) == 2  # List returned
    
    def test_process_queued_answers_offline(self, mock_state):
        """Test process_queued_answers when network is offline (lines 160-161)."""
        with patch('exam.state.network.check_network_status', return_value=False):
            count, queued_list = process_queued_answers(mock_state)
            assert count == 0  # No answers processed
            assert len(queued_list) == 0  # Empty list returned
    
    def test_process_queued_answers_empty(self):
        """Test process_queued_answers with no queued answers (lines 156-157)."""
        mock_state = {"session_id": "test_session", "queued_answers": []}
        count, queued_list = process_queued_answers(mock_state)
        assert count == 0
        assert len(queued_list) == 0

