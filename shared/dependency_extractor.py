"""
Dependency extraction utilities for reducing code duplication.

This module provides helpers for extracting dependencies from dependency dictionaries
in a DRY (Don't Repeat Yourself) way while preserving the dependency injection pattern.

**Purpose**: 
Centralizes the common pattern of extracting required and optional dependencies
from dependency injection dictionaries, reducing boilerplate code across handlers.

**Key Functions**:
- `extract_dependencies()`: Extract with validation (raises on missing required)
- `extract_dependencies_safe()`: Extract with safe defaults (returns None for missing)

**Usage Example**:
    ```python
    from shared.dependency_extractor import extract_dependencies
    
    # In a handler function
    def my_handler(s, dependencies):
        # Extract dependencies (validates required keys exist)
        deps = extract_dependencies(
            dependencies,
            required_keys=["ensure_state", "save_state_to_disk"],
            optional_keys=["ProctorState", "rate_limiter"]
        )
        
        # Use extracted dependencies
        s = deps["ensure_state"](s)
        deps["save_state_to_disk"](s)
        
        # Optional dependencies are None if not provided
        if deps["ProctorState"]:
            # Use proctor state
            pass
    ```

**Benefits**:
- Reduces code duplication (60+ lines saved across handlers)
- Validates dependencies early (fails fast on missing required)
- Maintains explicit dependency injection pattern
- Preserves wiring (no breaking changes)
"""

from typing import Dict, Any, List, Optional


def extract_dependencies(
    dependencies: Dict[str, Any],
    required_keys: List[str],
    optional_keys: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Extract dependencies from dictionary with validation.
    
    **Contract**:
    - **Inputs**: Dependencies dictionary, required_keys list, optional optional_keys list
    - **Outputs**: Dictionary with extracted dependencies
    - **Invariants**: All required_keys must exist in dependencies dictionary
    - **Failure Modes**: Raises KeyError if required key is missing
    
    This function reduces duplication in dependency extraction patterns while
    maintaining the explicit dependency injection approach. It validates that
    all required dependencies are present and extracts optional ones safely.
    
    Args:
        dependencies: Dependencies dictionary (from dependency injection)
        required_keys: List of required dependency keys (must exist)
        optional_keys: List of optional dependency keys (use .get() if not present)
        
    Returns:
        Dictionary with extracted dependencies (same keys as input)
        - Required keys: Always present (validated)
        - Optional keys: Present if provided, None if not provided
        
    Raises:
        KeyError: If required key is missing from dependencies dictionary.
                  Error message includes missing key and available keys.
        
    Example:
        ```python
        deps = extract_dependencies(
            dependencies,
            required_keys=["ensure_state", "save_state_to_disk"],
            optional_keys=["ProctorState"]
        )
        
        s = deps["ensure_state"](s)
        ```
    """
    extracted = {}
    
    # Extract required dependencies (must exist)
    for key in required_keys:
        if key not in dependencies:
            raise KeyError(
                f"Required dependency '{key}' not found in dependencies dictionary. "
                f"Available keys: {list(dependencies.keys())}"
            )
        extracted[key] = dependencies[key]
    
    # Extract optional dependencies (use .get() if not present)
    if optional_keys:
        for key in optional_keys:
            extracted[key] = dependencies.get(key)
    
    return extracted


def extract_dependencies_safe(
    dependencies: Dict[str, Any],
    required_keys: List[str],
    optional_keys: Optional[List[str]] = None,
    default_values: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Extract dependencies with safe defaults (non-raising version).
    
    Similar to extract_dependencies but returns None for missing required keys
    instead of raising. Useful when you want to handle missing dependencies
    gracefully.
    
    Args:
        dependencies: Dependencies dictionary
        required_keys: List of required dependency keys
        optional_keys: List of optional dependency keys
        default_values: Dictionary of default values for missing keys
        
    Returns:
        Dictionary with extracted dependencies (None for missing required keys)
        
    Example:
        ```python
        deps = extract_dependencies_safe(
            dependencies,
            required_keys=["ensure_state"],
            default_values={"ensure_state": lambda s: s}
        )
        ```
    """
    extracted = {}
    default_values = default_values or {}
    
    # Extract required dependencies (use default if missing)
    for key in required_keys:
        extracted[key] = dependencies.get(key, default_values.get(key))
    
    # Extract optional dependencies
    if optional_keys:
        for key in optional_keys:
            extracted[key] = dependencies.get(key)
    
    return extracted

