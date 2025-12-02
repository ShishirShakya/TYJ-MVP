"""
Unit tests for exam.flow.audio module.

Tests cover audio processing, transcription, and flow control.
"""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone
from exam.flow.audio import handle_mic


class TestHandleMic:
    """Tests for handle_mic function."""
    
    @pytest.fixture
    def mock_state(self):
        """Create a mock state for testing."""
        return {
            "session_id": "test_session",
            "request_id": "test_request",
            "phase": "awaiting_main_answer",
            "consent": True,
            "session_start_time": time.time() - 100,  # Started 100 seconds ago
            "current": {
                "main_question": "What is Python?",
                "answers": [],
                "followups_done": 0,
                "target_followups": 1,
                "q_time": time.time() - 10,  # Question asked 10 seconds ago
                "short_attempts": 0,
            },
            "history": [],
            "flags": [],
            "security_events": [],
        }
    
    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies."""
        deps = {}
        deps["ensure_state"] = lambda s: s
        deps["update_network_status"] = lambda s: "online"
        deps["save_state_to_disk"] = lambda s: None
        deps["_paths_for_session"] = lambda s: {"STATE_PATH": "/tmp/test_state.json"}
        deps["queue_answer_locally"] = lambda s, text, audio: None
        deps["transcribe"] = lambda audio, client, **kwargs: "This is my answer"
        deps["_detect_profanity"] = lambda text: False
        deps["_count_meaningful_words"] = lambda text: 5
        deps["_detect_answer_reuse"] = lambda s, text: False
        deps["_hash_answer"] = lambda text: "hash123"
        deps["analyze_speech_stylometry"] = lambda audio, s: {}
        deps["ask_followup_question"] = lambda s, gr, client, deps, **kwargs: (
            s, None, Mock(), Mock(), [], Mock(), Mock(), Mock(), Mock()  # 9 items including timeout
        )
        deps["grade_current_block"] = lambda s, gr, client, deps, **kwargs: (
            s, None, Mock(), Mock(), [], Mock(), Mock(), Mock()  # 8 items
        )
        deps["tts_to_mp3"] = lambda text, client, state, **kwargs: "/tmp/test.mp3"
        deps["get_max_answer_timeout_sec"] = lambda s: 300
        deps["_calculate_timeout_status"] = lambda s, gr, timeout: Mock()
        deps["_proctor_end_updates"] = lambda s, gr: (Mock(), Mock())
        deps["_categorize_error"] = lambda e: ("UNKNOWN_ERROR", {"message": str(e)})
        deps["MAX_SESSION_DURATION_SEC"] = 3600
        deps["MIN_WORDS"] = 3
        deps["MAX_SHORT_ATTEMPTS"] = 2
        deps["SHORT_PROMPT_TTS"] = "Your answer seems too short"
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
        return Mock()
    
    def test_handle_mic_no_consent(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handle_mic when consent is not given (line 95)."""
        mock_state["consent"] = False
        
        result = handle_mic(
            "/tmp/audio.mp3",
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # Returns 8 items when consent is False (no timeout update)
        assert len(result) == 8
        assert "consent" in str(result[2].get("value", "")).lower()
    
    def test_handle_mic_invalid_phase(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handle_mic when phase is invalid (line 102)."""
        mock_state["phase"] = "idle"
        
        result = handle_mic(
            "/tmp/audio.mp3",
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        assert len(result) == 9
    
    def test_handle_mic_session_timeout(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handle_mic when session timeout exceeded (lines 114-131)."""
        # Set session start time to exceed max duration
        mock_state["session_start_time"] = time.time() - 4000  # Exceeds 3600 seconds
        mock_dependencies["MAX_SESSION_DURATION_SEC"] = 3600
        
        result = handle_mic(
            "/tmp/audio.mp3",
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        assert len(result) == 9
        assert result[0]["phase"] == "complete"
        assert "SESSION_TIMEOUT" in result[0].get("flags", [])
    
    def test_handle_mic_answer_timeout(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handle_mic when answer timeout exceeded (lines 139-156)."""
        # Set q_time to exceed max timeout
        mock_state["current"]["q_time"] = time.time() - 400  # Exceeds 300 seconds
        mock_dependencies["get_max_answer_timeout_sec"] = lambda s: 300
        
        result = handle_mic(
            "/tmp/audio.mp3",
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        assert len(result) == 9
        assert result[0]["phase"] == "complete"
        assert "ANSWER_TIMEOUT" in result[0].get("flags", [])
    
    def test_handle_mic_offline(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handle_mic when network is offline (lines 162-169)."""
        mock_dependencies["update_network_status"] = lambda s: "offline"
        
        result = handle_mic(
            "/tmp/audio.mp3",
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        assert len(result) == 9
        assert "offline" in str(result[2].get("value", "")).lower()
    
    def test_handle_mic_empty_transcription(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handle_mic when transcription is empty (line 175)."""
        mock_dependencies["transcribe"] = lambda audio, client, **kwargs: ""
        
        result = handle_mic(
            "/tmp/audio.mp3",
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        assert len(result) == 9
        # Should handle empty transcription gracefully
    
    def test_handle_mic_profanity_detected(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handle_mic when profanity is detected (lines 183-204)."""
        mock_dependencies["_detect_profanity"] = lambda text: True
        mock_state["answers_tslog_all"] = []
        
        result = handle_mic(
            "/tmp/audio.mp3",
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        assert len(result) == 9
        assert result[0]["phase"] == "complete"
        assert "PROFANITY_DETECTED" in result[0].get("flags", [])
    
    def test_handle_mic_security_events(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handle_mic with security events (lines 76-88)."""
        # Add security events with proper timestamp format
        # The code replaces "Z" with "+00:00", so we need to provide format without Z
        now = datetime.now(timezone.utc)
        ts_iso = now.isoformat()  # Already has timezone info
        
        mock_state["security_events"] = [
            {
                "type": "TAB_BLUR",
                "ts_iso": ts_iso
            }
        ]
        mock_state["current"]["q_time"] = time.time() - 5  # Recent
        
        result = handle_mic(
            "/tmp/audio.mp3",
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        assert len(result) == 9
        # Security events should be processed
    
    def test_handle_mic_short_answer(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handle_mic with short answer (lines 214-223)."""
        mock_dependencies["_count_meaningful_words"] = lambda text: 2  # Less than MIN_WORDS
        mock_dependencies["MIN_WORDS"] = 3
        mock_state["current"]["short_attempts"] = 0
        
        result = handle_mic(
            "/tmp/audio.mp3",
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        assert len(result) == 9
        # Should handle short answer
    
    def test_handle_mic_followup_flow(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handle_mic followup question flow (lines 303-306)."""
        mock_state["phase"] = "awaiting_followup_answer"
        mock_state["current"]["followups_done"] = 0
        mock_state["current"]["target_followups"] = 2
        
        result = handle_mic(
            "/tmp/audio.mp3",
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        assert len(result) == 9
    
    def test_handle_mic_grade_after_followups(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test handle_mic grading after followups complete (lines 308-311)."""
        mock_state["phase"] = "awaiting_followup_answer"
        mock_state["current"]["followups_done"] = 1
        mock_state["current"]["target_followups"] = 1  # Already done
        mock_state["answers_tslog_all"] = []
        
        result = handle_mic(
            "/tmp/audio.mp3",
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies
        )
        
        # grade_current_block returns 8 items, but handle_mic adds timeout update
        # Actually, looking at the code, it returns 8 items when grading
        assert len(result) >= 8

