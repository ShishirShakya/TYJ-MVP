"""
Unit tests for shared/error_formatter.py.

Tests error message formatting functions.
"""

import pytest
from shared.error_formatter import (
    format_user_error,
    format_validation_error,
    format_status_message,
    format_info_message
)


class TestFormatUserError:
    """Tests for format_user_error function."""
    
    def test_format_user_error_basic(self):
        """Test basic error formatting."""
        result = format_user_error("TEST_ERROR", "Test message")
        
        assert "TEST_ERROR" in result
        assert "Test message" in result
        assert "❌" in result
    
    def test_format_user_error_with_solution(self):
        """Test error formatting with solution."""
        result = format_user_error("TEST_ERROR", "Test message", "Test solution")
        
        assert "Test message" in result
        assert "Test solution" in result
        assert "Solution" in result
    
    def test_format_user_error_no_solution(self):
        """Test error formatting without solution."""
        result = format_user_error("TEST_ERROR", "Test message")
        
        assert "Test message" in result
        assert "Solution" not in result


class TestFormatValidationError:
    """Tests for format_validation_error function."""
    
    def test_format_validation_error_basic(self):
        """Test basic validation error formatting."""
        result = format_validation_error("test_field", "Invalid value")
        
        assert "test_field" in result
        assert "Invalid value" in result
        assert "VALIDATION_ERROR" in result
    
    def test_format_validation_error_with_solution(self):
        """Test validation error with solution."""
        result = format_validation_error("test_field", "Invalid value", "Use valid format")
        
        assert "test_field" in result
        assert "Invalid value" in result
        assert "Use valid format" in result
    
    def test_format_validation_error_no_solution(self):
        """Test validation error without solution."""
        result = format_validation_error("test_field", "Invalid value")
        
        assert "test_field" in result
        assert "Invalid value" in result


class TestFormatStatusMessage:
    """Tests for format_status_message function."""
    
    def test_format_status_message_success(self):
        """Test success status message formatting."""
        result = format_status_message(True, "Operation completed")
        
        assert "✅" in result
        assert "Operation completed" in result
        assert "❌" not in result
    
    def test_format_status_message_error(self):
        """Test error status message formatting."""
        result = format_status_message(False, "Operation failed")
        
        assert "❌" in result
        assert "Operation failed" in result
        assert "✅" not in result
    
    def test_format_status_message_with_details(self):
        """Test status message with details."""
        result = format_status_message(True, "Operation completed", "Additional info")
        
        assert "Operation completed" in result
        assert "Additional info" in result
    
    def test_format_status_message_no_details(self):
        """Test status message without details."""
        result = format_status_message(True, "Operation completed")
        
        assert "Operation completed" in result
        assert "\n\n" not in result or result.count("\n") == 0


class TestFormatInfoMessage:
    """Tests for format_info_message function."""
    
    def test_format_info_message_basic(self):
        """Test basic info message formatting."""
        result = format_info_message("Information message")
        
        assert "ℹ️" in result
        assert "Information message" in result
    
    def test_format_info_message_with_details(self):
        """Test info message with details."""
        result = format_info_message("Information message", "Additional details")
        
        assert "Information message" in result
        assert "Additional details" in result
    
    def test_format_info_message_no_details(self):
        """Test info message without details."""
        result = format_info_message("Information message")
        
        assert "Information message" in result
        assert "\n\n" not in result or result.count("\n") == 0

