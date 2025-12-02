"""
Error info factory for standardized error information.

This module provides utilities for creating standardized error info dictionaries
to reduce duplication and ensure consistent error handling across handlers.
"""

from typing import Optional, Dict, Any
from enum import Enum
from shared.constants import MAX_FILE_SIZE  # SSOT - Principle #2


class ErrorType(Enum):
    """Standard error types for consistent error handling."""
    
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_SIZE_ERROR = "FILE_SIZE_ERROR"
    INVALID_PATH = "INVALID_PATH"
    DECRYPTION_FAILED = "DECRYPTION_FAILED"
    DECRYPTION_ERROR = "DECRYPTION_ERROR"
    INVALID_FILE_FORMAT = "INVALID_FILE_FORMAT"
    PARSING_ERROR = "PARSING_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    API_ERROR = "API_ERROR"


def create_error_info(
    error_type: ErrorType,
    message: str,
    solution: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create standardized error info dictionary.
    
    **Contract**:
    - **Inputs**: Error type enum, message string, optional solution string, optional context dict
    - **Outputs**: Standardized error info dictionary
    - **Invariants**: Error type must be valid ErrorType enum value
    - **Failure Modes**: Never raises exceptions (always returns valid dict)
    
    This function creates consistent error info dictionaries used throughout
    the codebase for error handling and reporting.
    
    Args:
        error_type: Error type enum value (must be valid ErrorType)
        message: Human-readable error message (user-facing, no implementation details)
        solution: Optional solution or suggestion for the user
        context: Optional context dictionary with additional error details
        
    Returns:
        Standardized error info dictionary with keys:
        - type: Error type string (from ErrorType enum)
        - message: Error message (user-friendly)
        - solution: Solution/suggestion (empty string if not provided)
        - context: Context dictionary (if provided, otherwise omitted)
        
    Raises:
        Never raises exceptions. Always returns valid dictionary.
        
    Example:
        ```python
        error_info = create_error_info(
            ErrorType.FILE_NOT_FOUND,
            f"File not found: {filename}",
            "File may have been moved or deleted. Please re-upload."
        )
        ```
    """
    error_info = {
        "type": error_type.value,
        "message": message,
        "solution": solution or ""
    }
    
    if context:
        error_info["context"] = context
    
    return error_info


# Predefined error info creators for common error cases

def file_not_found_error(filename: str) -> Dict[str, Any]:
    """
    Create file not found error info.
    
    Args:
        filename: Name of the file that was not found
        
    Returns:
        Error info dictionary
    """
    return create_error_info(
        ErrorType.FILE_NOT_FOUND,
        f"File not found: {filename}",
        "File may have been moved or deleted. Please re-upload."
    )


def file_too_large_error(size_mb: float, max_mb: Optional[float] = None) -> Dict[str, Any]:
    """
    Create file too large error info.
    
    Args:
        size_mb: Actual file size in MB
        max_mb: Maximum allowed file size in MB (defaults to MAX_FILE_SIZE from constants)
        
    Returns:
        Error info dictionary
    """
    if max_mb is None:
        max_mb = MAX_FILE_SIZE / (1024 * 1024)  # Convert bytes to MB
    
    return create_error_info(
        ErrorType.FILE_TOO_LARGE,
        f"File too large: {size_mb:.1f}MB (max {max_mb:.0f}MB)",
        f"Please use a file smaller than {max_mb:.0f}MB"
    )


def file_size_error(error_details: str) -> Dict[str, Any]:
    """
    Create file size determination error info.
    
    Args:
        error_details: Error details from size check
        
    Returns:
        Error info dictionary
    """
    return create_error_info(
        ErrorType.FILE_SIZE_ERROR,
        f"Could not determine file size: {error_details[:50]}",
        "File may be corrupted or inaccessible"
    )


def invalid_path_error() -> Dict[str, Any]:
    """
    Create invalid path error info.
    
    Returns:
        Error info dictionary
    """
    return create_error_info(
        ErrorType.INVALID_PATH,
        "Could not determine file path",
        "Please re-upload the file"
    )


def decryption_failed_error() -> Dict[str, Any]:
    """
    Create decryption failed error info (wrong passphrase).
    
    Returns:
        Error info dictionary
    """
    return create_error_info(
        ErrorType.DECRYPTION_FAILED,
        "Decryption failed - wrong passphrase",
        "Please verify the passphrase is correct"
    )


def decryption_error(error_details: str) -> Dict[str, Any]:
    """
    Create general decryption error info.
    
    Args:
        error_details: Error details from decryption attempt
        
    Returns:
        Error info dictionary
    """
    return create_error_info(
        ErrorType.DECRYPTION_ERROR,
        f"Decryption error: {error_details[:50]}",
        "File may be corrupted or passphrase incorrect"
    )


def invalid_file_format_error(error_details: str) -> Dict[str, Any]:
    """
    Create invalid file format error info.
    
    Args:
        error_details: Error details from parsing attempt
        
    Returns:
        Error info dictionary
    """
    return create_error_info(
        ErrorType.INVALID_FILE_FORMAT,
        f"Invalid file format: {error_details[:50]}",
        "File may be corrupted or not a valid .enc file"
    )


def parsing_error(error_type: str) -> Dict[str, Any]:
    """
    Create parsing error info.
    
    Args:
        error_type: Type of parsing error
        
    Returns:
        Error info dictionary
    """
    return create_error_info(
        ErrorType.PARSING_ERROR,
        f"Could not parse transcript: {error_type}",
        "File may be corrupted or in unexpected format"
    )


def unexpected_error(error_details: str) -> Dict[str, Any]:
    """
    Create unexpected error info.
    
    Args:
        error_details: Error details (truncated to 100 chars)
        
    Returns:
        Error info dictionary
    """
    return create_error_info(
        ErrorType.UNEXPECTED_ERROR,
        f"Unexpected error: {error_details[:100]}",
        "Please contact support with error details"
    )

