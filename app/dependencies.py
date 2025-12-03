"""
Shared dependencies and singletons for the FastAPI application.

This module provides centralized access to shared resources like rate limiters
and circuit breakers, avoiding circular import issues.
"""

from typing import Optional
from shared.rate_limiting import RateLimiter, RateLimitConfig
from shared.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from openai import AsyncOpenAI, OpenAI
import os

# These will be initialized in main.py
_rate_limiter: Optional[RateLimiter] = None
_circuit_breaker: Optional[CircuitBreaker] = None
_openai_client: Optional[AsyncOpenAI] = None
_openai_client_sync: Optional[OpenAI] = None  # Sync client for exam flow functions


def initialize_dependencies(
    rate_limit_config: Optional[RateLimitConfig] = None,
    circuit_breaker_config: Optional[CircuitBreakerConfig] = None
) -> None:
    """
    Initialize shared dependencies.
    
    This should be called once during app startup in main.py.
    """
    global _rate_limiter, _circuit_breaker, _openai_client
    
    if _rate_limiter is None:
        _rate_limiter = RateLimiter("api", config=rate_limit_config or RateLimitConfig())
    
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker(
            "external_apis",
            config=circuit_breaker_config or CircuitBreakerConfig(
                failure_threshold=5,
                timeout_seconds=60,
                expected_exception=Exception
            )
        )
    
    if _openai_client is None:
        # PERFORMANCE: Use AsyncOpenAI for non-blocking API calls (spd.txt #17, #2)
        _openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    if _openai_client_sync is None:
        # Keep sync client for exam flow functions (they're synchronous)
        _openai_client_sync = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def get_rate_limiter() -> RateLimiter:
    """Get the shared rate limiter instance."""
    if _rate_limiter is None:
        raise RuntimeError("Dependencies not initialized. Call initialize_dependencies() first.")
    return _rate_limiter


def get_circuit_breaker() -> CircuitBreaker:
    """Get the shared circuit breaker instance."""
    if _circuit_breaker is None:
        raise RuntimeError("Dependencies not initialized. Call initialize_dependencies() first.")
    return _circuit_breaker


def get_openai_client() -> AsyncOpenAI:
    """Get the shared AsyncOpenAI client instance."""
    if _openai_client is None:
        raise RuntimeError("Dependencies not initialized. Call initialize_dependencies() first.")
    return _openai_client


def get_openai_client_sync() -> OpenAI:
    """Get the shared synchronous OpenAI client instance (for exam flow functions)."""
    if _openai_client_sync is None:
        raise RuntimeError("Dependencies not initialized. Call initialize_dependencies() first.")
    return _openai_client_sync

