"""
Standardized error message formatting.

This module provides consistent error message formatting across the codebase,
improving Principle #8 (Consistency Everywhere) while preserving wiring.
"""

from typing import Optional


def format_user_error(
    error_type: str,
    message: str,
    solution: Optional[str] = None
) -> str:
    """
    Format standardized user-facing error message.
    
    All user-facing errors should use this formatter for consistency.
    
    Args:
        error_type: Error type (e.g., "VALIDATION_ERROR", "DECRYPTION_FAILED")
        message: Error message
        solution: Optional solution or suggestion
        
    Returns:
        Formatted error message string
    """
    parts = [f"❌ {error_type}: {message}"]
    
    if solution:
        parts.append(f"\n\n💡 Solution: {solution}")
    
    return "\n".join(parts)


def format_validation_error(
    field: str,
    issue: str,
    solution: Optional[str] = None
) -> str:
    """
    Format validation error message.
    
    Args:
        field: Field name that failed validation
        issue: Description of the issue
        solution: Optional solution
        
    Returns:
        Formatted validation error message
    """
    message = f"{field}: {issue}"
    return format_user_error("VALIDATION_ERROR", message, solution)


def format_status_message(
    success: bool,
    message: str,
    details: Optional[str] = None
) -> str:
    """
    Format status message (success or error).
    
    Args:
        success: True for success, False for error
        message: Status message
        details: Optional additional details
        
    Returns:
        Formatted status message
    """
    prefix = "✅" if success else "❌"
    parts = [f"{prefix} {message}"]
    
    if details:
        parts.append(f"\n{details}")
    
    return "\n".join(parts)


def format_info_message(message: str, details: Optional[str] = None) -> str:
    """
    Format informational message.
    
    Args:
        message: Info message
        details: Optional additional details
        
    Returns:
        Formatted info message
    """
    parts = [f"ℹ️ {message}"]
    
    if details:
        parts.append(f"\n{details}")
    
    return "\n".join(parts)

