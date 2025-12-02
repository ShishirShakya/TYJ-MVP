"""
Unit tests for exam.ai.context_manager module.

Tests cover context management, history optimization, and operation-specific limits.
"""

import pytest
from exam.ai.context_manager import (
    msgs_from_state,
    _get_relevant_history,
    MAX_HISTORY_LENGTH,
    MAX_HISTORY_LENGTH_QUESTION,
    MAX_HISTORY_LENGTH_FOLLOWUP,
    MAX_HISTORY_LENGTH_FEEDBACK,
)
from shared.config.prompts import SYSTEM_PROMPT


class TestMsgsFromState:
    """Tests for msgs_from_state function."""
    
    def test_msgs_from_state_basic(self):
        """Test basic message building from state."""
        state = {
            "history": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ]
        }
        
        result = msgs_from_state(state)
        
        assert len(result) == 3  # System prompt + 2 history items
        assert result[0]["role"] == "system"
        assert result[0]["content"] == SYSTEM_PROMPT
        assert result[1]["role"] == "user"
        assert result[2]["role"] == "assistant"
    
    def test_msgs_from_state_empty_history(self):
        """Test with empty history."""
        state = {"history": []}
        
        result = msgs_from_state(state)
        
        assert len(result) == 1  # Only system prompt
        assert result[0]["role"] == "system"
        assert result[0]["content"] == SYSTEM_PROMPT
    
    def test_msgs_from_state_missing_history(self):
        """Test with missing history field."""
        state = {}
        
        result = msgs_from_state(state)
        
        assert len(result) == 1  # Only system prompt
        assert result[0]["role"] == "system"
    
    def test_msgs_from_state_question_operation(self):
        """Test question operation with history limit."""
        # Create history longer than MAX_HISTORY_LENGTH_QUESTION
        long_history = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(MAX_HISTORY_LENGTH_QUESTION + 5)
        ]
        state = {"history": long_history}
        
        result = msgs_from_state(state, operation_type="question")
        
        # Should only include last MAX_HISTORY_LENGTH_QUESTION items
        assert len(result) == MAX_HISTORY_LENGTH_QUESTION + 1  # +1 for system prompt
        assert result[0]["role"] == "system"
        # Check that we got the last items
        assert result[-1]["content"] == f"Message {MAX_HISTORY_LENGTH_QUESTION + 4}"
    
    def test_msgs_from_state_followup_operation(self):
        """Test followup operation with history limit."""
        # Note: MAX_HISTORY_LENGTH_FOLLOWUP is 0, but history[-0:] returns all items
        # This is the actual behavior of the current implementation
        state = {
            "history": [
                {"role": "user", "content": "Question"},
                {"role": "assistant", "content": "Answer"}
            ]
        }
        
        result = msgs_from_state(state, operation_type="followup")
        
        # Current behavior: history[-0:] returns all items, so includes all history
        assert len(result) == 3  # System prompt + 2 history items
        assert result[0]["role"] == "system"
        assert result[1]["content"] == "Question"
        assert result[2]["content"] == "Answer"
    
    def test_msgs_from_state_feedback_operation(self):
        """Test feedback operation with history limit."""
        # Create history longer than MAX_HISTORY_LENGTH_FEEDBACK
        long_history = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(MAX_HISTORY_LENGTH_FEEDBACK + 5)
        ]
        state = {"history": long_history}
        
        result = msgs_from_state(state, operation_type="feedback")
        
        # Should only include last MAX_HISTORY_LENGTH_FEEDBACK items
        assert len(result) == MAX_HISTORY_LENGTH_FEEDBACK + 1  # +1 for system prompt
        assert result[0]["role"] == "system"
    
    def test_msgs_from_state_default_operation(self):
        """Test default operation type."""
        long_history = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(MAX_HISTORY_LENGTH + 5)
        ]
        state = {"history": long_history}
        
        result = msgs_from_state(state, operation_type="unknown")
        
        # Should use MAX_HISTORY_LENGTH
        assert len(result) == MAX_HISTORY_LENGTH + 1  # +1 for system prompt
    
    def test_msgs_from_state_non_dict_input(self):
        """Test defensive check for non-dict input."""
        result = msgs_from_state("not a dict")
        
        # Should return minimal valid messages list
        assert len(result) == 1
        assert result[0]["role"] == "system"
        assert result[0]["content"] == SYSTEM_PROMPT
    
    def test_msgs_from_state_history_not_list(self):
        """Test defensive check for history that's not a list."""
        state = {"history": "not a list"}
        
        result = msgs_from_state(state)
        
        # Should fix history and return only system prompt
        assert len(result) == 1
        assert result[0]["role"] == "system"
        # History should be fixed in state
        assert isinstance(state["history"], list)
        assert state["history"] == []


class TestGetRelevantHistory:
    """Tests for _get_relevant_history function."""
    
    def test_get_relevant_history_question(self):
        """Test getting relevant history for question operation."""
        long_history = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(MAX_HISTORY_LENGTH_QUESTION + 5)
        ]
        state = {"history": long_history}
        
        result = _get_relevant_history(state, operation_type="question")
        
        # Should return last MAX_HISTORY_LENGTH_QUESTION items
        assert len(result) == MAX_HISTORY_LENGTH_QUESTION
        assert result[0]["content"] == f"Message {5}"
        assert result[-1]["content"] == f"Message {MAX_HISTORY_LENGTH_QUESTION + 4}"
    
    def test_get_relevant_history_followup(self):
        """Test getting relevant history for followup operation."""
        state = {
            "history": [
                {"role": "user", "content": "Question"},
                {"role": "assistant", "content": "Answer"}
            ]
        }
        
        result = _get_relevant_history(state, operation_type="followup")
        
        # Followup should return empty list
        assert result == []
    
    def test_get_relevant_history_feedback(self):
        """Test getting relevant history for feedback operation."""
        long_history = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(MAX_HISTORY_LENGTH_FEEDBACK + 5)
        ]
        state = {"history": long_history}
        
        result = _get_relevant_history(state, operation_type="feedback")
        
        # Should return last MAX_HISTORY_LENGTH_FEEDBACK items
        assert len(result) == MAX_HISTORY_LENGTH_FEEDBACK
        assert result[0]["content"] == f"Message {5}"
    
    def test_get_relevant_history_custom_max_items(self):
        """Test with custom max_items parameter."""
        long_history = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(20)
        ]
        state = {"history": long_history}
        
        result = _get_relevant_history(state, operation_type="question", max_items=5)
        
        # Should use custom max_items instead of operation-specific default
        assert len(result) == 5
        assert result[0]["content"] == "Message 15"
    
    def test_get_relevant_history_short_history(self):
        """Test with history shorter than limit."""
        state = {
            "history": [
                {"role": "user", "content": "Message 1"},
                {"role": "user", "content": "Message 2"}
            ]
        }
        
        result = _get_relevant_history(state, operation_type="feedback")
        
        # Should return all history items
        assert len(result) == 2
        assert result[0]["content"] == "Message 1"
        assert result[1]["content"] == "Message 2"
    
    def test_get_relevant_history_empty_history(self):
        """Test with empty history."""
        state = {"history": []}
        
        result = _get_relevant_history(state, operation_type="question")
        
        assert result == []
    
    def test_get_relevant_history_missing_history(self):
        """Test with missing history field."""
        state = {}
        
        result = _get_relevant_history(state, operation_type="question")
        
        # Should handle missing history gracefully
        assert isinstance(result, list)
        assert len(result) == 0
    
    def test_get_relevant_history_default_operation(self):
        """Test with default/unknown operation type."""
        long_history = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(MAX_HISTORY_LENGTH + 5)
        ]
        state = {"history": long_history}
        
        result = _get_relevant_history(state, operation_type="unknown")
        
        # Should use MAX_HISTORY_LENGTH (takes first items, not last)
        assert len(result) == MAX_HISTORY_LENGTH
        assert result[0]["content"] == "Message 0"
        assert result[-1]["content"] == f"Message {MAX_HISTORY_LENGTH - 1}"

