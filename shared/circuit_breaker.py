"""
Circuit breaker implementation for external service calls.

This module provides a circuit breaker pattern to prevent cascading failures
when external services are unavailable. The circuit breaker can be injected
via dependency injection to preserve wiring.

Circuit breaker states:
- CLOSED: Normal operation, requests pass through
- OPEN: Service is failing, requests are rejected immediately
- HALF_OPEN: Testing if service recovered, limited requests allowed
"""

import time
from enum import Enum
from typing import Optional, Callable, Any, Dict
from threading import Lock
from dataclasses import dataclass, field


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """
    Configuration for circuit breaker.
    
    Attributes:
        failure_threshold: Number of failures before opening circuit
        success_threshold: Number of successes in HALF_OPEN before closing
        timeout_seconds: Time in OPEN state before transitioning to HALF_OPEN
        expected_exception: Exception type(s) that indicate failure (default: Exception)
    """
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: float = 60.0
    expected_exception: type | tuple = Exception


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker."""
    failures: int = 0
    successes: int = 0
    state_changes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None


class CircuitBreaker:
    """
    Circuit breaker for protecting external service calls.
    
    THREAD-SAFETY: Thread-safe implementation using locks.
    All operations are safe for concurrent access from multiple threads.
    See docs/CONCURRENCY_THREAD_SAFETY.md for details.
    """
    
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        """
        Initialize circuit breaker.
        
        Args:
            name: Name of the circuit breaker (for logging)
            config: Circuit breaker configuration
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._lock = Lock()
        self._state = CircuitState.CLOSED
        self._stats = CircuitBreakerStats()
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._opened_at: Optional[float] = None
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        **Contract**:
        - **Inputs**: Function to execute, its arguments
        - **Outputs**: Function result (if successful)
        - **Invariants**: State transitions are atomic
        - **Failure Modes**: Raises CircuitBreakerOpenError if circuit is open
        
        **Graceful Failure** (Principle #16):
        - Prevents cascading failures by opening circuit after threshold failures
        - Automatically recovers when service becomes available
        - Provides clear error messages for debugging
        
        **Thread Safety** (Principle #20):
        - State check and transition are atomic (inside lock)
        - Prevents race conditions when multiple threads check state simultaneously
        - All state modifications are protected by locks
        
        **Circuit States**:
        - CLOSED: Normal operation, requests pass through
        - OPEN: Service unavailable, requests rejected immediately
        - HALF_OPEN: Testing if service recovered, allows limited requests
        
        Args:
            func: Function to execute (must be callable)
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function
            
        Returns:
            Function result (if execution succeeds)
            
        Raises:
            CircuitBreakerOpenError: If circuit is OPEN and timeout hasn't passed
            Original exception: If function raises expected exception (circuit stays open)
            
        Example:
            ```python
            breaker = CircuitBreaker("api_service")
            try:
                result = breaker.call(api_client.get_data, param1, param2)
            except CircuitBreakerOpenError:
                # Service unavailable, use fallback
                result = cached_data
            ```
        """
        # THREAD-SAFETY: Check state and handle transitions atomically inside lock
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if timeout has passed
                if self._opened_at and (time.time() - self._opened_at) >= self.config.timeout_seconds:
                    # Transition to HALF_OPEN (atomic)
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    self._stats.state_changes += 1
                else:
                    # Circuit is still open, reject request
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is OPEN. "
                        f"Service unavailable. Retry after {self.config.timeout_seconds}s"
                    )
        
        # Execute function
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.config.expected_exception as e:
            self._on_failure()
            raise
    
    def _on_success(self) -> None:
        """Handle successful call."""
        with self._lock:
            self._stats.successes += 1
            self._stats.last_success_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    # Transition to CLOSED
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    self._opened_at = None
                    self._stats.state_changes += 1
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0
    
    def _on_failure(self) -> None:
        """Handle failed call."""
        with self._lock:
            self._stats.failures += 1
            self._stats.last_failure_time = time.time()
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                # Failure in HALF_OPEN, go back to OPEN
                self._state = CircuitState.OPEN
                self._opened_at = time.time()
                self._failure_count = 0
                self._success_count = 0
                self._stats.state_changes += 1
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.config.failure_threshold:
                    # Open circuit
                    self._state = CircuitState.OPEN
                    self._opened_at = time.time()
                    self._stats.state_changes += 1
    
    def get_state(self) -> CircuitState:
        """
        Get current circuit breaker state.
        
        Returns:
            Current state
        """
        return self._state
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get circuit breaker statistics.
        
        Returns:
            Dictionary with statistics
        """
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failures": self._stats.failures,
                "successes": self._stats.successes,
                "state_changes": self._stats.state_changes,
                "last_failure_time": self._stats.last_failure_time,
                "last_success_time": self._stats.last_success_time,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
            }
    
    def reset(self) -> None:
        """Reset circuit breaker to CLOSED state (mainly for testing)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._opened_at = None
            self._stats = CircuitBreakerStats()


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""
    pass


class CircuitBreakerManager:
    """
    Manager for multiple circuit breakers.
    
    Provides a convenient way to manage circuit breakers for different services.
    """
    
    def __init__(self):
        """Initialize circuit breaker manager."""
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = Lock()
    
    def get_breaker(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        """
        Get or create a circuit breaker.
        
        Args:
            name: Name of the circuit breaker
            config: Optional configuration (used only for new breakers)
            
        Returns:
            CircuitBreaker instance
        """
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, config)
            return self._breakers[name]
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics for all circuit breakers.
        
        Returns:
            Dictionary mapping breaker names to their stats
        """
        with self._lock:
            return {name: breaker.get_stats() for name, breaker in self._breakers.items()}
    
    def reset_all(self) -> None:
        """Reset all circuit breakers (mainly for testing)."""
        with self._lock:
            for breaker in self._breakers.values():
                breaker.reset()


# Global circuit breaker manager
_default_manager: Optional[CircuitBreakerManager] = None


def get_default_circuit_breaker_manager() -> CircuitBreakerManager:
    """
    Get or create default circuit breaker manager.
    
    Returns:
        CircuitBreakerManager instance
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = CircuitBreakerManager()
    return _default_manager


def create_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """
    Create a new circuit breaker instance.
    
    Args:
        name: Name of the circuit breaker
        config: Optional configuration
        
    Returns:
        New CircuitBreaker instance
    """
    return CircuitBreaker(name, config)

