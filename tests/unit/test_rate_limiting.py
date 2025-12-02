"""
Unit tests for shared.rate_limiting module.

These tests verify rate limiting functionality.
"""

import pytest
import time
from shared.rate_limiting import (
    RateLimiter,
    RateLimitConfig,
    TokenBucket,
    get_default_rate_limiter
)


class TestTokenBucket:
    """Tests for TokenBucket class."""
    
    def test_token_bucket_initialization(self):
        """Test token bucket initialization."""
        bucket = TokenBucket(tokens=10.0, capacity=10.0, refill_rate=1.0)
        assert bucket.tokens == 10.0
        assert bucket.capacity == 10.0
        assert bucket.refill_rate == 1.0
    
    def test_token_bucket_consume_success(self):
        """Test successful token consumption."""
        bucket = TokenBucket(tokens=10.0, capacity=10.0, refill_rate=1.0)
        assert bucket.consume(5.0) is True
        assert bucket.tokens == 5.0
    
    def test_token_bucket_consume_failure(self):
        """Test failed token consumption (insufficient tokens)."""
        bucket = TokenBucket(tokens=2.0, capacity=10.0, refill_rate=1.0)
        assert bucket.consume(5.0) is False
        assert bucket.tokens == 2.0
    
    def test_token_bucket_refill(self):
        """Test token refill over time."""
        bucket = TokenBucket(tokens=0.0, capacity=10.0, refill_rate=1.0)
        initial_time = time.time()
        bucket.last_refill = initial_time - 5.0  # 5 seconds ago
        
        bucket.refill(initial_time)
        assert bucket.tokens == 5.0  # Should have refilled 5 tokens
    
    def test_token_bucket_refill_capacity_limit(self):
        """Test that refill doesn't exceed capacity."""
        bucket = TokenBucket(tokens=8.0, capacity=10.0, refill_rate=1.0)
        initial_time = time.time()
        bucket.last_refill = initial_time - 5.0  # 5 seconds ago
        
        bucket.refill(initial_time)
        assert bucket.tokens == 10.0  # Should cap at capacity


class TestRateLimiter:
    """Tests for RateLimiter class."""
    
    def test_rate_limiter_initialization(self):
        """Test rate limiter initialization."""
        config = RateLimitConfig(
            requests_per_minute=60,
            requests_per_hour=1000,
            burst_size=10
        )
        limiter = RateLimiter("test", config)
        assert limiter.config == config
        assert limiter.name == "test"
    
    def test_rate_limiter_allows_request(self):
        """Test that rate limiter allows requests within limits."""
        config = RateLimitConfig(requests_per_minute=60, burst_size=10)
        limiter = RateLimiter("test", config)
        
        allowed, error = limiter.check_rate_limit("test_key")
        assert allowed is True
        assert error is None
    
    def test_rate_limiter_blocks_excessive_requests(self):
        """Test that rate limiter blocks excessive requests."""
        config = RateLimitConfig(requests_per_minute=2, burst_size=2)
        limiter = RateLimiter("test", config)
        
        # First two requests should succeed
        allowed1, _ = limiter.check_rate_limit("test_key")
        allowed2, _ = limiter.check_rate_limit("test_key")
        assert allowed1 is True
        assert allowed2 is True
        
        # Third request should fail (burst exceeded)
        allowed3, error3 = limiter.check_rate_limit("test_key")
        assert allowed3 is False
        assert error3 is not None
        assert "rate limit" in error3.lower()
    
    def test_rate_limiter_tracks_stats(self):
        """Test that rate limiter tracks statistics."""
        config = RateLimitConfig(requests_per_minute=60)
        limiter = RateLimiter("test", config)
        
        limiter.check_rate_limit("test_key")
        limiter.check_rate_limit("test_key")
        
        stats = limiter.get_stats("test_key")
        assert stats["requests"] == 2
        assert stats["violations"] == 0
    
    def test_rate_limiter_tracks_violations(self):
        """Test that rate limiter tracks violations."""
        config = RateLimitConfig(requests_per_minute=1, burst_size=1)
        limiter = RateLimiter("test", config)
        
        limiter.check_rate_limit("test_key")  # First request succeeds
        limiter.check_rate_limit("test_key")  # Second request fails
        
        stats = limiter.get_stats("test_key")
        assert stats["requests"] == 1
        assert stats["violations"] == 1
    
    def test_rate_limiter_reset_key(self):
        """Test that reset_key clears rate limit data."""
        config = RateLimitConfig(requests_per_minute=1, burst_size=1)
        limiter = RateLimiter("test", config)
        
        limiter.check_rate_limit("test_key")
        limiter.reset_key("test_key")
        
        # After reset, should be able to make request again
        allowed, _ = limiter.check_rate_limit("test_key")
        assert allowed is True
    
    def test_rate_limiter_different_keys(self):
        """Test that rate limiter tracks different keys independently."""
        config = RateLimitConfig(requests_per_minute=1, burst_size=1)
        limiter = RateLimiter("test", config)
        
        # Both keys should be able to make requests
        allowed1, _ = limiter.check_rate_limit("key1")
        allowed2, _ = limiter.check_rate_limit("key2")
        
        assert allowed1 is True
        assert allowed2 is True


class TestGetDefaultRateLimiter:
    """Tests for get_default_rate_limiter function."""
    
    def test_get_default_rate_limiter_returns_instance(self):
        """Test that get_default_rate_limiter returns a RateLimiter."""
        limiter = get_default_rate_limiter()
        assert isinstance(limiter, RateLimiter)
    
    def test_get_default_rate_limiter_singleton(self):
        """Test that get_default_rate_limiter returns same instance."""
        limiter1 = get_default_rate_limiter()
        limiter2 = get_default_rate_limiter()
        assert limiter1 is limiter2

