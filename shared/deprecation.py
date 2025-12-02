"""
Deprecation utilities for marking and tracking deprecated features.

This module provides utilities for deprecating functions, classes, and modules
while maintaining backward compatibility and providing clear migration paths.

EVOLVABILITY: Supports deprecation process for future-proof design (Principle #15).
"""

import warnings
from typing import Optional, Callable, Any, Dict
from functools import wraps
from dataclasses import dataclass
from datetime import datetime


@dataclass
class DeprecationInfo:
    """
    Information about a deprecated feature.
    
    Attributes:
        version: Version when feature was deprecated
        removal_version: Version when feature will be removed
        reason: Reason for deprecation
        replacement: Replacement feature (if any)
        migration_guide: URL or path to migration guide (optional)
    """
    version: str
    removal_version: str
    reason: str
    replacement: Optional[str] = None
    migration_guide: Optional[str] = None


def deprecated(
    version: str,
    removal_version: str,
    reason: str,
    replacement: Optional[str] = None,
    migration_guide: Optional[str] = None
) -> Callable:
    """
    Decorator to mark a function as deprecated.
    
    EVOLVABILITY: Provides clear deprecation notices with migration paths (Principle #15).
    
    Args:
        version: Version when feature was deprecated (e.g., "2.0.0")
        removal_version: Version when feature will be removed (e.g., "3.0.0")
        reason: Reason for deprecation
        replacement: Replacement function/feature name (optional)
        migration_guide: URL or path to migration guide (optional)
        
    Returns:
        Decorated function that issues deprecation warning
        
    Example:
        ```python
        @deprecated(
            version="2.0.0",
            removal_version="3.0.0",
            reason="Use new_function instead",
            replacement="new_function"
        )
        def old_function():
            pass
        ```
    """
    def decorator(func: Callable) -> Callable:
        deprecation_info = DeprecationInfo(
            version=version,
            removal_version=removal_version,
            reason=reason,
            replacement=replacement,
            migration_guide=migration_guide
        )
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build deprecation message
            message = f"{func.__name__} is deprecated since version {version}."
            message += f" It will be removed in version {removal_version}."
            message += f" Reason: {reason}"
            
            if replacement:
                message += f" Use {replacement} instead."
            
            if migration_guide:
                message += f" See {migration_guide} for migration guide."
            
            # Issue deprecation warning
            warnings.warn(
                message,
                DeprecationWarning,
                stacklevel=2
            )
            
            return func(*args, **kwargs)
        
        # Attach deprecation info to function for programmatic access
        wrapper._deprecation_info = deprecation_info
        
        return wrapper
    return decorator


def mark_class_deprecated(
    cls: type,
    version: str,
    removal_version: str,
    reason: str,
    replacement: Optional[str] = None,
    migration_guide: Optional[str] = None
) -> type:
    """
    Mark a class as deprecated.
    
    EVOLVABILITY: Provides deprecation notices for classes (Principle #15).
    
    Args:
        cls: Class to mark as deprecated
        version: Version when class was deprecated
        removal_version: Version when class will be removed
        reason: Reason for deprecation
        replacement: Replacement class name (optional)
        migration_guide: URL or path to migration guide (optional)
        
    Returns:
        Class with deprecation warning on instantiation
        
    Example:
        ```python
        @mark_class_deprecated(
            OldClass,
            version="2.0.0",
            removal_version="3.0.0",
            reason="Use NewClass instead",
            replacement="NewClass"
        )
        class OldClass:
            pass
        ```
    """
    original_init = cls.__init__
    
    deprecation_info = DeprecationInfo(
        version=version,
        removal_version=removal_version,
        reason=reason,
        replacement=replacement,
        migration_guide=migration_guide
    )
    
    def __init__(self, *args, **kwargs):
        # Build deprecation message
        message = f"{cls.__name__} is deprecated since version {version}."
        message += f" It will be removed in version {removal_version}."
        message += f" Reason: {reason}"
        
        if replacement:
            message += f" Use {replacement} instead."
        
        if migration_guide:
            message += f" See {migration_guide} for migration guide."
        
        # Issue deprecation warning
        warnings.warn(
            message,
            DeprecationWarning,
            stacklevel=2
        )
        
        original_init(self, *args, **kwargs)
    
    cls.__init__ = __init__
    cls._deprecation_info = deprecation_info
    
    return cls


def check_deprecation_status(
    current_version: str,
    deprecation_version: str,
    removal_version: str
) -> str:
    """
    Check deprecation status for a version.
    
    EVOLVABILITY: Helps determine if a feature is deprecated or removed (Principle #15).
    
    Args:
        current_version: Current version (e.g., "2.1.0")
        deprecation_version: Version when feature was deprecated (e.g., "2.0.0")
        removal_version: Version when feature will be removed (e.g., "3.0.0")
        
    Returns:
        Status string: "active", "deprecated", or "removed"
        
    Example:
        ```python
        status = check_deprecation_status("2.1.0", "2.0.0", "3.0.0")
        # Returns: "deprecated"
        ```
    """
    # Simple version comparison (assumes semantic versioning)
    def version_tuple(v: str) -> tuple:
        """Convert version string to tuple for comparison."""
        parts = v.replace("v", "").split(".")
        return tuple(int(p) for p in parts if p.isdigit())
    
    current = version_tuple(current_version)
    deprecated_ver = version_tuple(deprecation_version)
    removed_ver = version_tuple(removal_version)
    
    if current < deprecated_ver:
        return "active"
    elif current < removed_ver:
        return "deprecated"
    else:
        return "removed"


def get_deprecation_info(func: Callable) -> Optional[DeprecationInfo]:
    """
    Get deprecation information for a function.
    
    EVOLVABILITY: Allows programmatic access to deprecation metadata (Principle #15).
    
    Args:
        func: Function to check
        
    Returns:
        DeprecationInfo if function is deprecated, None otherwise
    """
    return getattr(func, "_deprecation_info", None)


__all__ = [
    "deprecated",
    "mark_class_deprecated",
    "check_deprecation_status",
    "get_deprecation_info",
    "DeprecationInfo",
]

