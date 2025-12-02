"""
Integration tests for audio file cleanup timing.

Tests verify that:
- Audio files persist during active exam
- Audio files are cleaned up after exam completion/termination
- Cleanup respects phase guard
"""

import os
import tempfile
import pytest
from unittest.mock import Mock, patch
from typing import Dict, Any

from exam.audio.utils import cleanup_session_tmp


class TestAudioCleanupTiming:
    """Integration tests for audio cleanup timing."""
    
    def test_audio_files_persist_during_active_exam(self):
        """Test that audio files are NOT cleaned up during active exam phases."""
        # Simulate active exam with multiple audio files
        tmp_files = []
        for i in range(5):
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_answer_{i}.wav")
            tmp_file.write(b"test audio data")
            tmp_file.close()
            tmp_files.append(tmp_file.name)
        
        # Add TTS audio files
        for i in range(3):
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_tts_{i}.mp3")
            tmp_file.write(b"test tts data")
            tmp_file.close()
            tmp_files.append(tmp_file.name)
        
        # Simulate active exam state
        active_phases = [
            "awaiting_main_answer",
            "awaiting_followup_answer",
            "awaiting_next_main",
            "armed"
        ]
        
        for phase in active_phases:
            state = {
                "session_id": "test_session",
                "phase": phase,
                "_tmp_files": tmp_files.copy(),
                "audio_data": {"test": "data"},
                "audio_features": {"test": "features"}
            }
            
            # Attempt cleanup - should skip
            cleanup_session_tmp(state)
            
            # Verify all files still exist
            for tmp_file in tmp_files:
                assert os.path.exists(tmp_file), f"File {tmp_file} should persist during phase {phase}"
            
            # Verify state not cleared
            assert len(state["_tmp_files"]) == len(tmp_files)
            assert state["audio_data"] == {"test": "data"}
        
        # Cleanup manually
        for tmp_file in tmp_files:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
    
    def test_audio_files_cleaned_up_after_successful_completion(self):
        """Test that audio files are cleaned up after successful exam completion."""
        # Create multiple audio files (simulating full exam)
        tmp_files = []
        
        # Answer files
        for i in range(3):
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_answer_{i}.wav")
            tmp_file.write(b"answer audio")
            tmp_file.close()
            tmp_files.append(tmp_file.name)
        
        # TTS files
        for i in range(5):
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_tts_{i}.mp3")
            tmp_file.write(b"tts audio")
            tmp_file.close()
            tmp_files.append(tmp_file.name)
        
        # Simulate exam completion
        state = {
            "session_id": "test_session",
            "phase": "complete",  # Exam completed successfully
            "_tmp_files": tmp_files,
            "audio_data": {"test": "data"},
            "audio_features": {"test": "features"},
            "asked_main": 3,
            "scores": [85, 90, 88]
        }
        
        # Perform cleanup
        cleanup_session_tmp(state)
        
        # Verify all files are deleted
        for tmp_file in tmp_files:
            assert not os.path.exists(tmp_file), f"File {tmp_file} should be deleted after completion"
        
        # Verify state is cleared
        assert state["_tmp_files"] == []
        assert state["audio_data"] is None
        assert state["audio_features"] is None
    
    def test_audio_files_cleaned_up_after_critical_violation(self):
        """Test that audio files are cleaned up after exam termination due to critical violation."""
        tmp_files = []
        for i in range(2):
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_answer_{i}.wav")
            tmp_file.write(b"answer audio")
            tmp_file.close()
            tmp_files.append(tmp_file.name)
        
        # Simulate exam termination due to critical violation
        state = {
            "session_id": "test_session",
            "phase": "complete",  # Terminated
            "_tmp_files": tmp_files,
            "flags": ["VOICEPRINT_MISMATCH"],  # Critical violation
            "audio_data": {"test": "data"},
            "audio_features": {"test": "features"}
        }
        
        # Perform cleanup
        cleanup_session_tmp(state)
        
        # Verify files are deleted
        for tmp_file in tmp_files:
            assert not os.path.exists(tmp_file), f"File {tmp_file} should be deleted after termination"
        
        # Verify state is cleared
        assert state["_tmp_files"] == []
        assert state["audio_data"] is None
    
    def test_audio_files_cleaned_up_after_threshold_violation(self):
        """Test that audio files are cleaned up after exam termination due to threshold violation."""
        tmp_files = []
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix="_answer.wav")
        tmp_file.write(b"answer audio")
        tmp_file.close()
        tmp_files.append(tmp_file.name)
        
        # Simulate exam termination due to threshold violation
        state = {
            "session_id": "test_session",
            "phase": "complete",  # Terminated
            "_tmp_files": tmp_files,
            "flags": ["TAB_BLUR_THRESHOLD_EXCEEDED"],  # Threshold violation
            "audio_data": {"test": "data"}
        }
        
        # Perform cleanup
        cleanup_session_tmp(state)
        
        # Verify file is deleted
        assert not os.path.exists(tmp_files[0])
        assert state["_tmp_files"] == []
    
    def test_audio_files_cleaned_up_after_session_timeout(self):
        """Test that audio files are cleaned up after session timeout."""
        tmp_files = []
        for i in range(3):
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_answer_{i}.wav")
            tmp_file.write(b"answer audio")
            tmp_file.close()
            tmp_files.append(tmp_file.name)
        
        # Simulate session timeout
        state = {
            "session_id": "test_session",
            "phase": "complete",  # Timed out
            "_tmp_files": tmp_files,
            "flags": ["SESSION_TIMEOUT"],
            "audio_data": {"test": "data"}
        }
        
        # Perform cleanup
        cleanup_session_tmp(state)
        
        # Verify files are deleted
        for tmp_file in tmp_files:
            assert not os.path.exists(tmp_file)
        assert state["_tmp_files"] == []
    
    def test_multiple_audio_files_accumulate_during_exam(self):
        """Test that multiple audio files accumulate during exam and all are cleaned up."""
        # Simulate exam progression with accumulating files
        all_files = []
        
        # Question 1: TTS + Answer
        q1_tts = tempfile.NamedTemporaryFile(delete=False, suffix="_q1_tts.mp3")
        q1_tts.write(b"q1 tts")
        q1_tts.close()
        all_files.append(q1_tts.name)
        
        q1_answer = tempfile.NamedTemporaryFile(delete=False, suffix="_q1_answer.wav")
        q1_answer.write(b"q1 answer")
        q1_answer.close()
        all_files.append(q1_answer.name)
        
        # Question 2: TTS + Answer
        q2_tts = tempfile.NamedTemporaryFile(delete=False, suffix="_q2_tts.mp3")
        q2_tts.write(b"q2 tts")
        q2_tts.close()
        all_files.append(q2_tts.name)
        
        q2_answer = tempfile.NamedTemporaryFile(delete=False, suffix="_q2_answer.wav")
        q2_answer.write(b"q2 answer")
        q2_answer.close()
        all_files.append(q2_answer.name)
        
        # During exam - files accumulate
        state = {
            "session_id": "test_session",
            "phase": "awaiting_next_main",
            "_tmp_files": all_files.copy()
        }
        
        # Cleanup should skip
        cleanup_session_tmp(state)
        
        # All files should still exist
        for tmp_file in all_files:
            assert os.path.exists(tmp_file)
        
        # After completion - all files cleaned up
        state["phase"] = "complete"
        cleanup_session_tmp(state)
        
        # All files should be deleted
        for tmp_file in all_files:
            assert not os.path.exists(tmp_file)
        assert state["_tmp_files"] == []
    
    def test_cleanup_idempotency(self):
        """Test that cleanup can be called multiple times safely."""
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tmp_file.write(b"test")
        tmp_file.close()
        tmp_path = tmp_file.name
        
        state = {
            "session_id": "test_session",
            "phase": "complete",
            "_tmp_files": [tmp_path]
        }
        
        # First cleanup
        cleanup_session_tmp(state)
        assert state["_tmp_files"] == []
        
        # Second cleanup (idempotent)
        cleanup_session_tmp(state)
        assert state["_tmp_files"] == []
        
        # File should be deleted (or already deleted)
        assert not os.path.exists(tmp_path)
    
    def test_ferpa_erasure_with_force_true(self):
        """Test that FERPA erasure can force cleanup even during active exam."""
        tmp_files = []
        for i in range(2):
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{i}.wav")
            tmp_file.write(b"test")
            tmp_file.close()
            tmp_files.append(tmp_file.name)
        
        # Active exam state
        state = {
            "session_id": "test_session",
            "phase": "awaiting_main_answer",  # Active exam
            "_tmp_files": tmp_files,
            "audio_data": {"test": "data"}
        }
        
        # Force cleanup (FERPA erasure scenario)
        cleanup_session_tmp(state, force=True)
        
        # Files should be deleted even though phase != "complete"
        for tmp_file in tmp_files:
            assert not os.path.exists(tmp_file)
        assert state["_tmp_files"] == []
        assert state["audio_data"] is None

