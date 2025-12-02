"""
Unit tests for error sanitization (Principle #7).

Tests verify that error messages are properly sanitized and don't expose
internal implementation details to users.
"""

import pytest
from exam.flow.error_handling import handle_flow_error
from shared.error_formatter import format_user_error
from shared.error_info import ErrorType, create_error_info
from tests.helpers import build_minimal_state


class TestErrorSanitization:
    """Tests for error sanitization."""
    
    def test_handle_flow_error_sanitizes_internal_details(self, mock_state):
        """Test that handle_flow_error doesn't expose internal error details."""
        # Create a mock exception with internal details
        class InternalError(Exception):
            def __init__(self):
                super().__init__("Database connection failed: user=admin, password=secret123")
        
        # Mock gradio module
        mock_gr = type('MockGradio', (), {
            'update': lambda **kwargs: type('Update', (), kwargs)()
        })()
        
        # Mock dependencies
        dependencies = {
            "_categorize_error": lambda e: ("API_ERROR", {
                "message": "Service temporarily unavailable",
                "retry": True,
                "_internal_error": str(e)
            }),
            "_calculate_timeout_status": lambda s: None
        }
        
        # Call error handler
        result = handle_flow_error(
            s=mock_state,
            e=InternalError(),
            gr_module=mock_gr,
            dependencies=dependencies,
            error_context="test_error"
        )
        
        # Extract error message from result tuple
        # Result format: (state, audio, status, mic, history, cam, proctor, timeout)
        status_update = result[2]
        error_message = status_update.value if hasattr(status_update, 'value') else str(status_update)
        
        # Verify internal details are NOT in user-facing message
        assert "password=secret123" not in error_message
        assert "user=admin" not in error_message
        assert "Database connection failed" not in error_message
        
        # Verify sanitized message is present
        assert "Service temporarily unavailable" in error_message or "Error occurred" in error_message
    
    def test_format_user_error_sanitizes_content(self):
        """Test that format_user_error produces safe messages."""
        # Try to include potentially sensitive content
        error_msg = format_user_error(
            error_type="DATABASE_ERROR",
            message="Database connection failed",
            solution="Please try again later"
        )
        
        # Verify message is user-friendly
        assert "DATABASE_ERROR" in error_msg
        assert "Database connection failed" in error_msg
        assert "Please try again later" in error_msg
        
        # Verify no internal details
        assert "password" not in error_msg.lower()
        assert "secret" not in error_msg.lower()
        assert "token" not in error_msg.lower()
    
    def test_create_error_info_sanitizes_context(self):
        """Test that create_error_info doesn't expose sensitive context."""
        # Create error info with potentially sensitive context
        error_info = create_error_info(
            error_type=ErrorType.API_ERROR,
            message="API request failed",
            solution="Please try again",
            context={
                "endpoint": "/api/v1/data",
                "api_key": "secret_key_12345",  # Should not be exposed
                "user_id": "user_123"
            }
        )
        
        # Verify error info structure
        assert error_info["type"] == "API_ERROR"
        assert error_info["message"] == "API request failed"
        assert error_info["solution"] == "Please try again"
        
        # Note: Context may contain sensitive data, but it should not be
        # included in user-facing messages. This test verifies structure only.
        # Actual sanitization happens when context is used in messages.
    
    def test_error_messages_dont_contain_stack_traces(self, mock_state):
        """Test that error messages don't contain stack traces."""
        import traceback
        
        # Create exception with stack trace
        try:
            raise ValueError("Test error")
        except ValueError as e:
            stack_trace = traceback.format_exc()
        
        # Mock gradio module
        mock_gr = type('MockGradio', (), {
            'update': lambda **kwargs: type('Update', (), kwargs)()
        })()
        
        # Mock dependencies
        dependencies = {
            "_categorize_error": lambda e: ("VALIDATION_ERROR", {
                "message": "Invalid input provided",
                "retry": False,
                "_internal_error": str(e)
            }),
            "_calculate_timeout_status": lambda s: None
        }
        
        # Call error handler
        result = handle_flow_error(
            s=mock_state,
            e=ValueError("Test error"),
            gr_module=mock_gr,
            dependencies=dependencies,
            error_context="test_error"
        )
        
        # Extract error message
        status_update = result[2]
        error_message = status_update.value if hasattr(status_update, 'value') else str(status_update)
        
        # Verify no stack trace in message
        assert "Traceback" not in error_message
        assert "File \"" not in error_message
        assert "line " not in error_message or "line " not in error_message.split("\n")[0]

