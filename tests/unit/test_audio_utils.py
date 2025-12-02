"""
Unit tests for audio utility functions.

Tests for:
- cleanup_session_tmp() phase guard behavior
- Audio file cleanup timing
"""

import os
import tempfile
import pytest
from unittest.mock import Mock, patch
from typing import Dict, Any

from exam.audio.utils import cleanup_session_tmp


class TestCleanupSessionTmp:
    """Tests for cleanup_session_tmp() function."""
    
    def test_cleanup_skips_when_phase_not_complete(self):
        """Test that cleanup is skipped when phase != 'complete'."""
        # Create temporary files
        tmp_files = []
        for i in range(3):
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{i}.wav")
            tmp_file.write(b"test audio data")
            tmp_file.close()
            tmp_files.append(tmp_file.name)
        
        state = {
            "session_id": "test_session",
            "phase": "awaiting_main_answer",
            "_tmp_files": tmp_files,
            "audio_data": {"test": "data"},
            "audio_features": {"test": "features"}
        }
        
        # Call cleanup - should skip
        cleanup_session_tmp(state)
        
        # Verify files still exist
        for tmp_file in tmp_files:
            assert os.path.exists(tmp_file), f"File {tmp_file} should still exist"
        
        # Verify state not cleared
        assert state["_tmp_files"] == tmp_files
        assert state["audio_data"] == {"test": "data"}
        assert state["audio_features"] == {"test": "features"}
        
        # Cleanup manually
        for tmp_file in tmp_files:
            os.remove(tmp_file)
    
    def test_cleanup_performs_when_phase_complete(self):
        """Test that cleanup performs when phase == 'complete'."""
        # Create temporary files
        tmp_files = []
        for i in range(3):
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{i}.wav")
            tmp_file.write(b"test audio data")
            tmp_file.close()
            tmp_files.append(tmp_file.name)
        
        state = {
            "session_id": "test_session",
            "phase": "complete",
            "_tmp_files": tmp_files,
            "audio_data": {"test": "data"},
            "audio_features": {"test": "features"}
        }
        
        # Call cleanup - should perform
        cleanup_session_tmp(state)
        
        # Verify files are deleted
        for tmp_file in tmp_files:
            assert not os.path.exists(tmp_file), f"File {tmp_file} should be deleted"
        
        # Verify state is cleared
        assert state["_tmp_files"] == []
        assert state["audio_data"] is None
        assert state["audio_features"] is None
    
    def test_cleanup_with_force_true(self):
        """Test that cleanup performs when force=True even if phase != 'complete'."""
        # Create temporary files
        tmp_files = []
        for i in range(2):
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{i}.mp3")
            tmp_file.write(b"test audio data")
            tmp_file.close()
            tmp_files.append(tmp_file.name)
        
        state = {
            "session_id": "test_session",
            "phase": "awaiting_followup_answer",
            "_tmp_files": tmp_files,
            "audio_data": {"test": "data"},
            "audio_features": {"test": "features"}
        }
        
        # Call cleanup with force=True - should perform
        cleanup_session_tmp(state, force=True)
        
        # Verify files are deleted
        for tmp_file in tmp_files:
            assert not os.path.exists(tmp_file), f"File {tmp_file} should be deleted"
        
        # Verify state is cleared
        assert state["_tmp_files"] == []
        assert state["audio_data"] is None
        assert state["audio_features"] is None
    
    def test_cleanup_handles_missing_phase(self):
        """Test that cleanup skips when phase field is missing."""
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tmp_file.write(b"test audio data")
        tmp_file.close()
        tmp_path = tmp_file.name
        
        state = {
            "session_id": "test_session",
            # No phase field
            "_tmp_files": [tmp_path]
        }
        
        # Call cleanup - should skip (phase != "complete")
        cleanup_session_tmp(state)
        
        # Verify file still exists
        assert os.path.exists(tmp_path)
        
        # Cleanup manually
        os.remove(tmp_path)
    
    def test_cleanup_handles_missing_tmp_files(self):
        """Test that cleanup handles missing _tmp_files gracefully."""
        state = {
            "session_id": "test_session",
            "phase": "complete"
            # No _tmp_files field
        }
        
        # Should not raise exception
        cleanup_session_tmp(state)
        
        # Verify _tmp_files is set to empty list
        assert state["_tmp_files"] == []
    
    def test_cleanup_handles_file_already_deleted(self):
        """Test that cleanup handles files that are already deleted."""
        # Create and immediately delete a file
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tmp_file.write(b"test audio data")
        tmp_file.close()
        tmp_path = tmp_file.name
        os.remove(tmp_path)  # Delete it
        
        state = {
            "session_id": "test_session",
            "phase": "complete",
            "_tmp_files": [tmp_path]  # Reference to deleted file
        }
        
        # Should not raise exception
        cleanup_session_tmp(state)
        
        # Verify state is cleared
        assert state["_tmp_files"] == []
    
    def test_cleanup_handles_multiple_phases(self):
        """Test cleanup behavior with various phase values."""
        phases_to_skip = [
            "idle",
            "armed",
            "awaiting_main_answer",
            "awaiting_followup_answer",
            "awaiting_next_main",
            None,  # Missing phase
        ]
        
        for phase in phases_to_skip:
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            tmp_file.write(b"test")
            tmp_file.close()
            tmp_path = tmp_file.name
            
            state = {
                "session_id": "test_session",
                "phase": phase,
                "_tmp_files": [tmp_path]
            }
            
            cleanup_session_tmp(state)
            
            # File should still exist
            assert os.path.exists(tmp_path), f"Phase {phase} should skip cleanup"
            
            # Cleanup manually
            os.remove(tmp_path)
    
    def test_cleanup_logs_warning_when_skipped(self):
        """Test that cleanup logs warning when skipped during active exam."""
        state = {
            "session_id": "test_session",
            "phase": "awaiting_main_answer",
            "_tmp_files": []
        }
        
        with patch("exam.audio.utils.logger") as mock_logger:
            cleanup_session_tmp(state)
            
            # Verify warning was logged
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert call_args[0][0] == "cleanup_called_during_active_exam"
            assert call_args[1]["phase"] == "awaiting_main_answer"
    
    def test_cleanup_logs_debug_when_completed(self):
        """Test that cleanup logs debug message when completed."""
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tmp_file.write(b"test")
        tmp_file.close()
        tmp_path = tmp_file.name
        
        state = {
            "session_id": "test_session",
            "phase": "complete",
            "_tmp_files": [tmp_path]
        }
        
        with patch("exam.audio.utils.logger") as mock_logger:
            cleanup_session_tmp(state)
            
            # Verify debug was logged
            mock_logger.debug.assert_called()
            # Check that cleanup_completed was logged
            debug_calls = [call[0][0] for call in mock_logger.debug.call_args_list]
            assert "cleanup_session_tmp_completed" in debug_calls
        
        # File should be deleted
        assert not os.path.exists(tmp_path)
    
    def test_cleanup_handles_file_permission_error_gracefully(self):
        """Test that cleanup handles file permission errors gracefully."""
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tmp_file.write(b"test")
        tmp_file.close()
        tmp_path = tmp_file.name
        
        state = {
            "session_id": "test_session",
            "phase": "complete",
            "_tmp_files": [tmp_path]
        }
        
        # Mock os.remove to raise permission error
        with patch("os.remove", side_effect=PermissionError("Permission denied")):
            # Should not raise exception
            cleanup_session_tmp(state)
        
        # Verify state is still cleared
        assert state["_tmp_files"] == []
        
        # Cleanup manually
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

