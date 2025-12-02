"""
Integration tests for grading workflow.

These tests verify the complete grading workflow,
including state management, AI calls, and error handling.

INTEGRATION TESTING: Tests critical workflows end-to-end (Principle #14).
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any

from exam.flow.grading import grade_current_block
from exam.state.core import ensure_state
from shared.time_provider import MockTimeProvider


class TestGradingWorkflow:
    """Integration tests for grading workflow."""
    
    def test_grading_workflow_complete(self, mock_state, mock_openai_client, mock_gradio_module, mock_dependencies_exam_flow):
        """
        Integration test: Complete grading workflow.
        
        Tests: State initialization → Answer collection → AI grading → State update → Next question
        """
        # Initialize state
        time_provider = MockTimeProvider(initial_time=1000.0)
        state = ensure_state(mock_state, time_provider=time_provider)
        
        # Set up state for grading
        state["phase"] = "awaiting_main_answer"
        state["current"] = {
            "main_question": "What is the main idea?",
            "answers": ["This is my answer"],
            "followups_done": 0,
            "target_followups": 1,
            "q_time": 1000.0,
            "short_attempts": 0,
            "ctx": "Test context"
        }
        state["asked_main"] = 0
        state["limit"] = 1
        
        # Mock AI grading response
        mock_response = Mock()
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Score: 85/100. Feedback: Good answer."
        
        mock_openai_client.chat.completions.create.return_value = mock_response
        
        # Mock dependencies
        deps = mock_dependencies_exam_flow
        # _parse_feedback returns tuple: (scores_dict, feedback_text)
        deps["_parse_feedback"] = Mock(return_value=(
            {"Conceptual": 85, "Analytical": 85, "Application": 85, "Reflection": 85, "Overall": 85},
            "Good answer"
        ))
        deps["_calculate_overall_score"] = Mock(return_value=85.0)
        deps["tts_to_mp3"] = Mock(return_value="/tmp/test.mp3")
        deps["get_audio_duration"] = Mock(return_value=5.0)
        # Ensure save_state_to_disk is properly mocked
        deps["save_state_to_disk"] = Mock(return_value=True)
        
        # Execute grading
        result = grade_current_block(
            s=state,
            gr_module=mock_gradio_module,
            client=mock_openai_client,
            dependencies=deps
        )
        
        # Verify result structure
        assert result is not None
        assert len(result) == 8  # Expected tuple length
        
        # Verify state updated
        updated_state = result[0]
        assert updated_state["asked_main"] == 1
        assert len(updated_state["scores"]) > 0
        assert updated_state["phase"] == "complete"  # Should be complete (limit reached)
    
    def test_grading_workflow_with_followups(self, mock_state, mock_openai_client, mock_gradio_module, mock_dependencies_exam_flow):
        """
        Integration test: Grading workflow with follow-up questions.
        
        Tests: Main question → Answer → Follow-up → Answer → Complete
        """
        # Initialize state
        time_provider = MockTimeProvider(initial_time=1000.0)
        state = ensure_state(mock_state, time_provider=time_provider)
        
        # Set up state for grading with followups
        state["phase"] = "awaiting_followup_answer"
        state["current"] = {
            "main_question": "What is the main idea?",
            "answers": ["Main answer", "Follow-up answer"],
            "followups_done": 1,
            "target_followups": 2,
            "q_time": 1000.0,
            "short_attempts": 0,
            "ctx": "Test context"
        }
        state["asked_main"] = 0
        state["limit"] = 2
        
        # Mock AI responses
        mock_response = Mock()
        mock_response.usage = Mock()
        mock_response.usage.total_tokens = 150
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Score: 85/100. Feedback: Good answer."
        
        mock_openai_client.chat.completions.create.return_value = mock_response
        
        # Mock dependencies
        deps = mock_dependencies_exam_flow
        # _parse_feedback returns tuple: (scores_dict, feedback_text)
        deps["_parse_feedback"] = Mock(return_value=(
            {"Conceptual": 85, "Analytical": 85, "Application": 85, "Reflection": 85, "Overall": 85},
            "Good answer"
        ))
        deps["_calculate_overall_score"] = Mock(return_value=85.0)
        deps["tts_to_mp3"] = Mock(return_value="/tmp/test.mp3")
        deps["get_audio_duration"] = Mock(return_value=5.0)
        deps["save_state_to_disk"] = Mock(return_value=True)
        # reset_current_block modifies state in place and returns None
        # Don't mock it - use the real function to ensure proper behavior
        # deps["reset_current_block"] is already set to the real function in conftest
        
        # Execute grading
        result = grade_current_block(
            s=state,
            gr_module=mock_gradio_module,
            client=mock_openai_client,
            dependencies=deps
        )
        
        # Verify result
        assert result is not None
        updated_state = result[0]
        assert updated_state["asked_main"] == 1
    
    def test_grading_workflow_error_handling(self, mock_state, mock_openai_client, mock_gradio_module, mock_dependencies_exam_flow):
        """
        Integration test: Grading workflow error handling.
        
        Tests: AI API failure → Error handling → User-friendly message
        """
        # Initialize state
        time_provider = MockTimeProvider(initial_time=1000.0)
        state = ensure_state(mock_state, time_provider=time_provider)
        
        # Set up state for grading
        state["phase"] = "awaiting_main_answer"
        state["current"] = {
            "main_question": "What is the main idea?",
            "answers": ["This is my answer"],
            "followups_done": 0,
            "target_followups": 1,
            "q_time": 1000.0,
            "short_attempts": 0,
            "ctx": "Test context"
        }
        
        # Mock AI API failure
        mock_openai_client.chat.completions.create.side_effect = Exception("API Error")
        
        # Mock dependencies
        deps = mock_dependencies_exam_flow
        deps["_categorize_error"] = Mock(return_value=(
            "API_ERROR",
            {
                "type": "API_ERROR",
                "message": "Unable to grade answer. Please try again.",
                "retry": True,
                "_internal_error": "API Error"
            }
        ))
        
        # Execute grading (should handle error gracefully)
        result = grade_current_block(
            s=state,
            gr_module=mock_gradio_module,
            client=mock_openai_client,
            dependencies=deps
        )
        
        # Verify error handled gracefully
        assert result is not None
        status_update = result[2]  # Status update should contain error message
        
        # Verify state not corrupted
        updated_state = result[0]
        assert "session_id" in updated_state
        assert updated_state["phase"] in ["awaiting_main_answer", "idle"]  # Should not be corrupted
    
    def test_grading_workflow_state_persistence(self, mock_state, mock_openai_client, mock_gradio_module, mock_dependencies_exam_flow):
        """
        Integration test: Grading workflow with state persistence.
        
        Tests: Grading → State update → Persistence → Verify saved
        """
        # Initialize state
        time_provider = MockTimeProvider(initial_time=1000.0)
        state = ensure_state(mock_state, time_provider=time_provider)
        
        # Set up state for grading
        state["phase"] = "awaiting_main_answer"
        state["current"] = {
            "main_question": "What is the main idea?",
            "answers": ["This is my answer"],
            "followups_done": 0,
            "target_followups": 1,
            "q_time": 1000.0,
            "short_attempts": 0,
            "ctx": "Test context"
        }
        state["asked_main"] = 0
        state["limit"] = 1
        
        # Mock AI response
        mock_response = Mock()
        mock_response.usage = Mock()
        mock_response.usage.total_tokens = 150
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Score: 85/100. Feedback: Good answer."
        
        mock_openai_client.chat.completions.create.return_value = mock_response
        
        # Mock dependencies with real save_state_to_disk
        deps = mock_dependencies_exam_flow
        # _parse_feedback returns tuple: (scores_dict, feedback_text)
        deps["_parse_feedback"] = Mock(return_value=(
            {"Conceptual": 85, "Analytical": 85, "Application": 85, "Reflection": 85, "Overall": 85},
            "Good answer"
        ))
        deps["_calculate_overall_score"] = Mock(return_value=85.0)
        deps["tts_to_mp3"] = Mock(return_value="/tmp/test.mp3")
        deps["get_audio_duration"] = Mock(return_value=5.0)
        
        # Track save calls
        save_calls = []
        original_save = deps["save_state_to_disk"]
        def tracked_save(s):
            save_calls.append(s)
            return original_save(s)
        deps["save_state_to_disk"] = tracked_save
        
        # Execute grading
        result = grade_current_block(
            s=state,
            gr_module=mock_gradio_module,
            client=mock_openai_client,
            dependencies=deps
        )
        
        # Verify state was saved
        assert len(save_calls) > 0, "State should be saved after grading"
        
        # Verify saved state has updated scores
        saved_state = save_calls[-1]
        assert len(saved_state["scores"]) > 0, "Saved state should have scores"

