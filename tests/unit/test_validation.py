"""
Unit tests for shared/validation.py.

Tests validation functions and ValidationResult class.
"""

import pytest
from shared.validation import (
    ValidationResult,
    validate_files_uploaded,
    validate_passphrase,
    validate_url,
    validate_non_empty,
    validate_range
)


class TestValidationResult:
    """Tests for ValidationResult class."""
    
    def test_validation_result_valid(self):
        """Test ValidationResult with valid result."""
        result = ValidationResult(is_valid=True)
        
        assert result.is_valid is True
        assert result.error_message == ""
        assert result.solution is None
        assert result.to_error_dict() == {}
        assert result.to_formatted_message() == ""
    
    def test_validation_result_invalid(self):
        """Test ValidationResult with invalid result."""
        result = ValidationResult(
            is_valid=False,
            error_message="Test error",
            solution="Test solution"
        )
        
        assert result.is_valid is False
        assert result.error_message == "Test error"
        assert result.solution == "Test solution"
        
        error_dict = result.to_error_dict()
        assert error_dict["type"] == "VALIDATION_ERROR"
        assert error_dict["message"] == "Test error"
        assert error_dict["solution"] == "Test solution"
        
        formatted = result.to_formatted_message()
        assert "Test error" in formatted
        assert "Test solution" in formatted
    
    def test_validation_result_no_solution(self):
        """Test ValidationResult without solution."""
        result = ValidationResult(
            is_valid=False,
            error_message="Test error"
        )
        
        error_dict = result.to_error_dict()
        assert error_dict["solution"] == ""


class TestValidateFilesUploaded:
    """Tests for validate_files_uploaded function."""
    
    def test_validate_files_uploaded_empty_list(self):
        """Test validation fails for empty file list."""
        result = validate_files_uploaded([])
        
        assert result.is_valid is False
        assert "No files uploaded" in result.error_message
        assert "upload" in result.solution.lower()
    
    def test_validate_files_uploaded_none(self):
        """Test validation fails for None."""
        result = validate_files_uploaded(None)
        
        assert result.is_valid is False
    
    def test_validate_files_uploaded_valid(self):
        """Test validation passes for non-empty list."""
        result = validate_files_uploaded(["file1.enc", "file2.enc"])
        
        assert result.is_valid is True
        assert result.error_message == ""


class TestValidatePassphrase:
    """Tests for validate_passphrase function."""
    
    def test_validate_passphrase_empty(self):
        """Test validation fails for empty passphrase."""
        result = validate_passphrase("")
        
        assert result.is_valid is False
        assert "required" in result.error_message.lower()
    
    def test_validate_passphrase_whitespace_only(self):
        """Test validation fails for whitespace-only passphrase."""
        result = validate_passphrase("   ")
        
        assert result.is_valid is False
    
    def test_validate_passphrase_too_short(self):
        """Test validation fails for passphrase shorter than minimum."""
        result = validate_passphrase("abc", min_length=4)
        
        assert result.is_valid is False
        assert "short" in result.error_message.lower()
    
    def test_validate_passphrase_valid(self):
        """Test validation passes for valid passphrase."""
        result = validate_passphrase("valid_passphrase")
        
        assert result.is_valid is True
    
    def test_validate_passphrase_custom_min_length(self):
        """Test validation with custom minimum length."""
        result = validate_passphrase("abc", min_length=2)
        
        assert result.is_valid is True


class TestValidateUrl:
    """Tests for validate_url function."""
    
    def test_validate_url_empty(self):
        """Test validation fails for empty URL."""
        result = validate_url("")
        
        assert result.is_valid is False
        assert "required" in result.error_message.lower()
    
    def test_validate_url_invalid_format(self):
        """Test validation fails for invalid URL format."""
        result = validate_url("not-a-url")
        
        assert result.is_valid is False
        assert "format" in result.error_message.lower()
    
    def test_validate_url_valid_http(self):
        """Test validation passes for HTTP URL."""
        result = validate_url("http://example.com")
        
        assert result.is_valid is True
    
    def test_validate_url_valid_https(self):
        """Test validation passes for HTTPS URL."""
        result = validate_url("https://example.com")
        
        assert result.is_valid is True
    
    def test_validate_url_custom_type(self):
        """Test validation with custom URL type."""
        result = validate_url("", url_type="custom type")
        
        assert "custom type" in result.error_message


class TestValidateNonEmpty:
    """Tests for validate_non_empty function."""
    
    def test_validate_non_empty_none(self):
        """Test validation fails for None."""
        result = validate_non_empty(None, "test_field")
        
        assert result.is_valid is False
        assert "test_field" in result.error_message
    
    def test_validate_non_empty_empty_string(self):
        """Test validation fails for empty string."""
        result = validate_non_empty("", "test_field")
        
        assert result.is_valid is False
    
    def test_validate_non_empty_whitespace_string(self):
        """Test validation fails for whitespace-only string."""
        result = validate_non_empty("   ", "test_field")
        
        assert result.is_valid is False
    
    def test_validate_non_empty_empty_list(self):
        """Test validation fails for empty list."""
        result = validate_non_empty([], "test_field")
        
        assert result.is_valid is False
    
    def test_validate_non_empty_empty_dict(self):
        """Test validation fails for empty dict."""
        result = validate_non_empty({}, "test_field")
        
        assert result.is_valid is False
    
    def test_validate_non_empty_valid_string(self):
        """Test validation passes for non-empty string."""
        result = validate_non_empty("valid", "test_field")
        
        assert result.is_valid is True
    
    def test_validate_non_empty_valid_list(self):
        """Test validation passes for non-empty list."""
        result = validate_non_empty([1, 2, 3], "test_field")
        
        assert result.is_valid is True
    
    def test_validate_non_empty_valid_dict(self):
        """Test validation passes for non-empty dict."""
        result = validate_non_empty({"key": "value"}, "test_field")
        
        assert result.is_valid is True


class TestValidateRange:
    """Tests for validate_range function."""
    
    def test_validate_range_below_minimum(self):
        """Test validation fails for value below minimum."""
        result = validate_range(5, "test_field", min_value=10, max_value=20)
        
        assert result.is_valid is False
        assert "between" in result.error_message.lower()
    
    def test_validate_range_above_maximum(self):
        """Test validation fails for value above maximum."""
        result = validate_range(25, "test_field", min_value=10, max_value=20)
        
        assert result.is_valid is False
    
    def test_validate_range_at_minimum(self):
        """Test validation passes for value at minimum."""
        result = validate_range(10, "test_field", min_value=10, max_value=20)
        
        assert result.is_valid is True
    
    def test_validate_range_at_maximum(self):
        """Test validation passes for value at maximum."""
        result = validate_range(20, "test_field", min_value=10, max_value=20)
        
        assert result.is_valid is True
    
    def test_validate_range_within_range(self):
        """Test validation passes for value within range."""
        result = validate_range(15, "test_field", min_value=10, max_value=20)
        
        assert result.is_valid is True

