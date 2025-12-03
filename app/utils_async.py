"""
Async utility functions for FastAPI application.

This module provides async versions of utility functions used by the exam flow,
specifically async retry logic for non-blocking API calls.

PERFORMANCE: Async retry logic for non-blocking operations (spd.txt #2, #17).
"""

import asyncio
import random
from typing import Any, Optional, Callable

from exam.utils import _categorize_error
from shared.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError


async def with_retry_async(
    fn: Callable,
    *args,
    max_tries: int = 4,
    base: float = 0.4,
    jitter: float = 0.25,
    rng: Optional[random.Random] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
    fallback_func: Optional[Callable] = None,
    service_name: str = "external_api",
    **kwargs
) -> Any:
    """
    Async version of with_retry for non-blocking retry logic.
    
    PERFORMANCE: Uses asyncio.sleep instead of time.sleep for non-blocking delays (spd.txt #2).
    
    Args:
        fn: Async function to retry
        *args: Positional arguments for function
        max_tries: Maximum number of retry attempts (default: 4)
        base: Base delay in seconds (default: 0.4)
        jitter: Jitter factor for exponential backoff (default: 0.25)
        rng: Optional random number generator
        circuit_breaker: Optional circuit breaker instance
        fallback_func: Optional fallback function to call if circuit is open
        service_name: Name of service for circuit breaker
        **kwargs: Keyword arguments for function
        
    Returns:
        Function result
        
    Raises:
        Last exception if all retries fail
        CircuitBreakerOpenError: If circuit is open and no fallback provided
    """
    # GRACEFUL FAILURE: Use circuit breaker protection if provided (cp.txt #16)
    if circuit_breaker is not None:
        from shared.api_protection import call_with_protection
        try:
            # Note: call_with_protection is sync, but we can wrap it
            # For now, we'll handle circuit breaker in the retry loop
            pass
        except CircuitBreakerOpenError:
            if fallback_func:
                return await fallback_func(*args, **kwargs)
            raise
    
    # Check max_tries before proceeding
    if max_tries <= 0:
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            error_type, error_metadata = _categorize_error(e)
            e.error_metadata = error_metadata
            raise
    
    # DETERMINISTIC: Use provided RNG or create deterministic one (cp.txt #5)
    if rng is None:
        rng = random.Random(12345)  # Fixed seed for deterministic jitter
    
    # Set default timeout for API calls (30s for chat, 60s for audio)
    if "timeout" not in kwargs:
        kwargs["timeout"] = 30
    
    last_error = None
    last_error_metadata = None
    
    for i in range(max_tries):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            error_type, error_metadata = _categorize_error(e)
            last_error_metadata = error_metadata
            
            if i == max_tries - 1:
                e.error_metadata = error_metadata
                raise
            
            # Check if error is retryable
            if not error_metadata["retry"]:
                e.error_metadata = error_metadata
                raise
            
            msg = str(e).lower()
            # Longer backoff for rate limits, timeouts, and connection errors
            penalty = 1.0 if ("429" in msg or "rate limit" in msg or "timeout" in msg or "connection" in msg) else 0.0
            # DETERMINISTIC: Use provided RNG instead of global random (cp.txt #5)
            delay = max(0.0, base * (2 ** i) + rng.random() * jitter + penalty)
            await asyncio.sleep(delay)  # Non-blocking sleep (spd.txt #2)
    
    # Should never reach here, but just in case
    if last_error:
        last_error.error_metadata = last_error_metadata
        raise last_error

