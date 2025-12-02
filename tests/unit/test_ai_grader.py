"""
Unit tests for exam.ai.grader module.

Tests cover feedback parsing, score calculation, and grading logic.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from exam.ai.grader import (
    _parse_feedback,
    _calculate_overall_score,
    _extract_scores,
    grade_current_block
)


class TestParseFeedback:
    """Tests for _parse_feedback function."""
    
    def test_parse_feedback_complete(self):
        """Test parsing complete feedback with all fields."""
        fb_raw = """
        Conceptual: 85
        Analytical: 90
        Application: 80
        Reflection: 75
        Overall: 82
        Feedback: This is a comprehensive answer that demonstrates good understanding.
        """
        
        scores_dict, feedback_text = _parse_feedback(fb_raw)
        
        assert scores_dict["Conceptual"] == 85
        assert scores_dict["Analytical"] == 90
        assert scores_dict["Application"] == 80
        assert scores_dict["Reflection"] == 75
        assert scores_dict["Overall"] == 82
        assert "comprehensive answer" in feedback_text.lower()
    
    def test_parse_feedback_missing_fields(self):
        """Test parsing feedback with missing fields."""
        fb_raw = """
        Conceptual: 70
        Analytical: 75
        Feedback: Good work.
        """
        
        scores_dict, feedback_text = _parse_feedback(fb_raw)
        
        assert scores_dict["Conceptual"] == 70
        assert scores_dict["Analytical"] == 75
        # Missing fields should use fallback (60)
        assert scores_dict["Application"] == 60
        assert scores_dict["Reflection"] == 60
        assert scores_dict["Overall"] == 60
        assert feedback_text == "Good work."
    
    def test_parse_feedback_no_feedback_text(self):
        """Test parsing feedback without feedback text."""
        fb_raw = """
        Conceptual: 80
        Analytical: 85
        Application: 75
        Reflection: 70
        """
        
        scores_dict, feedback_text = _parse_feedback(fb_raw)
        
        assert scores_dict["Conceptual"] == 80
        # Should use fallback feedback text
        assert feedback_text == "Evaluation completed."
    
    def test_parse_feedback_case_insensitive(self):
        """Test that field names are case-insensitive."""
        fb_raw = """
        conceptual: 85
        ANALYTICAL: 90
        Application: 80
        reflection: 75
        Feedback: Case insensitive test
        """
        
        scores_dict, feedback_text = _parse_feedback(fb_raw)
        
        assert scores_dict["Conceptual"] == 85
        assert scores_dict["Analytical"] == 90
        assert scores_dict["Application"] == 80
        assert scores_dict["Reflection"] == 75
        assert "case insensitive" in feedback_text.lower()
    
    def test_parse_feedback_score_bounds(self):
        """Test that scores are clamped to 0-100 range."""
        fb_raw = """
        Conceptual: 150
        Analytical: 200
        Application: 50
        Reflection: 0
        Overall: 100
        Feedback: Score bounds test
        """
        
        scores_dict, feedback_text = _parse_feedback(fb_raw)
        
        # Scores should be clamped (negative numbers won't match regex, so use fallback)
        assert scores_dict["Conceptual"] == 100  # Clamped from 150
        assert scores_dict["Analytical"] == 100  # Clamped from 200
        assert scores_dict["Application"] == 50
        assert scores_dict["Reflection"] == 0
        assert scores_dict["Overall"] == 100
    
    def test_parse_feedback_multiline_feedback(self):
        """Test parsing multiline feedback text."""
        fb_raw = """
        Conceptual: 85
        Analytical: 90
        Feedback: This is a multi-line
        feedback that spans
        multiple lines.
        Application: 80
        """
        
        scores_dict, feedback_text = _parse_feedback(fb_raw)
        
        assert scores_dict["Conceptual"] == 85
        assert scores_dict["Analytical"] == 90
        # Feedback regex includes content until end or next field
        # The actual behavior includes the next field line
        assert "multi-line" in feedback_text
        assert "multiple lines" in feedback_text
        # Note: The regex includes the next field in feedback (actual behavior)
    
    def test_parse_feedback_empty_string(self):
        """Test parsing empty feedback string."""
        fb_raw = ""
        
        scores_dict, feedback_text = _parse_feedback(fb_raw)
        
        # All fields should use fallback
        assert all(score == 60 for score in scores_dict.values())
        assert feedback_text == "Evaluation completed."


class TestCalculateOverallScore:
    """Tests for _calculate_overall_score function."""
    
    def test_calculate_overall_score_complete(self):
        """Test calculating overall score with all dimensions."""
        scores_dict = {
            "Conceptual": 80,
            "Analytical": 85,
            "Application": 75,
            "Reflection": 70
        }
        
        overall = _calculate_overall_score(scores_dict)
        
        # Average of 80, 85, 75, 70 = 77.5 -> 78 (rounded)
        assert overall == 78
    
    def test_calculate_overall_score_missing_fields(self):
        """Test calculating overall score with missing fields."""
        scores_dict = {
            "Conceptual": 80,
            "Analytical": 85
            # Missing Application and Reflection
        }
        
        overall = _calculate_overall_score(scores_dict)
        
        # Average of 80, 85, 60 (fallback), 60 (fallback) = 71.25 -> 71
        assert overall == 71
    
    def test_calculate_overall_score_empty_dict(self):
        """Test calculating overall score with empty dict."""
        scores_dict = {}
        
        overall = _calculate_overall_score(scores_dict)
        
        # All fallbacks (60) -> average = 60
        assert overall == 60
    
    def test_calculate_overall_score_rounding(self):
        """Test that scores are properly rounded."""
        scores_dict = {
            "Conceptual": 83,
            "Analytical": 84,
            "Application": 82,
            "Reflection": 83
        }
        
        overall = _calculate_overall_score(scores_dict)
        
        # Average of 83, 84, 82, 83 = 83.0 -> 83
        assert overall == 83
    
    def test_calculate_overall_score_boundary_values(self):
        """Test with boundary values (0 and 100)."""
        scores_dict = {
            "Conceptual": 0,
            "Analytical": 100,
            "Application": 50,
            "Reflection": 50
        }
        
        overall = _calculate_overall_score(scores_dict)
        
        # Average of 0, 100, 50, 50 = 50
        assert overall == 50


class TestExtractScores:
    """Tests for _extract_scores function."""
    
    def test_extract_scores_complete(self):
        """Test extracting scores from complete feedback."""
        fb_raw = """
        Conceptual: 85
        Analytical: 90
        Application: 80
        Reflection: 75
        Feedback: Good answer
        """
        
        scores_dict = _extract_scores(fb_raw)
        
        assert scores_dict["Conceptual"] == 85
        assert scores_dict["Analytical"] == 90
        assert scores_dict["Application"] == 80
        assert scores_dict["Reflection"] == 75
        # Overall should be calculated (average of 85, 90, 80, 75 = 82.5 -> 82 with banker's rounding)
        assert scores_dict["Overall"] == 82
    
    def test_extract_scores_overrides_overall(self):
        """Test that calculated Overall overrides any provided Overall."""
        fb_raw = """
        Conceptual: 80
        Analytical: 85
        Application: 75
        Reflection: 70
        Overall: 100
        Feedback: Test
        """
        
        scores_dict = _extract_scores(fb_raw)
        
        # Overall should be calculated, not the provided value
        # Average of 80, 85, 75, 70 = 77.5 -> 78
        assert scores_dict["Overall"] == 78
    
    def test_extract_scores_missing_fields(self):
        """Test extracting scores with missing fields."""
        fb_raw = """
        Conceptual: 70
        Feedback: Partial feedback
        """
        
        scores_dict = _extract_scores(fb_raw)
        
        assert scores_dict["Conceptual"] == 70
        # Missing fields use fallback (60)
        assert scores_dict["Analytical"] == 60
        assert scores_dict["Application"] == 60
        assert scores_dict["Reflection"] == 60
        # Overall calculated from 70, 60, 60, 60 = 62.5 -> 62 with banker's rounding
        assert scores_dict["Overall"] == 62


class TestGradeCurrentBlock:
    """Tests for grade_current_block function."""
    
    @pytest.fixture
    def mock_state(self):
        """Create a mock state for testing."""
        return {
            "session_id": "test_session",
            "current": {
                "main_question": "What is Python?",
                "answers": ["Python is a programming language"]
            },
            "history": [],
            "rubrics": [],
            "scores": [],
            "asked_main": 0,
            "proctor_state": None,
            "proctor_blocks": []
        }
    
    @pytest.fixture
    def mock_openai_client(self):
        """Create a mock OpenAI client."""
        client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = """
        Conceptual: 85
        Analytical: 90
        Application: 80
        Reflection: 75
        Feedback: Good understanding of the concept.
        """
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_response.model = "gpt-4o-mini"
        
        client.chat.completions.create.return_value = mock_response
        return client
    
    def test_grade_current_block_basic(self, mock_state, mock_openai_client):
        """Test basic grading flow."""
        def mock_ensure_state(s):
            return s
        
        def mock_save_state(s):
            return True
        
        def mock_reset_block(s):
            pass
        
        def mock_get_chunks():
            return []
        
        result = grade_current_block(
            mock_state,
            mock_openai_client,
            mock_ensure_state,
            mock_save_state,
            mock_reset_block,
            mock_get_chunks
        )
        
        # Should have added rubric and score
        assert len(result["rubrics"]) == 1
        assert len(result["scores"]) == 1
        assert result["rubrics"][0]["Conceptual"] == 85
        assert result["rubrics"][0]["Analytical"] == 90
        assert result["scores"][0] == 82  # Average of 85, 90, 80, 75 = 82.5 -> 82 (banker's rounding)
        assert result["asked_main"] == 1
    
    def test_grade_current_block_no_answers(self, mock_openai_client):
        """Test grading with no answers."""
        state = {
            "session_id": "test_session",
            "current": {
                "main_question": "What is Python?",
                "answers": []
            },
            "history": [],
            "rubrics": [],
            "scores": [],
            "asked_main": 0
        }
        
        def mock_ensure_state(s):
            return s
        
        def mock_save_state(s):
            return True
        
        def mock_reset_block(s):
            pass
        
        def mock_get_chunks():
            return []
        
        result = grade_current_block(
            state,
            mock_openai_client,
            mock_ensure_state,
            mock_save_state,
            mock_reset_block,
            mock_get_chunks
        )
        
        # Should still process (though with empty answers)
        assert "history" in result
    
    def test_grade_current_block_with_progress(self, mock_state, mock_openai_client):
        """Test grading with progress callback."""
        progress_calls = []
        
        def mock_progress(value):
            progress_calls.append(value)
        
        def mock_ensure_state(s):
            return s
        
        def mock_save_state(s):
            return True
        
        def mock_reset_block(s):
            pass
        
        def mock_get_chunks():
            return []
        
        result = grade_current_block(
            mock_state,
            mock_openai_client,
            mock_ensure_state,
            mock_save_state,
            mock_reset_block,
            mock_get_chunks,
            progress=mock_progress
        )
        
        # Should have called progress
        assert len(progress_calls) > 0
        assert progress_calls[-1] == 1.0  # Should end at 100%
    
    def test_grade_current_block_error_handling(self, mock_state):
        """Test error handling in grading."""
        # Create a client that raises an error
        error_client = Mock()
        error_client.chat.completions.create.side_effect = Exception("API Error")
        
        def mock_ensure_state(s):
            return s
        
        def mock_save_state(s):
            return True
        
        def mock_reset_block(s):
            pass
        
        def mock_get_chunks():
            return []
        
        result = grade_current_block(
            mock_state,
            error_client,
            mock_ensure_state,
            mock_save_state,
            mock_reset_block,
            mock_get_chunks
        )
        
        # Should handle error gracefully
        assert "history" in result
        # Should have error message in history
        assert any("Error" in msg.get("content", "") for msg in result["history"])

