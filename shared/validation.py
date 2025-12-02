"""
Common validation functions.

This module provides reusable validation functions to reduce duplication
and improve Principle #2 (SSOT) and Principle #1 (Minimal Code).
"""

import os
from typing import Tuple, Optional
from shared.error_formatter import format_validation_error


class ValidationResult:
    """
    Standardized validation result.
    
    Provides consistent return format for all validation functions.
    """
    
    def __init__(
        self,
        is_valid: bool,
        error_message: str = "",
        solution: Optional[str] = None
    ):
        """
        Initialize validation result.
        
        Args:
            is_valid: True if validation passed
            error_message: Error message if validation failed
            solution: Optional solution or suggestion
        """
        self.is_valid = is_valid
        self.error_message = error_message
        self.solution = solution
    
    def to_error_dict(self) -> dict:
        """
        Convert to error dictionary format.
        
        Returns:
            Dictionary with error information (empty if valid)
        """
        if self.is_valid:
            return {}
        
        return {
            "type": "VALIDATION_ERROR",
            "message": self.error_message,
            "solution": self.solution or ""
        }
    
    def to_formatted_message(self) -> str:
        """
        Convert to formatted error message.
        
        Returns:
            Formatted error message string (empty if valid)
        """
        if self.is_valid:
            return ""
        
        return format_validation_error(
            "Input",
            self.error_message,
            self.solution
        )


def validate_files_uploaded(files: list) -> ValidationResult:
    """
    Validate that files are uploaded.
    
    Args:
        files: List of files
        
    Returns:
        ValidationResult
    """
    if not files:
        return ValidationResult(
            is_valid=False,
            error_message="No files uploaded",
            solution="Please upload one or more .enc files"
        )
    return ValidationResult(is_valid=True)


def validate_passphrase(passphrase: str, min_length: int = 4) -> ValidationResult:
    """
    Validate passphrase.
    
    Args:
        passphrase: Passphrase to validate
        min_length: Minimum length required
        
    Returns:
        ValidationResult
    """
    if not passphrase or not passphrase.strip():
        return ValidationResult(
            is_valid=False,
            error_message="Passphrase is required",
            solution="Please enter the passphrase to decrypt files"
        )
    
    if len(passphrase.strip()) < min_length:
        return ValidationResult(
            is_valid=False,
            error_message=f"Passphrase seems short (minimum {min_length} characters)",
            solution="Verify the passphrase is correct before proceeding"
        )
    
    return ValidationResult(is_valid=True)


def validate_url(url: str, url_type: str = "exam configuration") -> ValidationResult:
    """
    Validate URL.
    
    Args:
        url: URL to validate
        url_type: Type of URL (for error messages)
        
    Returns:
        ValidationResult
    """
    if not url or not url.strip():
        return ValidationResult(
            is_valid=False,
            error_message=f"{url_type} URL is required",
            solution=f"Please provide a valid {url_type} URL"
        )
    
    # Basic URL validation
    url_stripped = url.strip()
    if not (url_stripped.startswith("http://") or url_stripped.startswith("https://")):
        return ValidationResult(
            is_valid=False,
            error_message=f"Invalid {url_type} URL format",
            solution="URL must start with http:// or https://"
        )
    
    # SECURITY: Require HTTPS in production, allow HTTP in development
    environment = os.getenv("ENVIRONMENT", "development").lower()
    if environment == "production":
        if not url_stripped.startswith("https://"):
            return ValidationResult(
                is_valid=False,
                error_message=f"HTTPS required for {url_type} URL in production",
                solution="URL must start with https:// (HTTPS required for security in production)"
            )
    
    return ValidationResult(is_valid=True)


def validate_non_empty(value: any, field_name: str) -> ValidationResult:
    """
    Validate that a value is not empty.
    
    Args:
        value: Value to validate
        field_name: Name of the field (for error messages)
        
    Returns:
        ValidationResult
    """
    if value is None:
        return ValidationResult(
            is_valid=False,
            error_message=f"{field_name} is required",
            solution=f"Please provide a value for {field_name}"
        )
    
    if isinstance(value, str) and not value.strip():
        return ValidationResult(
            is_valid=False,
            error_message=f"{field_name} cannot be empty",
            solution=f"Please provide a non-empty value for {field_name}"
        )
    
    if isinstance(value, (list, dict)) and len(value) == 0:
        return ValidationResult(
            is_valid=False,
            error_message=f"{field_name} cannot be empty",
            solution=f"Please provide at least one item for {field_name}"
        )
    
    return ValidationResult(is_valid=True)


def validate_range(
    value: float,
    field_name: str,
    min_value: float,
    max_value: float
) -> ValidationResult:
    """
    Validate that a value is within a range.
    
    Args:
        value: Value to validate
        field_name: Name of the field
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        
    Returns:
        ValidationResult
    """
    if value < min_value or value > max_value:
        return ValidationResult(
            is_valid=False,
            error_message=f"{field_name} must be between {min_value} and {max_value}",
            solution=f"Please provide a value between {min_value} and {max_value}"
        )
    
    return ValidationResult(is_valid=True)

