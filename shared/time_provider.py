"""
Time provider abstraction for dependency injection.

This module provides a time provider interface that can be injected via
dependency injection, enabling deterministic testing and preserving wiring.

All time operations should use the time provider instead of direct time.time()
or datetime.now() calls.
"""

from datetime import datetime, timezone
from typing import Protocol
from abc import ABC, abstractmethod


class TimeProvider(Protocol):
    """
    Protocol for time providers.
    
    This allows both real and mock implementations to be used interchangeably.
    """
    
    def time(self) -> float:
        """Get current Unix timestamp as float."""
        ...
    
    def now(self) -> datetime:
        """Get current datetime in local timezone."""
        ...
    
    def utcnow(self) -> datetime:
        """Get current datetime in UTC timezone."""
        ...


class RealTimeProvider:
    """
    Real time provider that uses system time.
    
    This is the default implementation for production use.
    """
    
    def time(self) -> float:
        """Get current Unix timestamp as float."""
        import time
        return time.time()
    
    def now(self) -> datetime:
        """Get current datetime in local timezone."""
        return datetime.now()
    
    def utcnow(self) -> datetime:
        """Get current datetime in UTC timezone."""
        return datetime.now(timezone.utc)


class MockTimeProvider:
    """
    Mock time provider for testing.
    
    Allows setting fixed times and advancing time programmatically.
    """
    
    def __init__(self, initial_time: float = 1000.0):
        """
        Initialize mock time provider.
        
        Args:
            initial_time: Initial Unix timestamp (default: 1000.0)
        """
        self._current_time = initial_time
        self._initial_time = initial_time
    
    def time(self) -> float:
        """Get current mock timestamp."""
        return self._current_time
    
    def now(self) -> datetime:
        """Get current mock datetime in local timezone."""
        return datetime.fromtimestamp(self._current_time)
    
    def utcnow(self) -> datetime:
        """Get current mock datetime in UTC timezone."""
        return datetime.fromtimestamp(self._current_time, tz=timezone.utc)
    
    def set_time(self, timestamp: float) -> None:
        """
        Set the current time.
        
        Args:
            timestamp: Unix timestamp to set
        """
        self._current_time = timestamp
    
    def advance(self, seconds: float) -> None:
        """
        Advance time by specified seconds.
        
        Args:
            seconds: Number of seconds to advance
        """
        self._current_time += seconds
    
    def reset(self) -> None:
        """Reset time to initial value."""
        self._current_time = self._initial_time


# Global default time provider (can be overridden via dependency injection)
_default_time_provider: TimeProvider = RealTimeProvider()


def get_default_time_provider() -> TimeProvider:
    """
    Get the default time provider instance.
    
    Returns:
        TimeProvider instance (RealTimeProvider by default)
    """
    return _default_time_provider


def set_default_time_provider(provider: TimeProvider) -> None:
    """
    Set the default time provider (mainly for testing).
    
    Args:
        provider: TimeProvider instance to use as default
    """
    global _default_time_provider
    _default_time_provider = provider


def create_time_provider(use_mock: bool = False, initial_time: float = 1000.0) -> TimeProvider:
    """
    Create a time provider instance.
    
    Args:
        use_mock: If True, create MockTimeProvider; otherwise RealTimeProvider
        initial_time: Initial time for MockTimeProvider (ignored if use_mock=False)
        
    Returns:
        TimeProvider instance
    """
    if use_mock:
        return MockTimeProvider(initial_time)
    return RealTimeProvider()

