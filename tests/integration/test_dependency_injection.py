"""
Integration tests for dependency injection wiring.

These tests verify that the dependency injection system works correctly
and that all handlers can receive dependencies as expected.
"""

import pytest
from tests.helpers import assert_dependencies_structure


class TestExamFlowDependencies:
    """Tests for exam flow dependency injection."""
    
    def test_exam_flow_dependencies_structure(self, mock_dependencies_exam_flow):
        """Test that exam flow dependencies have required structure."""
        deps = mock_dependencies_exam_flow
        
        required_keys = [
            "ensure_state",
            "reset_current_block",
            "get_followup_range",
            "save_state_to_disk",
            "get_chunks",
            "with_retry",
            "_log_token_usage",
            "_sanitize_for_prompt",
        ]
        
        assert_dependencies_structure(deps, required_keys)
    
    def test_exam_flow_dependencies_callable(self, mock_dependencies_exam_flow):
        """Test that exam flow dependencies are callable functions."""
        deps = mock_dependencies_exam_flow
        
        # Test that key dependencies are callable
        assert callable(deps["ensure_state"])
        assert callable(deps["reset_current_block"])
        assert callable(deps["get_followup_range"])
        assert callable(deps["with_retry"])


class TestDashDependencies:
    """Tests for dash dependency injection."""
    
    def test_dash_dependencies_structure(self, mock_dependencies_dash):
        """Test that dash dependencies have required structure."""
        deps = mock_dependencies_dash
        
        required_keys = [
            "parse_professor_link_and_setup",
            "instructor_decrypt",
            "get_cache_entry",
            "set_cache_entry",
            "TRANSCRIPT_CACHE_TIMEOUT_SECONDS",
        ]
        
        assert_dependencies_structure(deps, required_keys)
    
    def test_dash_dependencies_callable(self, mock_dependencies_dash):
        """Test that dash dependencies are callable functions."""
        deps = mock_dependencies_dash
        
        assert callable(deps["parse_professor_link_and_setup"])
        assert callable(deps["instructor_decrypt"])
        assert callable(deps["get_cache_entry"])


class TestProfDependencies:
    """Tests for prof dependency injection."""
    
    def test_prof_dependencies_structure(self, mock_dependencies_prof):
        """Test that prof dependencies have required structure."""
        deps = mock_dependencies_prof
        
        required_keys = [
            "validate_pdf_and_calculate_chunks",
            "encode_config_to_url",
            "generate_secure_passphrase",
            "calculate_max_duration",
        ]
        
        assert_dependencies_structure(deps, required_keys)
    
    def test_prof_dependencies_callable(self, mock_dependencies_prof):
        """Test that prof dependencies are callable functions."""
        deps = mock_dependencies_prof
        
        assert callable(deps["validate_pdf_and_calculate_chunks"])
        assert callable(deps["encode_config_to_url"])
        assert callable(deps["generate_secure_passphrase"])

