"""
Property-based tests for retry logic.

These tests use property-based testing to verify that retry logic
behaves correctly across a wide range of scenarios.

PROPERTY-BASED TESTING: Tests invariants and properties rather than specific cases (Principle #14).
"""

import pytest
from hypothesis import given, strategies as st, assume
from unittest.mock import Mock, MagicMock, patch
import random
from typing import Callable, Any

from exam.utils import with_retry
from shared.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpenError


class TestRetryLogicProperties:
    """Property-based tests for retry logic."""
    
    @given(
        max_tries=st.integers(min_value=1, max_value=10),
        base_delay=st.floats(min_value=0.1, max_value=10.0),
        jitter=st.floats(min_value=0.0, max_value=5.0),
        failure_count=st.integers(min_value=0, max_value=20),
    )
    @patch('exam.utils.time.sleep')
    def test_with_retry_eventual_success(
        self,
        mock_sleep,
        max_tries: int,
        base_delay: float,
        jitter: float,
        failure_count: int
    ):
        """
        Property: Retry eventually succeeds if function succeeds within max_tries.
        
        Given a function that fails N times then succeeds,
        retry should eventually succeed if N < max_tries.
        """
        assume(failure_count < max_tries)
        
        call_count = [0]
        def mock_function(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= failure_count:
                raise Exception(f"Simulated failure {call_count[0]}")
            return "success"
        
        # Use deterministic RNG for testing
        rng = random.Random(42)
        
        result = with_retry(
            mock_function,
            max_tries=max_tries,
            base=base_delay,
            jitter=jitter,
            rng=rng
        )
        
        # Property: Should eventually succeed
        assert result == "success"
        assert call_count[0] == failure_count + 1
    
    @given(
        max_tries=st.integers(min_value=1, max_value=10),
        failure_count=st.integers(min_value=1, max_value=20),
    )
    @patch('exam.utils.time.sleep')
    def test_with_retry_too_many_failures(
        self,
        mock_sleep,
        max_tries: int,
        failure_count: int
    ):
        """
        Property: Retry fails if function fails more than max_tries times.
        
        Given a function that always fails,
        retry should raise exception after max_tries attempts.
        """
        assume(failure_count >= max_tries)
        
        call_count = [0]
        def mock_function(*args, **kwargs):
            call_count[0] += 1
            raise Exception(f"Simulated failure {call_count[0]}")
        
        # Use deterministic RNG for testing
        rng = random.Random(42)
        
        with pytest.raises(Exception):
            with_retry(
                mock_function,
                max_tries=max_tries,
                rng=rng
            )
        
        # Property: Should attempt exactly max_tries times
        assert call_count[0] == max_tries
    
    @given(
        max_tries=st.integers(min_value=1, max_value=10),
        base_delay=st.floats(min_value=0.1, max_value=10.0),
    )
    @patch('exam.utils.time.sleep')
    def test_with_retry_exponential_backoff(
        self,
        mock_sleep,
        max_tries: int,
        base_delay: float
    ):
        """
        Property: Retry uses exponential backoff (delays increase exponentially).
        
        Given a function that always fails,
        delays between retries should increase exponentially.
        """
        # Track sleep calls to verify exponential backoff
        sleep_calls = []
        def track_sleep(delay):
            sleep_calls.append(delay)
        
        mock_sleep.side_effect = track_sleep
        
        call_count = [0]
        def mock_function(*args, **kwargs):
            call_count[0] += 1
            raise Exception(f"Simulated failure {call_count[0]}")
        
        # Use deterministic RNG for testing (no jitter for predictable delays)
        rng = random.Random(42)
        
        try:
            with_retry(
                mock_function,
                max_tries=max_tries,
                base=base_delay,
                jitter=0.0,  # No jitter for predictable delays
                rng=rng
            )
        except Exception:
            pass  # Expected to fail
        
        # Property: Delays should increase exponentially
        if len(sleep_calls) >= 1:
            # Each delay should be approximately base * 2^i (allowing for timing variance)
            for i, delay in enumerate(sleep_calls):
                expected_delay = base_delay * (2 ** i)
                # Allow 20% variance for timing precision
                assert delay >= expected_delay * 0.8, f"Delay {delay} < expected {expected_delay * 0.8}"
                assert delay <= expected_delay * 1.2, f"Delay {delay} > expected {expected_delay * 1.2}"
    
    @given(
        max_tries=st.integers(min_value=1, max_value=10),
    )
    def test_with_retry_circuit_breaker_open(
        self,
        max_tries: int
    ):
        """
        Property: Retry respects circuit breaker OPEN state.
        
        Given a circuit breaker in OPEN state,
        retry should immediately raise CircuitBreakerOpenError.
        """
        circuit_breaker = CircuitBreaker(
            "test_service",
            config=CircuitBreakerConfig(
                failure_threshold=1,
                timeout_seconds=60.0,
                expected_exception=Exception
            )
        )
        
        # Force circuit breaker to OPEN state
        try:
            circuit_breaker.call(lambda: (_ for _ in ()).throw(Exception("Force failure")))
        except Exception:
            pass
        
        call_count = [0]
        def mock_function(*args, **kwargs):
            call_count[0] += 1
            return "success"
        
        # Use deterministic RNG for testing
        rng = random.Random(42)
        
        with pytest.raises(CircuitBreakerOpenError):
            with_retry(
                mock_function,
                max_tries=max_tries,
                circuit_breaker=circuit_breaker,
                service_name="test_service",
                rng=rng
            )
        
        # Property: Should not call function when circuit is open
        assert call_count[0] == 0
    
    @given(
        max_tries=st.integers(min_value=1, max_value=10),
    )
    def test_with_retry_fallback_function(
        self,
        max_tries: int
    ):
        """
        Property: Retry uses fallback function when circuit breaker is open.
        
        Given a circuit breaker in OPEN state and a fallback function,
        retry should call fallback instead of raising exception.
        """
        circuit_breaker = CircuitBreaker(
            "test_service",
            config=CircuitBreakerConfig(
                failure_threshold=1,
                timeout_seconds=60.0,
                expected_exception=Exception
            )
        )
        
        # Force circuit breaker to OPEN state
        try:
            circuit_breaker.call(lambda: (_ for _ in ()).throw(Exception("Force failure")))
        except Exception:
            pass
        
        call_count = [0]
        fallback_called = [False]
        
        def mock_function(*args, **kwargs):
            call_count[0] += 1
            return "success"
        
        def fallback_function():
            fallback_called[0] = True
            return "fallback_result"
        
        # Use deterministic RNG for testing
        rng = random.Random(42)
        
        result = with_retry(
            mock_function,
            max_tries=max_tries,
            circuit_breaker=circuit_breaker,
            service_name="test_service",
            fallback_func=fallback_function,
            rng=rng
        )
        
        # Property: Should use fallback when circuit is open
        assert result == "fallback_result"
        assert fallback_called[0] is True
        assert call_count[0] == 0

