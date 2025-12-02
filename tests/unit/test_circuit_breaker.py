"""
Unit tests for shared.circuit_breaker module.

These tests verify circuit breaker functionality and state transitions.
"""

import pytest
import time
from shared.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitBreakerOpenError,
    CircuitBreakerManager,
    get_default_circuit_breaker_manager
)


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""
    
    def test_circuit_breaker_initialization(self):
        """Test circuit breaker initialization."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        assert breaker.name == "test"
        assert breaker.get_state() == CircuitState.CLOSED
    
    def test_circuit_breaker_success(self):
        """Test successful call through circuit breaker."""
        breaker = CircuitBreaker("test")
        
        def success_func():
            return "success"
        
        result = breaker.call(success_func)
        assert result == "success"
        assert breaker.get_state() == CircuitState.CLOSED
    
    def test_circuit_breaker_failure(self):
        """Test failure handling."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2))
        
        def fail_func():
            raise ValueError("Test error")
        
        # First failure
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        assert breaker.get_state() == CircuitState.CLOSED
        
        # Second failure - should open circuit
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        assert breaker.get_state() == CircuitState.OPEN
    
    def test_circuit_breaker_open_rejects(self):
        """Test that open circuit rejects requests."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=1))
        
        def fail_func():
            raise ValueError("Test error")
        
        # Open circuit
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        
        # Should reject immediately
        with pytest.raises(CircuitBreakerOpenError):
            breaker.call(lambda: "should not execute")
    
    def test_circuit_breaker_half_open_recovery(self):
        """Test circuit breaker recovery through HALF_OPEN state."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=2,
            timeout_seconds=0.1  # Short timeout for testing
        )
        breaker = CircuitBreaker("test", config)
        
        def fail_func():
            raise ValueError("Test error")
        
        # Open circuit
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        assert breaker.get_state() == CircuitState.OPEN
        
        # Wait for timeout
        time.sleep(0.2)
        
        # First success in HALF_OPEN
        breaker.call(lambda: "success1")
        assert breaker.get_state() == CircuitState.HALF_OPEN
        
        # Second success - should close circuit
        breaker.call(lambda: "success2")
        assert breaker.get_state() == CircuitState.CLOSED
    
    def test_circuit_breaker_half_open_failure(self):
        """Test that failure in HALF_OPEN reopens circuit."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=2,
            timeout_seconds=0.1
        )
        breaker = CircuitBreaker("test", config)
        
        def fail_func():
            raise ValueError("Test error")
        
        # Open circuit
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        
        # Wait for timeout
        time.sleep(0.2)
        
        # Failure in HALF_OPEN should reopen
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        assert breaker.get_state() == CircuitState.OPEN
    
    def test_circuit_breaker_stats(self):
        """Test circuit breaker statistics."""
        breaker = CircuitBreaker("test")
        
        breaker.call(lambda: "success")
        breaker.call(lambda: "success")
        
        stats = breaker.get_stats()
        assert stats["successes"] == 2
        assert stats["failures"] == 0
        assert stats["state"] == CircuitState.CLOSED.value
    
    def test_circuit_breaker_reset(self):
        """Test resetting circuit breaker."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=1))
        
        def fail_func():
            raise ValueError("Test error")
        
        # Open circuit
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        assert breaker.get_state() == CircuitState.OPEN
        
        # Reset
        breaker.reset()
        assert breaker.get_state() == CircuitState.CLOSED
        
        # Should work again
        result = breaker.call(lambda: "success")
        assert result == "success"


class TestCircuitBreakerManager:
    """Tests for CircuitBreakerManager class."""
    
    def test_manager_get_breaker(self):
        """Test getting breaker from manager."""
        manager = CircuitBreakerManager()
        breaker1 = manager.get_breaker("service1")
        breaker2 = manager.get_breaker("service1")
        
        assert breaker1 is breaker2  # Should return same instance
        assert breaker1.name == "service1"
    
    def test_manager_multiple_breakers(self):
        """Test managing multiple breakers."""
        manager = CircuitBreakerManager()
        breaker1 = manager.get_breaker("service1")
        breaker2 = manager.get_breaker("service2")
        
        assert breaker1 is not breaker2
        assert breaker1.name == "service1"
        assert breaker2.name == "service2"
    
    def test_manager_get_all_stats(self):
        """Test getting stats for all breakers."""
        manager = CircuitBreakerManager()
        breaker1 = manager.get_breaker("service1")
        breaker2 = manager.get_breaker("service2")
        
        breaker1.call(lambda: "success")
        
        stats = manager.get_all_stats()
        assert "service1" in stats
        assert "service2" in stats
        assert stats["service1"]["successes"] == 1
    
    def test_manager_reset_all(self):
        """Test resetting all breakers."""
        manager = CircuitBreakerManager()
        breaker = manager.get_breaker("service1")
        
        def fail_func():
            raise ValueError("Test error")
        
        # Open circuit
        with pytest.raises(ValueError):
            breaker.call(fail_func)
        
        # Reset all
        manager.reset_all()
        assert breaker.get_state() == CircuitState.CLOSED


class TestCircuitBreakerFunctions:
    """Tests for circuit breaker utility functions."""
    
    def test_get_default_circuit_breaker_manager(self):
        """Test that get_default_circuit_breaker_manager returns instance."""
        manager = get_default_circuit_breaker_manager()
        assert isinstance(manager, CircuitBreakerManager)
    
    def test_get_default_circuit_breaker_manager_singleton(self):
        """Test that get_default_circuit_breaker_manager returns same instance."""
        manager1 = get_default_circuit_breaker_manager()
        manager2 = get_default_circuit_breaker_manager()
        assert manager1 is manager2

