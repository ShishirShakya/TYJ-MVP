"""
Unit tests for exam.state.core module.

These tests verify state management functions while preserving the dependency
injection wiring pattern.
"""

import pytest
from exam.state.core import ensure_state, reset_current_block, get_followup_range
from tests.helpers import build_minimal_state, assert_state_valid


class TestEnsureState:
    """Tests for ensure_state function."""
    
    def test_ensure_state_initializes_empty_dict(self):
        """Test that ensure_state initializes an empty dict correctly."""
        state = ensure_state({})
        assert_state_valid(state)
        assert state["session_id"] is not None
        assert isinstance(state["session_id"], str)
    
    def test_ensure_state_preserves_existing_values(self):
        """Test that ensure_state preserves existing state values."""
        existing_state = build_minimal_state(
            student_id="existing_student",
            course_id="EXISTING_COURSE"
        )
        result = ensure_state(existing_state)
        
        assert result["student_id"] == "existing_student"
        assert result["course_id"] == "EXISTING_COURSE"
        assert_state_valid(result)
    
    def test_ensure_state_sets_defaults(self):
        """Test that ensure_state sets all required defaults."""
        state = ensure_state({})
        
        assert state["history"] == []
        assert state["asked_main"] == 0
        assert state["scores"] == []
        assert state["rubrics"] == []
        assert state["phase"] == "idle"
        assert state["consent"] is False
        assert state["flags"] == []
        assert state["security_events"] == []
    
    def test_ensure_state_creates_session_id(self):
        """Test that ensure_state creates unique session IDs."""
        state1 = ensure_state({})
        state2 = ensure_state({})
        
        assert state1["session_id"] != state2["session_id"]
        assert len(state1["session_id"]) > 0
    
    def test_ensure_state_creates_request_id(self):
        """Test that ensure_state creates request IDs for idempotency."""
        state = ensure_state({})
        
        assert "request_id" in state
        assert isinstance(state["request_id"], str)
        assert len(state["request_id"]) > 0
    
    def test_ensure_state_creates_unique_request_ids(self):
        """Test that ensure_state creates unique request IDs."""
        state1 = ensure_state({})
        state2 = ensure_state({})
        
        assert state1["request_id"] != state2["request_id"]
    
    def test_ensure_state_initializes_current_block(self):
        """Test that ensure_state initializes current block structure."""
        state = ensure_state({})
        
        assert "current" in state
        assert state["current"]["main_question"] is None
        assert state["current"]["answers"] == []
        assert state["current"]["followups_done"] == 0
        assert state["current"]["target_followups"] == 0


class TestResetCurrentBlock:
    """Tests for reset_current_block function."""
    
    def test_reset_current_block_clears_current_data(self):
        """Test that reset_current_block clears current block data."""
        state = build_minimal_state(
            current={
                "main_question": "Test question",
                "answers": ["Answer 1"],
                "followups_done": 2,
                "target_followups": 3,
                "q_time": 1000.0,
                "short_attempts": 1,
                "ctx": {"test": "data"}
            }
        )
        
        reset_current_block(state)
        
        # Verify all fields are reset
        assert state["current"]["main_question"] is None
        assert state["current"]["answers"] == []
        assert state["current"]["followups_done"] == 0
        assert state["current"]["target_followups"] == 0
        assert state["current"]["q_time"] is None
        assert state["current"]["short_attempts"] == 0
        assert state["current"]["ctx"] is None
    
    def test_reset_current_block_raises_on_non_dict(self):
        """Test that reset_current_block raises TypeError on non-dict input."""
        with pytest.raises(TypeError):
            reset_current_block("not a dict")
        
        with pytest.raises(TypeError):
            reset_current_block(None)
        
        with pytest.raises(TypeError):
            reset_current_block([])
    
    def test_reset_current_block_preserves_other_state(self):
        """Test that reset_current_block doesn't affect other state fields."""
        state = build_minimal_state(
            student_id="test_student",
            asked_main=5,
            scores=[85, 90]
        )
        
        reset_current_block(state)
        
        assert state["student_id"] == "test_student"
        assert state["asked_main"] == 5
        assert state["scores"] == [85, 90]


class TestGetFollowupRange:
    """Tests for get_followup_range function."""
    
    def test_get_followup_range_with_valid_values(self):
        """Test get_followup_range with valid min/max values."""
        state = build_minimal_state(
            followups_min=1,
            followups_max=3
        )
        
        min_followups, max_followups = get_followup_range(state)
        
        assert min_followups == 1
        assert max_followups == 3
    
    def test_get_followup_range_with_defaults(self):
        """Test get_followup_range with default values."""
        state = build_minimal_state(
            followups_min=0,
            followups_max=1
        )
        
        min_followups, max_followups = get_followup_range(state)
        
        assert min_followups == 0
        assert max_followups == 1
    
    def test_get_followup_range_handles_missing_values(self):
        """Test get_followup_range handles missing values gracefully."""
        state = build_minimal_state()
        # Remove followups_min/max to test defaults
        state.pop("followups_min", None)
        state.pop("followups_max", None)
        
        # ensure_state should set defaults, but test edge case
        state = ensure_state(state)
        min_followups, max_followups = get_followup_range(state)
        
        assert min_followups >= 0
        assert max_followups >= min_followups
    
    def test_get_followup_range_handles_corrupted_state(self):
        """Test get_followup_range handles corrupted state (min > max)."""
        state = build_minimal_state(
            followups_min=5,  # min > max (corrupted state)
            followups_max=2
        )
        
        min_followups, max_followups = get_followup_range(state)
        
        # Should fix corrupted state by ensuring min <= max
        assert min_followups <= max_followups
        assert min_followups == 5  # Uses min as max when corrupted
        assert max_followups == 5

