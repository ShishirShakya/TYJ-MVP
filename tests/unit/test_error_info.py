"""
Unit tests for shared/error_info.py.

Tests error info factory functions.
"""

import pytest
from shared.error_info import (
    ErrorType,
    create_error_info,
    file_not_found_error,
    file_too_large_error,
    file_size_error,
    invalid_path_error,
    decryption_failed_error,
    decryption_error,
    invalid_file_format_error,
    parsing_error,
    unexpected_error
)


class TestErrorType:
    """Tests for ErrorType enum."""
    
    def test_error_type_values(self):
        """Test ErrorType enum has expected values."""
        assert ErrorType.FILE_NOT_FOUND.value == "FILE_NOT_FOUND"
        assert ErrorType.FILE_TOO_LARGE.value == "FILE_TOO_LARGE"
        assert ErrorType.DECRYPTION_FAILED.value == "DECRYPTION_FAILED"


class TestCreateErrorInfo:
    """Tests for create_error_info function."""
    
    def test_create_error_info_basic(self):
        """Test creating basic error info."""
        error_info = create_error_info(
            ErrorType.FILE_NOT_FOUND,
            "File not found",
            "Please check the file path"
        )
        
        assert error_info["type"] == "FILE_NOT_FOUND"
        assert error_info["message"] == "File not found"
        assert error_info["solution"] == "Please check the file path"
        assert "context" not in error_info
    
    def test_create_error_info_with_context(self):
        """Test creating error info with context."""
        error_info = create_error_info(
            ErrorType.DECRYPTION_FAILED,
            "Decryption failed",
            "Please check your passphrase",
            context={"filename": "test.enc", "attempt": 1}
        )
        
        assert error_info["type"] == "DECRYPTION_FAILED"
        assert error_info["context"] == {"filename": "test.enc", "attempt": 1}
    
    def test_create_error_info_no_solution(self):
        """Test creating error info without solution."""
        error_info = create_error_info(
            ErrorType.UNEXPECTED_ERROR,
            "Unexpected error occurred"
        )
        
        assert error_info["solution"] == ""
    
    def test_create_error_info_never_raises(self):
        """Test create_error_info never raises exceptions."""
        # Should handle all edge cases gracefully
        error_info = create_error_info(
            ErrorType.FILE_NOT_FOUND,
            "",
            None,
            context=None
        )
        
        assert isinstance(error_info, dict)
        assert error_info["type"] == "FILE_NOT_FOUND"


class TestPredefinedErrorCreators:
    """Tests for predefined error info creator functions."""
    
    def test_file_not_found_error(self):
        """Test file_not_found_error creator."""
        error_info = file_not_found_error("test.txt")
        
        assert error_info["type"] == "FILE_NOT_FOUND"
        assert "test.txt" in error_info["message"]
        assert error_info["solution"] != ""
    
    def test_file_too_large_error(self):
        """Test file_too_large_error creator."""
        error_info = file_too_large_error(10.5, max_mb=5.0)
        
        assert error_info["type"] == "FILE_TOO_LARGE"
        assert "10.5" in error_info["message"] or "10" in error_info["message"]
        assert "5" in error_info["message"]
    
    def test_decryption_failed_error(self):
        """Test decryption_failed_error creator."""
        error_info = decryption_failed_error()
        
        assert error_info["type"] == "DECRYPTION_FAILED"
        assert error_info["message"] != ""
    
    def test_invalid_file_format_error(self):
        """Test invalid_file_format_error creator."""
        error_info = invalid_file_format_error("test.xyz")
        
        assert error_info["type"] == "INVALID_FILE_FORMAT"
        assert "test.xyz" in error_info["message"]
    
    def test_parsing_error(self):
        """Test parsing_error creator."""
        error_info = parsing_error("config.json")
        
        assert error_info["type"] == "PARSING_ERROR"
        assert "config.json" in error_info["message"]
    
    def test_unexpected_error(self):
        """Test unexpected_error creator."""
        error_info = unexpected_error("Something went wrong")
        
        assert error_info["type"] == "UNEXPECTED_ERROR"
        assert "Something went wrong" in error_info["message"]

