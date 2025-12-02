"""
Unit tests for exam.security.logging module.

These tests verify security event logging functionality.
"""

import pytest
from exam.security.logging import log_security_event
from tests.helpers import build_minimal_state


class TestLogSecurityEvent:
    """Tests for log_security_event function."""
    
    def test_log_security_event_adds_event(self):
        """Test that log_security_event adds an event to security_events."""
        state = build_minimal_state()
        initial_count = len(state["security_events"])
        
        result = log_security_event(state, "TAB_BLUR")
        
        assert len(result["security_events"]) == initial_count + 1
        assert result["security_events"][-1]["type"] == "TAB_BLUR"
    
    def test_log_security_event_includes_timestamp(self):
        """Test that log_security_event includes ISO timestamp."""
        state = build_minimal_state()
        
        result = log_security_event(state, "CLIPBOARD_COPY")
        
        event = result["security_events"][-1]
        assert "ts_iso" in event
        assert "T" in event["ts_iso"]  # ISO format includes T
        assert event["ts_iso"].endswith("Z")  # UTC timezone
    
    def test_log_security_event_includes_detail(self):
        """Test that log_security_event includes event detail."""
        state = build_minimal_state()
        detail = {"action": "copy", "target": "text"}
        
        result = log_security_event(state, "CLIPBOARD_COPY", detail)
        
        event = result["security_events"][-1]
        assert event["detail"] == detail
    
    def test_log_security_event_adds_to_flags(self):
        """Test that significant security events are added to flags."""
        state = build_minimal_state()
        initial_flags_count = len(state["flags"])
        
        result = log_security_event(state, "TAB_BLUR")
        
        assert "TAB_BLUR" in result["flags"]
        assert len(result["flags"]) == initial_flags_count + 1
    
    def test_log_security_event_multiple_events(self):
        """Test that multiple security events are logged correctly."""
        state = build_minimal_state()
        
        state = log_security_event(state, "TAB_BLUR")
        state = log_security_event(state, "CLIPBOARD_COPY")
        state = log_security_event(state, "CLIPBOARD_PASTE")
        
        assert len(state["security_events"]) == 3
        assert state["security_events"][0]["type"] == "TAB_BLUR"
        assert state["security_events"][1]["type"] == "CLIPBOARD_COPY"
        assert state["security_events"][2]["type"] == "CLIPBOARD_PASTE"
    
    def test_log_security_event_preserves_state(self):
        """Test that log_security_event preserves other state fields."""
        state = build_minimal_state(
            student_id="test_student",
            asked_main=5
        )
        
        result = log_security_event(state, "TAB_BLUR")
        
        assert result["student_id"] == "test_student"
        assert result["asked_main"] == 5

