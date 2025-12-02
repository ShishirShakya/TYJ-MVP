"""
Rate limiting and DoS protection module.

This module provides rate limiting functionality to prevent abuse and DoS attacks.
It uses a token bucket algorithm for efficient rate limiting.

All rate limiting is injected via dependency injection to preserve wiring.
"""

import time
from typing import Dict, Optional, Tuple, Any
from threading import Lock
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class RateLimitConfig:
    """
    Configuration for rate limiting.
    
    Attributes:
        requests_per_minute: Maximum requests allowed per minute
        requests_per_hour: Maximum requests allowed per hour
        burst_size: Maximum burst requests allowed
    """
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_size: int = 10


@dataclass
class TokenBucket:
    """
    Token bucket for rate limiting.
    
    Attributes:
        tokens: Current number of tokens
        last_refill: Timestamp of last token refill
        capacity: Maximum tokens in bucket
        refill_rate: Tokens added per second
    """
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.time)
    capacity: float = 10.0
    refill_rate: float = 1.0  # tokens per second
    
    def refill(self, current_time: Optional[float] = None) -> None:
        """
        Refill tokens based on elapsed time.
        
        Args:
            current_time: Current timestamp (defaults to time.time())
        """
        if current_time is None:
            current_time = time.time()
        
        elapsed = current_time - self.last_refill
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = current_time
    
    def consume(self, tokens: float = 1.0, current_time: Optional[float] = None) -> bool:
        """
        Try to consume tokens from bucket.
        
        Args:
            tokens: Number of tokens to consume
            current_time: Current timestamp (defaults to time.time())
            
        Returns:
            True if tokens were consumed, False if insufficient tokens
        """
        self.refill(current_time)
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class RateLimiter:
    """
    Rate limiter using token bucket algorithm.
    
    Supports multiple rate limit windows (per-minute, per-hour) and
    per-key tracking (session, IP, user).
    
    THREAD-SAFETY: Thread-safe implementation using locks.
    All operations are safe for concurrent access from multiple threads.
    See docs/CONCURRENCY_THREAD_SAFETY.md for details.
    """
    
    def __init__(self, name: str = "default", config: Optional[RateLimitConfig] = None):
        """
        Initialize rate limiter.
        
        Args:
            name: Name of the rate limiter (for logging and identification)
            config: Rate limit configuration (defaults to standard config)
        """
        self.name = name
        self.config = config or RateLimitConfig()
        self._lock = Lock()
        
        # Per-minute buckets: key -> TokenBucket
        self._minute_buckets: Dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(
                tokens=self.config.burst_size,
                capacity=self.config.burst_size,
                refill_rate=self.config.requests_per_minute / 60.0
            )
        )
        
        # Per-hour buckets: key -> TokenBucket
        self._hour_buckets: Dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(
                tokens=self.config.requests_per_hour,
                capacity=self.config.requests_per_hour,
                refill_rate=self.config.requests_per_hour / 3600.0
            )
        )
        
        # Request counts for monitoring
        self._request_counts: Dict[str, int] = defaultdict(int)
        self._violation_counts: Dict[str, int] = defaultdict(int)
        
        # OBSERVABILITY: Aggregate statistics for metrics endpoint (Principle #13)
        self._total_requests: int = 0
        self._total_allowed: int = 0
        self._total_rejected: int = 0
    
    def check_rate_limit(
        self,
        key: str,
        current_time: Optional[float] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if request should be allowed based on rate limits.
        
        Args:
            key: Unique identifier (session_id, IP, user_id, etc.)
            current_time: Current timestamp (defaults to time.time())
            
        Returns:
            Tuple of (allowed: bool, error_message: Optional[str])
            - allowed: True if request should be allowed
            - error_message: Error message if rate limit exceeded
        """
        if current_time is None:
            current_time = time.time()
        
        with self._lock:
            # RESOURCE MANAGEMENT: Proactive cleanup to prevent memory growth
            # Clean up old keys if we have too many active keys (prevent unbounded growth)
            _MAX_ACTIVE_KEYS = 10000  # Maximum active keys before proactive cleanup
            if len(self._minute_buckets) > _MAX_ACTIVE_KEYS:
                # Trigger cleanup of old keys (older than 1 hour)
                self.cleanup_old_keys(max_age_seconds=3600)
            
            # OBSERVABILITY: Track total requests for metrics (Principle #13)
            self._total_requests += 1
            
            # Check per-minute limit
            minute_bucket = self._minute_buckets[key]
            if not minute_bucket.consume(1.0, current_time):
                self._violation_counts[key] += 1
                self._total_rejected += 1
                return False, "Rate limit exceeded: too many requests per minute"
            
            # Check per-hour limit
            hour_bucket = self._hour_buckets[key]
            if not hour_bucket.consume(1.0, current_time):
                self._violation_counts[key] += 1
                self._total_rejected += 1
                return False, "Rate limit exceeded: too many requests per hour"
            
            # Request allowed
            self._request_counts[key] += 1
            self._total_allowed += 1
            return True, None
    
    def get_stats(self, key: str) -> Dict[str, int]:
        """
        Get rate limiting statistics for a key.
        
        THREAT MODELING: Provides statistics for traffic pattern monitoring (Principle #12).
        
        Args:
            key: Unique identifier
            
        Returns:
            Dictionary with request count and violation count
        """
        with self._lock:
            return {
                "requests": self._request_counts.get(key, 0),
                "violations": self._violation_counts.get(key, 0),
            }
    
    def get_all_violations(self, min_violations: int = 5) -> Dict[str, Dict[str, Any]]:
        """
        Get all keys with violations above threshold.
        
        THREAT MODELING: Used for traffic pattern monitoring and alerting (Principle #12).
        
        Args:
            min_violations: Minimum violations to include (default: 5)
            
        Returns:
            Dictionary mapping keys to their violation statistics
        """
        with self._lock:
            result = {}
            for key, violation_count in self._violation_counts.items():
                if violation_count >= min_violations:
                    result[key] = {
                        "requests": self._request_counts.get(key, 0),
                        "violations": violation_count
                    }
            return result
    
    def get_aggregate_stats(self) -> Dict[str, Any]:
        """
        Get aggregate statistics for metrics endpoint.
        
        OBSERVABILITY: Provides aggregate metrics for monitoring (Principle #13).
        
        Returns:
            Dictionary with total_requests, total_allowed, total_rejected
        """
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "total_allowed": self._total_allowed,
                "total_rejected": self._total_rejected
            }
    
    def reset_key(self, key: str) -> None:
        """
        Reset rate limits for a specific key.
        
        Args:
            key: Unique identifier to reset
        """
        with self._lock:
            self._minute_buckets.pop(key, None)
            self._hour_buckets.pop(key, None)
            self._request_counts.pop(key, None)
            self._violation_counts.pop(key, None)
    
    def cleanup_old_keys(self, max_age_seconds: int = 3600) -> int:
        """
        Clean up old rate limit entries to prevent memory growth.
        
        Args:
            max_age_seconds: Maximum age of entries before cleanup
            
        Returns:
            Number of keys cleaned up
        """
        current_time = time.time()
        cleaned = 0
        
        with self._lock:
            # Clean up minute buckets
            keys_to_remove = []
            for key, bucket in self._minute_buckets.items():
                if current_time - bucket.last_refill > max_age_seconds:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                self._minute_buckets.pop(key, None)
                self._hour_buckets.pop(key, None)
                self._request_counts.pop(key, None)
                self._violation_counts.pop(key, None)
                cleaned += 1
        
        return cleaned


# Global rate limiter instance (can be overridden via dependency injection)
# SCALABILITY NOTE: This is a per-instance default. For distributed rate limiting,
# inject a Redis-backed RateLimiter via dependency injection.
# See docs/SCALABILITY_ARCHITECTURE.md for details.
_default_rate_limiter: Optional[RateLimiter] = None


def get_default_rate_limiter() -> RateLimiter:
    """
    Get or create default rate limiter instance.
    
    SCALABILITY: This returns a per-instance rate limiter. For horizontal scaling
    with shared rate limits across instances, inject a distributed rate limiter
    (e.g., Redis-backed) via dependency injection.
    
    Returns:
        RateLimiter instance
    """
    global _default_rate_limiter
    if _default_rate_limiter is None:
        # Load config from environment if available
        import os
        requests_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
        requests_per_hour = int(os.getenv("RATE_LIMIT_PER_HOUR", "1000"))
        burst_size = int(os.getenv("RATE_LIMIT_BURST", "10"))
        
        config = RateLimitConfig(
            requests_per_minute=requests_per_minute,
            requests_per_hour=requests_per_hour,
            burst_size=burst_size
        )
        _default_rate_limiter = RateLimiter("default", config)
    
    return _default_rate_limiter


def create_rate_limiter(name: str = "default", config: Optional[RateLimitConfig] = None) -> RateLimiter:
    """
    Create a new rate limiter instance.
    
    Args:
        name: Name of the rate limiter (for logging and identification)
        config: Rate limit configuration
        
    Returns:
        New RateLimiter instance
    """
    return RateLimiter(name, config)

