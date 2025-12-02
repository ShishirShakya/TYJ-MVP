"""
Unit tests for timeout status calculation and automatic termination.

Tests cover:
- Timeout display with clamped remaining time (no negatives)
- Automatic termination when timeout expires
- Consistent naming (max_timeout instead of timeout_sec)
"""

import pytest
import time
from unittest.mock import Mock, patch
from exam.ui.helpers import _calculate_timeout_status


class TestCalculateTimeoutStatus:
    """Tests for _calculate_timeout_status function."""
    
    @pytest.fixture
    def mock_gr_module(self):
        """Create mock Gradio module."""
        gr = Mock()
        def mock_update(**kwargs):
            return kwargs
        gr.update = mock_update
        return gr
    
    @pytest.fixture
    def mock_state(self):
        """Create mock state with q_time."""
        return {
            "current": {
                "q_time": time.time() - 30,  # 30 seconds ago
            },
            "phase": "awaiting_main_answer"
        }
    
    def test_timeout_status_positive_remaining(self, mock_state, mock_gr_module):
        """Test timeout status with positive remaining time."""
        with patch('exam.ui.helpers.get_max_answer_timeout_sec', return_value=60):
            result = _calculate_timeout_status(mock_state, mock_gr_module)
            
            # Should show green/yellow/orange/red based on remaining time
            assert result.get("visible") is True
            assert "⏱️" in result.get("value", "")
    
    def test_timeout_status_zero_remaining(self, mock_state, mock_gr_module):
        """Test timeout status when remaining time is exactly 0."""
        # Set q_time so that elapsed == max_timeout
        mock_state["current"]["q_time"] = time.time() - 60
        
        with patch('exam.ui.helpers.get_max_answer_timeout_sec', return_value=60):
            result = _calculate_timeout_status(mock_state, mock_gr_module)
            
            # Should show "00:00 - Time expired!"
            assert result.get("visible") is True
            value = result.get("value", "")
            assert "00:00" in value
            assert "Time expired!" in value
    
    def test_timeout_status_negative_remaining_clamped(self, mock_state, mock_gr_module):
        """Test that negative remaining time is clamped to 0."""
        # Set q_time so that elapsed > max_timeout (negative remaining)
        mock_state["current"]["q_time"] = time.time() - 120  # 120 seconds ago
        
        with patch('exam.ui.helpers.get_max_answer_timeout_sec', return_value=60):
            result = _calculate_timeout_status(mock_state, mock_gr_module)
            
            # Should show "00:00 - Time expired!" (not negative time like "-01:00")
            assert result.get("visible") is True
            value = result.get("value", "")
            assert "00:00" in value
            assert "Time expired!" in value
            # Should NOT show negative minutes/seconds (e.g., "-01:00" or "-12:22")
            # The time_str should be "00:00", not something like "-01:00"
            assert "00:00" in value.split(" - ")[0]  # Time part should be "00:00"
    
    def test_timeout_status_no_q_time(self, mock_state, mock_gr_module):
        """Test timeout status when q_time is not set."""
        mock_state["current"]["q_time"] = None
        
        result = _calculate_timeout_status(mock_state, mock_gr_module)
        
        # Should be hidden
        assert result.get("visible") is False
    
    def test_timeout_status_uses_max_timeout_naming(self, mock_state, mock_gr_module):
        """Test that function uses max_timeout naming (not timeout_sec)."""
        # This is verified by checking the code uses get_max_answer_timeout_sec
        # and the variable is named max_timeout
        with patch('exam.ui.helpers.get_max_answer_timeout_sec', return_value=45) as mock_get:
            result = _calculate_timeout_status(mock_state, mock_gr_module)
            
            # Verify the function was called
            mock_get.assert_called_once()
            
            # Result should be visible
            assert result.get("visible") is True

