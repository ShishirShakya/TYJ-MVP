"""
Error boundary utilities for preventing cascading failures.

This module provides error boundary patterns to isolate failures
between components and prevent cascading failures.

GRACEFUL FAILURE: Prevents cascading failures with clear error boundaries (Principle #16).
"""

from typing import Callable, Any, Optional, Dict
from functools import wraps
from shared.logging_config import get_logger

logger = get_logger()


def error_boundary(
    component_name: str,
    fallback_value: Any = None,
    fallback_func: Optional[Callable] = None,
    log_error: bool = True
) -> Callable:
    """
    Decorator to create an error boundary around a function.
    
    GRACEFUL FAILURE: Isolates failures to prevent cascading (Principle #16).
    
    Args:
        component_name: Name of component (for logging)
        fallback_value: Value to return if function fails (if fallback_func not provided)
        fallback_func: Optional function to call if main function fails
        log_error: Whether to log errors (default: True)
        
    Returns:
        Decorated function with error boundary
        
    Example:
        ```python
        @error_boundary("question_generation", fallback_value="Could you explain your understanding?")
        def generate_question():
            # May raise exception
            return ai_client.generate()
        ```
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_error:
                    logger.error(
                        "error_boundary_caught",
                        component=component_name,
                        error_type=type(e).__name__,
                        error_message=str(e)[:200],
                        message=f"Error boundary caught exception in {component_name}"
                    )
                
                # Use fallback function if provided
                if fallback_func:
                    try:
                        return fallback_func(*args, **kwargs)
                    except Exception as fallback_error:
                        logger.error(
                            "fallback_failed",
                            component=component_name,
                            error_type=type(fallback_error).__name__,
                            error_message=str(fallback_error)[:200],
                            message=f"Fallback function also failed in {component_name}"
                        )
                        if fallback_value is not None:
                            return fallback_value
                        raise
                
                # Use fallback value if provided
                if fallback_value is not None:
                    return fallback_value
                
                # Re-raise if no fallback
                raise
        
        return wrapper
    return decorator


def isolate_component(
    component_name: str,
    fallback_value: Any = None
) -> Callable:
    """
    Context manager to isolate a component with error boundary.
    
    GRACEFUL FAILURE: Isolates component failures (Principle #16).
    
    Args:
        component_name: Name of component
        fallback_value: Value to return if component fails
        
    Returns:
        Context manager
        
    Example:
        ```python
        with isolate_component("grading", fallback_value={"score": 0, "feedback": "Error"}):
            result = grade_answer(answer)
        ```
    """
    class ComponentIsolator:
        def __init__(self, name: str, fallback: Any):
            self.name = name
            self.fallback = fallback
            self.result = None
            self.error = None
        
        def __enter__(self):
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is not None:
                logger.error(
                    "component_isolation_caught",
                    component=self.name,
                    error_type=exc_type.__name__ if exc_type else None,
                    error_message=str(exc_val)[:200] if exc_val else None,
                    message=f"Component isolation caught exception in {self.name}"
                )
                self.error = exc_val
                if self.fallback is not None:
                    self.result = self.fallback
                    return True  # Suppress exception
            return False  # Don't suppress exception
    
    return ComponentIsolator(component_name, fallback_value)


__all__ = [
    "error_boundary",
    "isolate_component",
]

