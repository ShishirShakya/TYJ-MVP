"""
API protection utilities for graceful failure and degradation.

This module provides circuit breaker integration and fallback behavior
for external API calls, ensuring graceful degradation when services fail.

GRACEFUL FAILURE: Provides controlled fallback behavior instead of crashing (Principle #16).
"""

from typing import Optional, Callable, Any, Dict
from shared.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    get_default_circuit_breaker_manager
)
from shared.logging_config import get_logger

logger = get_logger()


def call_with_protection(
    func: Callable,
    circuit_breaker: Optional[CircuitBreaker] = None,
    fallback_func: Optional[Callable] = None,
    service_name: str = "external_api",
    *args,
    **kwargs
) -> Any:
    """
    Execute function with circuit breaker protection and fallback behavior.
    
    GRACEFUL FAILURE: Provides controlled fallback instead of crashing (Principle #16).
    
    Args:
        func: Function to execute (e.g., OpenAI API call)
        circuit_breaker: Optional circuit breaker instance (if None, gets default)
        fallback_func: Optional fallback function to call if circuit is open
        service_name: Name of service for circuit breaker (default: "external_api")
        *args: Positional arguments for function
        **kwargs: Keyword arguments for function
        
    Returns:
        Function result or fallback result
        
    Raises:
        CircuitBreakerOpenError: If circuit is open and no fallback provided
        Original exception: If function raises exception and no fallback
        
    Example:
        ```python
        # With circuit breaker and fallback
        result = call_with_protection(
            lambda: client.chat.completions.create(...),
            circuit_breaker=breaker,
            fallback_func=lambda: get_cached_response(),
            service_name="openai_chat"
        )
        ```
    """
    # Get circuit breaker if not provided
    if circuit_breaker is None:
        manager = get_default_circuit_breaker_manager()
        circuit_breaker = manager.get_breaker(
            service_name,
            config=CircuitBreakerConfig(
                failure_threshold=5,
                success_threshold=2,
                timeout_seconds=60.0,
                expected_exception=Exception
            )
        )
    
    try:
        # Execute with circuit breaker protection
        result = circuit_breaker.call(func, *args, **kwargs)
        return result
    except CircuitBreakerOpenError as e:
        # Circuit is open - use fallback if available
        logger.warning(
            "circuit_breaker_open",
            service_name=service_name,
            message=str(e),
            using_fallback=fallback_func is not None
        )
        
        if fallback_func:
            try:
                logger.info(
                    "using_fallback",
                    service_name=service_name,
                    message="Circuit breaker open, using fallback function"
                )
                return fallback_func()
            except Exception as fallback_error:
                logger.error(
                    "fallback_failed",
                    service_name=service_name,
                    error=str(fallback_error),
                    message="Fallback function also failed"
                )
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{service_name}' is OPEN and fallback failed: {str(fallback_error)}"
                )
        else:
            # No fallback - raise error
            raise
    except Exception as e:
        # Other exceptions are handled by circuit breaker
        raise


def get_cached_response_fallback(
    cache_key: str,
    cache_store: Optional[Dict[str, Any]] = None
) -> Callable:
    """
    Create a fallback function that returns cached response.
    
    GRACEFUL FAILURE: Provides cached data as fallback (Principle #16).
    
    Args:
        cache_key: Key to look up in cache
        cache_store: Optional cache dictionary (if None, returns None fallback)
        
    Returns:
        Fallback function that returns cached response or None
    """
    def fallback():
        if cache_store and cache_key in cache_store:
            logger.info(
                "using_cached_response",
                cache_key=cache_key,
                message="Using cached response as fallback"
            )
            return cache_store[cache_key]
        else:
            logger.warning(
                "no_cached_response",
                cache_key=cache_key,
                message="No cached response available for fallback"
            )
            return None
    
    return fallback


def create_api_protection_wrapper(
    service_name: str,
    circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    fallback_func: Optional[Callable] = None
) -> Callable:
    """
    Create a reusable API protection wrapper for a specific service.
    
    GRACEFUL FAILURE: Provides reusable protection wrapper (Principle #16).
    
    Args:
        service_name: Name of service (e.g., "openai_chat", "openai_audio")
        circuit_breaker_config: Optional circuit breaker configuration
        fallback_func: Optional fallback function
        
    Returns:
        Wrapper function that can be used to protect API calls
        
    Example:
        ```python
        # Create wrapper
        protect_openai_chat = create_api_protection_wrapper(
            "openai_chat",
            fallback_func=lambda: get_cached_question()
        )
        
        # Use wrapper
        result = protect_openai_chat(
            lambda: client.chat.completions.create(...)
        )
        ```
    """
    manager = get_default_circuit_breaker_manager()
    breaker = manager.get_breaker(service_name, circuit_breaker_config)
    
    def wrapper(func: Callable, *args, **kwargs) -> Any:
        return call_with_protection(
            func,
            circuit_breaker=breaker,
            fallback_func=fallback_func,
            service_name=service_name,
            *args,
            **kwargs
        )
    
    return wrapper


__all__ = [
    "call_with_protection",
    "get_cached_response_fallback",
    "create_api_protection_wrapper",
]

